# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : RapidWright/DREAMPlaceFPGA netlist, placement and routing backends.
# Module   : rapidwright.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import json, os, pathlib, re, shutil, sys
from ..core import Backend, backend

US_PLUS = ("xczu", "xcvu", "xcku")  # families RapidWright/DREAMPlaceFPGA IF models cover (UltraScale+)

def _jar():
    import rapidwright
    return next(pathlib.Path(rapidwright.__file__).parent.glob("rapidwright-*-standalone-*.jar"))

def rw(ctx, cls, args, log, cwd=None):
    ctx.sh(["java", f"-Xmx{ctx.cfg.get('java_mem', '16g')}", "-cp", _jar(), f"com.xilinx.rapidwright.{cls}", *args], log, cwd=cwd or ctx.work)

class _UsPlus(Backend):
    def supports(self, target):
        if target.get("family") not in US_PLUS:
            return f"UltraScale+ only (target family {target.get('family')})"
        return super().supports(target)

@backend
class RwNetlist(_UsPlus):
    """Yosys EDIF -> RapidWright DCP (no Vivado)."""
    stage, name, tools = "netlist", "rapidwright_edif", ["java"]
    def run(self, ctx):
        ctx.sh([sys.executable, pathlib.Path(__file__).parent.parent / "rw" / "edif2dcp.py", ctx.art["edif"], ctx.target["part"], ctx.work / "linked.dcp"], "edif2dcp")
        ctx.art["dcp"] = ctx.work / "linked.dcp"

@backend
class DreamPlaceFpga(_UsPlus):
    """DCP -> Interchange netlist -> Bookshelf -> DREAMPlaceFPGA (gpu or cpu) -> phys netlist -> DCP."""
    metric = "hpwl"
    stage, name, tools = "place", "dreamplacefpga", ["java"]
    def supports(self, target):
        return super().supports(target) or (None if self._root() else "build DREAMPlaceFPGA: `make install-dreamplace` (or set DREAMPLACEFPGA_ROOT)")
    def _root(self):
        r = pathlib.Path(os.environ.get("DREAMPLACEFPGA_ROOT", pathlib.Path(__file__).parents[2] / "third_party/dreamplacefpga"))
        return r if (r / "install" / "dreamplacefpga" / "Placer.py").exists() else None
    def run(self, ctx):
        root, w, d = self._root(), ctx.work, ctx.work / "dp"
        d.mkdir(exist_ok=True); base = f"design_{abs(hash(str(w))) % 10**8}"  # unique: bookshelf dir is shared under the DREAMPlace root
        shutil.copy(ctx.art["dcp"], d / f"{base}.dcp")
        rw(ctx, "interchange.DcpToInterchange", [d / f"{base}.dcp"], "dcp2if", cwd=d)
        part = ctx.target["part"]
        if not (root / "IFsupport" / f"{part}.device").exists():  # large; generated once per part
            rw(ctx, "interchange.DeviceResourcesExample", [part], "device", cwd=root / "IFsupport")
        # IF2bookshelf hardcodes xcvu3p; run a patched copy for the target part
        patched = root / "IFsupport" / f"IF2bookshelf_{part}.py"  # schema dir is script-relative
        patched.write_text((root / "IFsupport/IF2bookshelf.py").read_text().replace("xcvu3p-ffvc1517-2-e", part)
                            # top-level port refs have no instance; upstream reuses the previous cell for them
                            .replace("                    if port_inst.which() == 'inst':", "                    if port_inst.which() != 'inst':\n                        continue\n                    if port_inst.which() == 'inst':"))
        py = [sys.executable]
        ctx.sh(py + [patched, "--netlist", d / f"{base}.netlist"], "if2bookshelf", cwd=root)
        cfg = {**json.loads((pathlib.Path(__file__).parent.parent / "rw" / "dp_template.json").read_text()),  # settings from RapidWright's tutorial
               "aux_input": f"benchmarks/IF2bookshelf/{base}/design.aux", "gpu": int(ctx.cfg.get("gpu", 0)),
               "part_name": ctx.target["part"], "num_threads": int(ctx.cfg.get("threads", 4)), "result_dir": str(d / "results"),
               **ctx.cfg.get("dreamplace", {})}
        # the default 2000-iteration schedule is sized for big designs; a few hundred cells never reach the stop criterion
        # (overflow stays high because the density force is dominated by filler cells), so scale the schedule with design size
        if "global_place_stages" not in ctx.cfg.get("dreamplace", {}):
            n = sum(1 for _ in open(root / f"benchmarks/IF2bookshelf/{base}/design.nodes"))
            its = int(ctx.cfg.get("dreamplace_iterations", 150 if n < 1000 else 500 if n < 10000 else 2000))
            for st in cfg.get("global_place_stages", []): st["iteration"] = its
            print(f"   dreamplace: {n} nodes -> {its} iterations", flush=True)
        # tiny designs can make the optimizer diverge (HPWL -inf/nan, then a crash): retry with a smaller step and another seed
        for attempt in range(int(ctx.cfg.get("dreamplace_retries", 3))):
            c = json.loads(json.dumps(cfg)); shutil.rmtree(d / "results", ignore_errors=True)
            c["random_seed"] = cfg["random_seed"] + attempt
            for st in c.get("global_place_stages", []): st["learning_rate"] = st.get("learning_rate", 0.01) / 2 ** attempt
            (d / "dp.json").write_text(json.dumps(c, indent=1))
            try:
                ctx.sh(py + [root / "install/dreamplacefpga/Placer.py", d / "dp.json"], "dreamplace", cwd=root, watch=r"HPWL\s+-?(inf|nan)")
                ok = not re.search(r"HPWL\s+-?(inf|nan)", (ctx.work / "dreamplace.log").read_text(), re.I) and any((d / "results").rglob("*.phys"))
            except SystemExit:
                ok = False
            if ok: break
            print(f"   dreamplace attempt {attempt + 1} diverged or crashed; retrying with a smaller step", flush=True)
        else:
            raise SystemExit(f"[dreamplace] failed after {attempt + 1} attempts, see {os.path.relpath(ctx.work / 'dreamplace.log')}")
        phys = next((d / "results").rglob("*.phys"))
        rw(ctx, "interchange.PhysicalNetlistToDcp", [d / f"{base}.netlist", phys, d / f"{base}.xdc", w / "placed.dcp", "--out_of_context"], "phys2dcp")
        ctx.art["dcp"] = w / "placed.dcp"
    def score(self, ctx):  # final HPWL printed by DREAMPlaceFPGA
        import re
        m = re.findall(r"HPWL\s*[:=]?\s*([0-9.eE+]+)", (ctx.work / "dreamplace.log").read_text())
        return float(m[-1]) if m else None

@backend
class RwRoute(_UsPlus):
    """RWRoute: open timing-driven router for UltraScale+ (runs in the RapidWright jar, multi-threaded)."""
    metric = "wirelength"
    stage, name, tools = "route", "rwroute", ["java"]
    def run(self, ctx):
        rw(ctx, "rwroute.RWRoute", [ctx.art["dcp"], ctx.work / "routed.dcp", *ctx.cfg.get("rwroute_args", ["--nonTimingDriven", "--outOfContext"])], "rwroute")  # timing-driven needs clock constraints
        ctx.art["dcp"] = ctx.work / "routed.dcp"
    def score(self, ctx):  # total wirelength reported by RWRoute; unrouted/failed -> None
        import re
        m = re.findall(r"[Tt]otal wirelength:?\s*([0-9]+)", (ctx.work / "rwroute.log").read_text())
        return int(m[-1]) if m else (ctx.work / "routed.dcp").stat().st_size
