"""Fully open P&R + bitstream. Only xc7 (Zynq-7000/Artix/Kintex) has a database (prjxray); nothing open exists for UltraScale+."""
import os, pathlib
from ..core import Backend, backend

def _p(x):  # board paths: ~ and flow-root relative
    return str(pathlib.Path(os.path.expanduser(x)) if os.path.isabs(os.path.expanduser(x)) else pathlib.Path(__file__).parents[2] / x)

class _Xc7(Backend):
    def supports(self, target):
        if target.get("family") != "xc7":
            return f"no open bitstream database for {target.get('family')} (prjxray is xc7 only)"
        return super().supports(target)

@backend
class NextpnrXilinx(_Xc7):
    """nextpnr-xilinx place+route -> FASM (needs chipdb from prjxray-db; see tools/install.sh)."""
    stage, name, tools = "route", "nextpnr_xilinx", ["nextpnr-xilinx"]
    def run(self, ctx):
        t, c = ctx.target, ctx.cfg
        ctx.sh(["nextpnr-xilinx", "--chipdb", _p(t["chipdb"]), "--xdc", ctx.root / c["xdc"][0], "--json", ctx.art["json"],
                "--fasm", ctx.work / "out.fasm"], "nextpnr", cwd=ctx.work)
        ctx.art["fasm"] = ctx.work / "out.fasm"

@backend
class PlaceSkip(Backend):
    stage, name = "place", "in_route"
    def run(self, ctx): pass  # nextpnr does place+route together

@backend
class Prjxray(_Xc7):
    stage, name, tools = "bitgen", "prjxray", ["fasm2frames", "xc7frames2bit"]
    def run(self, ctx):
        t = ctx.target; db = _p(t["db_root"])
        ctx.sh(["fasm2frames", "--db-root", _p(t["db_root"]), "--part", t["part"], ctx.art["fasm"], ctx.work / "out.frames"], "fasm2frames")
        ctx.sh(["xc7frames2bit", "--part_file", f"{db}/{t['part']}/part.yaml", "--part_name", t["part"],
                "--frm_file", ctx.work / "out.frames", "--output_file", ctx.work / "out.bit"], "frames2bit")
        ctx.art["bit"] = ctx.work / "out.bit"

@backend
class Prjuray(Backend):
    """Project U-Ray (UltraScale/US+ bit database). Placeholder: no routed-DCP->FASM exporter and no confirmed Zynq US+ coverage yet."""
    stage, name = "bitgen", "prjuray"
    def supports(self, target):
        return "prjuray has a partial UltraScale+ database but no DCP/phys->FASM converter or verified xczu7ev/xck26 coverage; implement here when available"
    def run(self, ctx): raise SystemExit(self.supports(ctx.target))
