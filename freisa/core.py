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
                    sys.exit(f"[{log}] stopped early: '{watch}' found in the log, see {os.path.relpath(self.cur_log)}")
        if p.returncode:
            sys.exit(f"[{log}] failed ({p.returncode}), see {os.path.relpath(self.work / (log + '.log'))}")

class Backend:
    stage = name = None
    tools = []  # executables needed
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

def pick(stage, flow, target, profile=None):
    name = flow.get("stages", {}).get(stage)
    name = (target.get("flow") or {}).get(stage, name)
    name = (flow.get("profiles", {}).get(profile) or {}).get(stage, name) if profile else name
    if name not in REGISTRY.get(stage, {}):
        sys.exit(f"stage '{stage}': backend '{name}' unknown (have {list(REGISTRY.get(stage, {}))})")
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
    if variants == "all":
        variants = [{"backend": n} for n, cls in REGISTRY[stage].items() if cls().supports(ctx.target) is None]
        variants.sort(key=lambda v: v["backend"] != b.name)  # the selected backend first: it defines the ranking metric
    def one(i_v):
        i, v = i_v
        c = copy.copy(ctx); c.cfg = {**ctx.cfg, **v}; c.work = ctx.work / f"{stage}_v{i}"; c.art = dict(ctx.art)
        c.work.mkdir(parents=True, exist_ok=True)
        try:
            bk = REGISTRY[stage][v["backend"]]() if "backend" in v else b  # variants may pick a different tool
            why = bk.supports(ctx.target)
            if why: print(f"   {stage} v{i} skipped: {why}"); return i, v, c, None
            bk.run(c); return i, v, c, bk.score(c)
        except SystemExit as e:
            return i, v, c, None
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(one, enumerate(variants)))
    metric = lambda v: (REGISTRY[stage][v["backend"]] if "backend" in v else type(b)).metric
    ok = [r for r in res if r[3] is not None]
    for i, v, c, s in res: print(f"   {stage} v{i} {v} [{metric(v)}]: {'FAILED' if s is None else s}")
    ok = [r for r in ok if metric(r[1]) == metric(res[0][1])] or ok  # rank only comparable scores
    if not ok: sys.exit(f"stage {stage}: every variant failed")
    i, v, c, s = min(ok, key=lambda r: r[3])
    (ctx.work / f"{stage}_best.json").write_text(json.dumps({"variant": i, "overlay": v, "score": s, "all": [[r[0], r[3]] for r in res]}))
    print(f"   -> {stage} keeps v{i}")
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
