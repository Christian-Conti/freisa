# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Backend registry, stage runner and YAML loading.
# Module   : core.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import os, importlib, pkgutil, shutil, subprocess, sys, pathlib, yaml

REGISTRY = {}  # stage -> {name: class}
STAGES = ["sources", "synth", "netlist", "place", "route", "bitgen"]

def backend(cls):
    REGISTRY.setdefault(cls.stage, {})[cls.name] = cls
    return cls

def load_backends():
    from . import stages
    for m in pkgutil.iter_modules(stages.__path__):
        importlib.import_module(f"{stages.__name__}.{m.name}")

def _t():
    from . import term
    return term

def _err(msg):
    return _t().error(msg)

class Ctx:
    def __init__(self, target, cfg, work, root):
        self.target, self.cfg, self.work, self.root = target, cfg, pathlib.Path(work), pathlib.Path(root)
        self.art = {}  # artifacts passed between stages: name -> path/list
        self.work.mkdir(parents=True, exist_ok=True)
    def sh(self, cmd, log, watch=None, **kw):
        """Run a command, tee to work/<log>.log, raise on failure. `watch`: regex; if it shows up in the log the command is
        killed early (e.g. a diverging optimizer) and the call fails."""
        import re, time
        self.cur_log = self.work / f"{log}.log"  # the monitor tails this
        with open(self.work / f"{log}.log", "w") as f:
            f.write("$ " + " ".join(map(str, cmd)) + "\n"); f.flush()
            p = subprocess.Popen(list(map(str, cmd)), stdout=f, stderr=subprocess.STDOUT, **kw)
            while p.poll() is None:
                time.sleep(2)
                if watch and re.search(watch, self.cur_log.read_text(errors="replace")[-4000:], re.I):
                    p.terminate(); p.wait()
                    sys.exit(_err(f"{log}: stopped early ('{watch}' in its log), see {os.path.relpath(self.cur_log)}"))
        if p.returncode:
            sys.exit(_err(f"{log} failed (exit {p.returncode}), see {os.path.relpath(self.work / (log + '.log'))}"))

class Backend:
    stage = name = None
    tools = []  # executables needed
    vendor = None  # proprietary tool used by this step (e.g. "vivado"), shown next to the name
    @classmethod
    def label(cls):
        """Name as shown to the user: open tools plain, steps that use a vendor tool marked e.g. `open_io (vivado)`."""
        return cls.name if not cls.vendor or cls.name == cls.vendor else f"{cls.name} ({cls.vendor})"
    metric = "none"  # unit of score(): scores of different metrics are never ranked against each other
    def score(self, ctx):
        """Lower is better; used by `explore:`. Default: no preference."""
        return 0
    def supports(self, target):
        """Return None if usable, else a reason string."""
        miss = [t for t in self.tools if not shutil.which(t)]
        return f"missing tool(s): {', '.join(miss)}" if miss else None

def load_yaml(p):
    return yaml.safe_load(open(p))

AUTO = {  # `auto` in the project file (or a step not listed): first open tool that works on the board, in this order
    "sources": ["files"], "synth": ["yosys"], "netlist": ["rapidwright_if", "yosys_json_if"], "place": ["dreamplacefpga", "in_route"],
    "route": ["rwroute", "nextpnr_interchange"], "bitgen": ["prjxray", "prjuray"], "upload": ["openfpgaloader"]}

def pick(stage, name, target):
    """Backend instance for `name` in `stage`; `auto` resolves to the first AUTO entry the board supports (else the last one)."""
    if name == "auto":
        cands = AUTO[stage]
        name = next((n for n in cands if REGISTRY[stage][n]().supports(target) is None), cands[-1])
    if name not in REGISTRY.get(stage, {}):
        sys.exit(f"step '{stage}': tool '{name}' unknown; available: {', '.join(REGISTRY.get(stage, {}))}")
    return REGISTRY[stage][name]()

def apply_patches(ctx):
    """design.yml `patches: [{file, from, to}]`: tool-compat fixes applied to copies, source tree untouched."""
    for p in ctx.cfg.get("patches", []):
        for i, (f, ft) in enumerate(ctx.art["rtl"]):
            if f.endswith(p["file"]):
                txt = pathlib.Path(f).read_text()
                if p["from"] not in txt: sys.exit(f"patch for {p['file']} no longer applies")
                dst = ctx.work / "patched" / pathlib.Path(f).name
                dst.parent.mkdir(exist_ok=True); dst.write_text(txt.replace(p["from"], p["to"]))
                ctx.art["rtl"][i] = (str(dst), ft)

def explore(stage, b, ctx, variants, jobs):
    """`variants`: list of config overlays (optional `backend:` swaps the tool) or "all" = every backend that supports the target.
    Scores are only compared within one `metric` (the first variant's); other metrics are reported, not ranked.
    Run `variants` (config overlays, optional `backend:` to swap the tool) in parallel, keep the lowest b.score(); returns winner's ctx state."""
    import concurrent.futures as cf, copy, json
    if variants in ("all", "all_open"):
        variants = [{"backend": n} for n, cls in REGISTRY[stage].items() if cls().supports(ctx.target) is None
                    and (variants == "all" or not cls.vendor)]
        variants.sort(key=lambda v: v["backend"] != b.name)  # the selected backend first: it defines the ranking metric
    def one(i_v):
        i, v = i_v
        c = copy.copy(ctx); c.cfg = {**ctx.cfg, **v}; c.work = ctx.work / f"{stage}_v{i}"; c.art = dict(ctx.art)
        c.work.mkdir(parents=True, exist_ok=True)
        try:
            bk = REGISTRY[stage][v["backend"]]() if "backend" in v else b  # variants may pick a different tool
            why = bk.supports(ctx.target)
            if why: print(f"    {_t().dim(f'v{i} skipped: {why}')}"); return i, v, c, None
            bk.run(c); return i, v, c, bk.score(c)
        except SystemExit as e:
            msg = (_t().plain(str(e)).splitlines() or [""])[0][:120]
            print("    " + _t().dim(f"v{i} {v.get('backend', '')} failed: {msg}")); return i, v, c, None
        except Exception as e:  # any error of one variant only fails that variant
            print("    " + _t().dim(f"v{i} {v.get('backend', '')} failed: {type(e).__name__}: {e}"[:140])); return i, v, c, None
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(one, enumerate(variants)))
    metric = lambda v: (REGISTRY[stage][v["backend"]] if "backend" in v else type(b)).metric
    ok = [r for r in res if r[3] is not None]
    for i, v, c, s in res: print(f"    {_t().dim(f'v{i}')} {v} {_t().dim('[' + metric(v) + ']')}: {_t().red('failed') if s is None else s}")
    ok = [r for r in ok if metric(r[1]) == metric(res[0][1])] or ok  # rank only comparable scores
    if not ok: sys.exit(f"stage {stage}: every variant failed")
    i, v, c, s = min(ok, key=lambda r: r[3])
    (ctx.work / f"{stage}_best.json").write_text(json.dumps({"variant": i, "overlay": v, "score": s, "all": [[r[0], r[3]] for r in res]}))
    print(f"    {_t().OK} {stage} keeps {_t().bold(f'v{i}')}")
    ctx.art.update(c.art)

def find_vivado():
    """$VIVADO, then PATH, then /eda/Xilinx/Vivado/<version>/bin/vivado ($VIVADO_ROOT, $VIVADO_VERSION; prefers 2024.1)."""
    if os.environ.get("VIVADO"): return os.environ["VIVADO"]
    if shutil.which("vivado"): return "vivado"
    root = pathlib.Path(os.environ.get("VIVADO_ROOT", "/eda/Xilinx/Vivado"))
    ver = os.environ.get("VIVADO_VERSION", "2024.1")
    found = sorted(root.glob("*/bin/vivado"), key=lambda p: p.parts[-3])
    pref = [p for p in found if p.parts[-3] == ver]
    return str((pref or found[-1:] or [None])[0]) if (pref or found) else None
