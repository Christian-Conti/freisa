# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Open 7-series (xc7) steps on the FPGA Interchange format: Yosys JSON -> .netlist (python-fpga-interchange),
#            place and route with nextpnr-fpga_interchange (.netlist -> .phys), FASM from .netlist + .phys
#            (python-fpga-interchange) -> bitstream with prjxray. Also the Project U-Ray placeholder for UltraScale+.
# Module   : open_pnr.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import os, pathlib, re
from ..core import Backend, backend
from .. import ifx

def _p(x):  # board paths: ~ and flow-root relative
    return str(pathlib.Path(os.path.expanduser(x)) if os.path.isabs(os.path.expanduser(x)) else pathlib.Path(__file__).parents[2] / x)

class _Xc7(Backend):
    def supports(self, target):
        if target.get("family") != "xc7": return "7-series (xc7) only"
        if ifx.if_python() is None: return "python-fpga-interchange not installed (make install-interchange)"
        return super().supports(target)

@backend
class YosysJsonIf(_Xc7):
    """Yosys JSON -> Interchange logical netlist (python-fpga-interchange yosys_json)."""
    stage, name = "netlist", "yosys_json_if"
    def run(self, ctx):
        out = ctx.work / "design.netlist"
        ifx.pyif(ctx, "yosys_json", ["--schema_dir", ifx.SCHEMA, "--device", ifx.device(ctx), "--top", ctx.cfg["top"],
                                     ctx.art["json"], out], "yosys_json_if")
        ctx.art["netlist"] = out; ctx.art.pop("phys", None)

@backend
class PlaceSkip(_Xc7):
    """nextpnr-fpga_interchange places and routes in one run (route step)."""
    stage, name = "place", "in_route"
    def run(self, ctx): pass

@backend
class NextpnrInterchange(_Xc7):
    """nextpnr-fpga_interchange: .netlist (+ pin XDC) -> placed and routed .phys."""
    stage, name, tools = "route", "nextpnr_interchange", ["nextpnr-fpga_interchange"]
    def run(self, ctx):
        xdc = ctx.work / "pins.xdc"
        xdc.write_text("".join((ctx.root / x).read_text() + "\n" for x in ctx.cfg.get("xdc", [])))
        out = ctx.work / "routed.phys"
        ctx.sh(["nextpnr-fpga_interchange", "--chipdb", ifx.chipdb(ctx), "--xdc", xdc, "--netlist", ctx.art["netlist"],
                "--phys", out, "--package", ctx.target["package"]], "nextpnr_interchange", cwd=ctx.work)
        ctx.art["phys"] = out

@backend
class NextpnrXilinx(_Xc7):
    """nextpnr-xilinx: place and route with a chip database built from prjxray-db (open documentation), alternative to
    nextpnr_interchange (whose database comes from the RapidWright/AMD device description). Exception to the Interchange
    contract: it reads the Yosys JSON and writes FASM directly (no .phys); prjxray then uses that FASM."""
    stage, name, tools = "route", "nextpnr_xilinx", ["nextpnr-xilinx"]
    def supports(self, target):
        db = pathlib.Path(__file__).parents[2] / "install" / "share" / "nextpnr-xilinx" / f"{target.get('part')}.bin"
        if target.get("family") != "xc7": return "7-series (xc7) only"
        return super(_Xc7, self).supports(target) or (None if db.exists() else f"no nextpnr-xilinx database for {target.get('part')} (make install-xc7)")
    def run(self, ctx):
        db = pathlib.Path(__file__).parents[2] / "install" / "share" / "nextpnr-xilinx" / f"{ctx.target['part']}.bin"
        xdc = ctx.work / "pins.xdc"
        xdc.write_text("".join((ctx.root / x).read_text() + "\n" for x in ctx.cfg.get("xdc", [])))
        ctx.sh(["nextpnr-xilinx", "--chipdb", db, "--xdc", xdc, "--json", ctx.art["json"], "--fasm", ctx.work / "out.fasm"], "nextpnr_xilinx", cwd=ctx.work)
        ctx.art["fasm"] = ctx.work / "out.fasm"; ctx.art.pop("phys", None)

@backend
class Prjxray(_Xc7):
    """.netlist + .phys -> FASM (python-fpga-interchange) -> frames -> .bit (prjxray); after nextpnr_xilinx its FASM is used."""
    stage, name, tools = "bitgen", "prjxray", ["fasm2frames", "xc7frames2bit"]
    def run(self, ctx):
        t = ctx.target; db = _p(t["db_root"])
        if "phys" in ctx.art:  # Interchange design -> FASM; after nextpnr_xilinx the FASM is already there
            ifx.pyif(ctx, "fasm_generator", ["--schema_dir", ifx.SCHEMA, "--family", "xc7", ifx.device(ctx), ctx.art["netlist"],
                                             ctx.art["phys"], ctx.work / "out.fasm"], "fasm_generator")
        ctx.sh(["fasm2frames", "--db-root", db, "--part", t["part"], ctx.work / "out.fasm", ctx.work / "out.frames"], "fasm2frames")
        ctx.sh(["xc7frames2bit", "--part_file", f"{db}/{t['part']}/part.yaml", "--part_name", t["part"],
                "--frm_file", ctx.work / "out.frames", "--output_file", ctx.work / "out.bit"], "frames2bit")
        ctx.art.update(fasm=ctx.work / "out.fasm", bit=ctx.work / "out.bit")

PRJURAY_DB = pathlib.Path(__file__).parents[2] / "third_party" / "prjuray-db"

def prjuray_parts():
    """Parts with a complete prjuray-db description (tile grid), e.g. zynqusp/xczu3eg-sbva484-1-e."""
    return sorted(str(p.parent.relative_to(PRJURAY_DB)) for p in PRJURAY_DB.glob("*/*/tilegrid.json"))

@backend
class Prjuray(Backend):
    """Project U-Ray: FASM -> UltraScale+ bitstream (prjuray-fasm2bit, database prjuray-db). Needs the part in prjuray-db
    and a FASM of the design; the FASM generator from Interchange .phys for UltraScale+ does not exist yet."""
    stage, name, tools = "bitgen", "prjuray", ["prjuray-fasm2bit", "xcframes2bit"]
    def _db(self, target):
        dev = lambda part: re.sub(r"-[0-9a-z]+-[a-z]$", "", part.lower())  # tile grid depends on device+package, not speed/temperature
        return next((p for p in prjuray_parts() if dev(p.split("/")[-1]) == dev(target["part"])), None)
    def supports(self, target):
        if target.get("family") not in ("xczu", "xcvu", "xcku"): return "UltraScale+ only"
        if not PRJURAY_DB.exists(): return "prjuray not installed (make install-prjuray)"
        if self._db(target) is None:
            return f"prjuray-db has no tile grid for {target['part']} (covered: {', '.join(p.split('/')[1] for p in prjuray_parts())})"
        return super().supports(target) or "no Interchange (.phys) -> FASM generator for UltraScale+ yet"
    def run(self, ctx):
        db = self._db(ctx.target)
        if "fasm" not in ctx.art: raise SystemExit(self.supports(ctx.target))
        ctx.sh(["prjuray-fasm2bit", "--db-root", PRJURAY_DB / db.split("/")[0], "--part", ctx.target["part"], "--architecture",
                "UltraScalePlus", "--frames-file", ctx.work / "out.frm", "--bits-file", ctx.work / "out.bits",  # explicit files:
                ctx.art["fasm"], ctx.work / "out.bit"], "prjuray_fasm2bit")                                     # its tempfiles break on py3
        ctx.art["bit"] = ctx.work / "out.bit"
