# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Optional Vivado backends for synthesis, placement, routing and bitstream.
# Module   : vivado_back.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import os, re
from ..core import Backend, backend, find_vivado

def _run(ctx, body, log):
    t = ctx.work / f"{log}.tcl"
    t.write_text(body)
    ctx.sh([find_vivado(), "-mode", "batch", "-nojournal", "-log", f"{log}.vivado.log", "-source", t.name], log, cwd=ctx.work)

def _wns(rpt):
    """Worst negative slack from a report_timing_summary file (None if absent)."""
    try:
        m = re.search(r"WNS\(ns\).*?\n.*?\n\s*(-?[0-9.]+)", rpt.read_text(), re.S)
        return float(m.group(1)) if m else None
    except OSError:
        return None

class _Viv(Backend):
    metric = "wns"
    def supports(self, target):
        return None if find_vivado() else "Vivado not found (PATH, $VIVADO, or /eda/Xilinx/Vivado/<version>/bin/vivado)"
    def score(self, ctx):  # explore: lower is better -> maximise WNS
        w = _wns(ctx.work / f"{self.stage}_timing.rpt")
        return -w if w is not None else 0

@backend
class VivadoSynth(_Viv):
    """synth_design on the RTL: maps URAM/BRAM/LUTRAM/SRL/DSP/carry natively."""
    stage, name = "synth", "vivado"
    def run(self, ctx):
        c = ctx.cfg
        read = []
        for f, ft in ctx.art["rtl"]:
            read.append(f"read_{'vhdl -vhdl2008' if ft == 'vhdlSource' else 'verilog -sv' if ft == 'systemVerilogSource' else 'verilog'} {{{f}}}")
        defs = " ".join(f"-verilog_define {k}={v}" for k, v in c.get("defines", {}).items())
        gens = " ".join(f"-generic {k}={v}" for k, v in c.get("params", {}).items())
        xdc = "".join(f"read_xdc {{{ctx.root / x}}}\n" for x in c.get("xdc", []))
        ooc = "-mode out_of_context" if c.get("ooc", not c.get("xdc")) else ""  # no pin constraints -> out-of-context
        _run(ctx, "\n".join(read) + f"\n{xdc}synth_design -top {c['top']} -part {ctx.target['part']} {ooc} {defs} {gens} {c.get('vivado_synth_args', '-flatten_hierarchy rebuilt')}\n"
             f"report_utilization -file synth_util.rpt\nreport_timing_summary -file synth_timing.rpt\nwrite_checkpoint -force synth.dcp\nwrite_edif -force synth.edf\n", "viv_synth")
        ctx.art["dcp"], ctx.art["edif"] = ctx.work / "synth.dcp", ctx.work / "synth.edf"

@backend
class VivadoLink(_Viv):
    """Yosys/other EDIF -> checkpoint with constraints (use after `synth: yosys`)."""
    stage, name = "netlist", "vivado_link"
    def run(self, ctx):
        xdc = "".join(f"read_xdc {{{ctx.root / x}}}\n" for x in ctx.cfg.get("xdc", []))
        _run(ctx, f"read_edif {{{ctx.art['edif']}}}\nlink_design -mode out_of_context -part {ctx.target['part']} -top {ctx.cfg['top']}\n{xdc}write_checkpoint -force linked.dcp\n", "viv_link")
        ctx.art["dcp"] = ctx.work / "linked.dcp"

@backend
class VivadoPlace(_Viv):
    """opt_design + place_design (+ optional phys_opt_design)."""
    stage, name = "place", "vivado"
    def run(self, ctx):
        c = ctx.cfg
        po = "phys_opt_design\n" if c.get("phys_opt", False) else ""
        _run(ctx, f"open_checkpoint {{{ctx.art['dcp']}}}\nopt_design -directive {c.get('opt_directive', 'Default')}\n"
             f"place_design -directive {c.get('place_directive', 'Default')}\n{po}report_timing_summary -file place_timing.rpt\nreport_utilization -file place_util.rpt\nreport_clock_utilization -file place_clock_util.rpt\nreport_congestion -file place_congestion.rpt\nwrite_checkpoint -force placed.dcp\n", "viv_place")
        ctx.art["dcp"] = ctx.work / "placed.dcp"

@backend
class VivadoRoute(_Viv):
    """route_design (+ optional post-route phys_opt_design)."""
    stage, name = "route", "vivado"
    def run(self, ctx):
        c = ctx.cfg
        po = f"phys_opt_design -directive {c.get('post_route_phys_opt', 'Default')}\n" if c.get("post_route_phys_opt") else ""
        _run(ctx, f"open_checkpoint {{{ctx.art['dcp']}}}\nroute_design -directive {c.get('route_directive', 'Default')}\n{po}"
             "report_timing_summary -max_paths 20 -file route_timing.rpt\nreport_utilization -file route_util.rpt\nreport_route_status -file route_status.rpt\nreport_drc -file route_drc.rpt\nreport_power -file route_power.rpt\nreport_methodology -file route_methodology.rpt\nwrite_checkpoint -force routed.dcp\n", "viv_route")
        ctx.art["dcp"] = ctx.work / "routed.dcp"

@backend
class VivadoBitgen(_Viv):
    """write_bitstream from a routed checkpoint (PL only: no PS/BD)."""
    stage, name = "bitgen", "vivado"
    def supports(self, target):
        return super().supports(target) or ("PS present: use `bitgen: vivado_ps` (block design, produces .bit + .hwh + .xsa)" if target.get("needs_ps") else None)
    def run(self, ctx):
        _run(ctx, f"open_checkpoint {{{ctx.art['dcp']}}}\nwrite_bitstream -force out.bit\n", "viv_bitgen")
        ctx.art["bit"] = ctx.work / "out.bit"

@backend
class VivadoPs(_Viv):
    """Project/BD flow for boards with a Zynq PS: sources + the design's block-design Tcl -> synth, impl, bitstream.
    Produces out.bit, out.hwh (hardware handoff) and out.xsa.  Takes the RTL, not an open-flow checkpoint, so it covers
    the whole synth..bitgen chain (use with `PROFILE=vivado_ps`)."""
    stage, name = "bitgen", "vivado_ps"
    def supports(self, target):
        return super().supports(target)
    def run(self, ctx):
        c = ctx.cfg
        if "bd_tcl" not in c: raise SystemExit("vivado_ps: set `bd_tcl:` (and `bd_name:`) in the design file")
        files = "\n".join(f"add_files -norecurse {{{f}}}" for f, _ in ctx.art["rtl"])
        xdc = "".join(f"add_files -fileset constrs_1 -norecurse {{{ctx.root / x}}}\n" for x in c.get("xdc", []))
        bd, jobs = c.get("bd_name", "design_1"), int(c.get("vivado_jobs", 8))
        _run(ctx, f"create_project -force proj proj -part {ctx.target['part']}\n"
             + (f"set_property board_part {ctx.target['board_part']} [current_project]\n" if "board_part" in ctx.target else "")
             + f"{files}\n{xdc}source {{{ctx.root / c['bd_tcl']}}}\n"
             f"make_wrapper -files [get_files {bd}.bd] -top\nadd_files -norecurse [glob proj/proj.gen/sources_1/bd/{bd}/hdl/{bd}_wrapper.v]\n"
             f"set_property top {bd}_wrapper [current_fileset]\nupdate_compile_order -fileset sources_1\n"
             f"launch_runs impl_1 -to_step write_bitstream -jobs {jobs}\nwait_on_run impl_1\n"
             "open_run impl_1\nreport_timing_summary -file route_timing.rpt\n"
             f"file copy -force [glob proj/proj.runs/impl_1/*.bit] out.bit\n"
             f"file copy -force [glob proj/proj.gen/sources_1/bd/{bd}/hw_handoff/{bd}.hwh] out.hwh\n"
             "write_hw_platform -fixed -force -include_bit -file out.xsa\n", "viv_ps")
        ctx.art.update(bit=ctx.work / "out.bit", hwh=ctx.work / "out.hwh", xsa=ctx.work / "out.xsa")
