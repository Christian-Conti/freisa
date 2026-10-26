# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Optional Vivado steps: synthesis, netlist linking, placement, routing and bitstream (PL only, around an open
#            core, or with a Zynq PS block design). Every step reads and writes the Interchange files like the open ones.
# Module   : vivado.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import json
from ..core import Backend, backend, find_vivado
from .. import ifx
from .. import vivado as V

class _Viv(Backend):
    metric = "wns"
    vendor = "vivado"
    def supports(self, target):
        return None if find_vivado() else "Vivado not found (PATH, $VIVADO, or /eda/Xilinx/Vivado/<version>/bin/vivado)"
    def score(self, ctx):  # explore: lower is better -> maximise WNS
        w = V.wns(ctx.work / f"{self.stage}_timing.rpt")
        return -w if w is not None else 0

@backend
class VivadoSynth(_Viv):
    """synth_design on the RTL: maps URAM/BRAM/LUTRAM/SRL/DSP/carry natively."""
    stage, name = "synth", "vivado"
    def run(self, ctx):
        c = ctx.cfg
        defines = {**ctx.art.get("defines", {}), **c.get("defines", {})}
        incs = " ".join(f"{{{d}}}" for d in ctx.art.get("incdirs", []))
        gens = " ".join(f"-generic {k}={v}" for k, v in c.get("params", {}).items())
        ooc = "-mode out_of_context" if V.ooc(ctx) else ""
        out = ("report_utilization -file synth_util.rpt\nreport_timing_summary -file synth_timing.rpt\n"
               "write_checkpoint -force synth.dcp\nwrite_edif -force synth.edf\n")
        read = [f"read_{'vhdl -vhdl2008' if ft == 'vhdlSource' else 'verilog -sv' if ft == 'systemVerilogSource' else 'verilog'} {{{f}}}"
                for f, ft in ctx.art["rtl"]]
        args = (f"{ooc} {' '.join(f'-verilog_define {k}={v}' for k, v in defines.items())} {gens} "
                f"{c.get('vivado_synth_args', '-flatten_hierarchy rebuilt')}" + (f" -include_dirs [list {incs}]" if incs else ""))
        body = "\n".join(read) + f"\n{V.xdc(ctx)}synth_design -top {c['top']} -part {ctx.target['part']} {args}\n" + out
        V.run(ctx, body, "viv_synth")
        ctx.art["edif"] = ctx.work / "synth.edf"
        ifx.from_dcp(ctx, ctx.work / "synth.dcp", "synth", vivado=True)  # exchange format: .netlist + .phys

@backend
class VivadoLink(_Viv):
    """Yosys/other EDIF -> checkpoint with constraints (use after `synth: yosys`)."""
    stage, name = "netlist", "vivado_link"
    def run(self, ctx):
        mode = "-mode out_of_context " if V.ooc(ctx) else ""
        V.run(ctx, f"read_edif {{{V.edif_for_vivado(ctx, ctx.art['edif'])}}}\nlink_design {mode}-part {ctx.target['part']} "
              f"-top {ctx.cfg['top']}\n{V.xdc(ctx)}write_checkpoint -force linked.dcp\nwrite_edif -force linked.edf\n", "viv_link")
        ifx.from_dcp(ctx, ctx.work / "linked.dcp", "linked", vivado=True)

@backend
class VivadoPlace(_Viv):
    """opt_design + place_design (+ optional phys_opt_design)."""
    stage, name = "place", "vivado"
    def run(self, ctx):
        c = ctx.cfg
        po = "phys_opt_design\n" if c.get("phys_opt", False) else ""
        if "phys" in ctx.art:  # Interchange design from the previous step
            load = f"open_checkpoint {{{ifx.to_dcp(ctx, 'place_in', ooc=V.ooc(ctx))}}}\n"
        else:                  # xc7 path: nothing placed yet, start from the synthesized EDIF
            load = (f"read_edif {{{V.edif_for_vivado(ctx, ctx.art['edif'])}}}\nlink_design {'-mode out_of_context ' if V.ooc(ctx) else ''}"
                    f"-part {ctx.target['part']} -top {c['top']}\n")
        V.run(ctx, f"{load}{V.xdc(ctx)}opt_design -directive {c.get('opt_directive', 'Default')}\n"
              f"place_design -directive {c.get('place_directive', 'Default')}\n{po}"
              "report_timing_summary -file place_timing.rpt\nreport_utilization -file place_util.rpt\n"
              "report_clock_utilization -file place_clock_util.rpt\nreport_design_analysis -congestion -file place_congestion.rpt\n"
              "write_checkpoint -force placed.dcp\nwrite_edif -force placed.edf\n", "viv_place")
        ifx.from_dcp(ctx, ctx.work / "placed.dcp", "placed", vivado=True)

@backend
class VivadoRoute(_Viv):
    """route_design (+ optional post-route phys_opt_design)."""
    stage, name = "route", "vivado"
    def run(self, ctx):
        c = ctx.cfg
        po = f"phys_opt_design -directive {c.get('post_route_phys_opt', 'Default')}\n" if c.get("post_route_phys_opt") else ""
        if "phys" not in ctx.art: raise SystemExit("vivado route: no placed design (the place step did not place: use place: vivado)")
        V.run(ctx, f"open_checkpoint {{{ifx.to_dcp(ctx, 'route_in', ooc=V.ooc(ctx))}}}\n{V.xdc(ctx)}"
              f"route_design -directive {c.get('route_directive', 'Default')}\n{po}"
              "report_timing_summary -max_paths 20 -file route_timing.rpt\nreport_utilization -file route_util.rpt\n"
              "report_route_status -file route_status.rpt\nreport_drc -file route_drc.rpt\nreport_power -file route_power.rpt\n"
              "report_methodology -file route_methodology.rpt\nwrite_checkpoint -force routed.dcp\nwrite_edif -force routed.edf\n", "viv_route")
        ifx.from_dcp(ctx, ctx.work / "routed.dcp", "routed", vivado=True)

@backend
class VivadoBitgen(_Viv):
    """write_bitstream from a routed, in-context checkpoint (PL only; out-of-context checkpoints are refused by Vivado, DRC HDOOC-3)."""
    stage, name = "bitgen", "vivado"
    def run(self, ctx):
        if "bd_tcl" in ctx.cfg:
            raise SystemExit("design has a block design (bd_tcl, e.g. with the PS): set `bitgen: vivado_ps` in the project file to get .bit + .hwh + .xsa")
        if V.ooc(ctx):
            raise SystemExit("out-of-context design (no `xdc:` pin constraints): Vivado cannot write a bitstream for it; add pin constraints and run place/route with Vivado (project file)")
        if "phys" not in ctx.art: raise SystemExit("vivado bitgen: no placed and routed design (route with vivado or rwroute)")
        V.run(ctx, f"open_checkpoint {{{ifx.to_dcp(ctx, 'bitgen_in', ooc=False)}}}\n{V.xdc(ctx)}write_bitstream -force out.bit\n", "viv_bitgen")
        ctx.art["bit"] = ctx.work / "out.bit"

@backend
class VivadoWrap(_Viv):
    """Bitstream for a design implemented by the open tools (out of context, no pins): Vivado synthesizes only the I/O wrapper
    (`wrap:` in the design: top, rtl, cell), inserts the open placed-and-routed checkpoint into `cell` with its placement locked,
    places and routes the wrapper (clock buffer, pins) and writes the bitstream. The open routing of the core is kept."""
    stage, name = "bitgen", "vivado_wrap"
    def run(self, ctx):
        w = ctx.cfg.get("wrap") or {}
        if not {"top", "rtl", "cell"} <= set(w):
            raise SystemExit("vivado_wrap: set `wrap: {top: <wrapper module>, rtl: [<wrapper files>], cell: <core instance>}` in the design")
        # black-box stub of the core, from the ports of the Yosys netlist
        core = json.loads(open(ctx.art["json"]).read())["modules"][ctx.cfg["top"]]["ports"]
        def decl(n, p):
            rng = f"[{len(p['bits']) - 1}:0] " if len(p["bits"]) > 1 else ""
            return ("input " if p["direction"] == "input" else "output ") + rng + n
        (ctx.work / "core_stub.v").write_text(f"(* black_box *) module {ctx.cfg['top']}({', '.join(decl(n, p) for n, p in core.items())}); endmodule\n")
        rtl = "".join(f"read_verilog {{{ctx.root / f}}}\n" for f in w["rtl"]) + "read_verilog core_stub.v\n"
        V.run(ctx, f"{rtl}{V.xdc(ctx)}synth_design -top {w['top']} -part {ctx.target['part']}\n"
              f"read_checkpoint -cell {w['cell']} {{{ifx.to_dcp(ctx, 'core')}}}\nlock_design -level placement [get_cells {w['cell']}]\n"
              # freeze every net the open router already routed (before routing only those are routed): Vivado routes the wrapper
              "set fixed [get_nets -quiet -hier -filter {ROUTE_STATUS == ROUTED}]\n"
              "if {[llength $fixed]} { set_property IS_ROUTE_FIXED 1 $fixed }\n"
              "puts \"FREISA: [llength $fixed] nets keep the open routing\"\n"
              "report_route_status -file wrap_pre_route_status.rpt\nplace_design\nroute_design\n"
              "report_route_status -file wrap_route_status.rpt\nreport_timing_summary -file wrap_timing.rpt\nreport_utilization -file wrap_util.rpt\n"
              "write_checkpoint -force wrapped.dcp\nwrite_bitstream -force out.bit\n", "viv_wrap")
        ctx.art.update(dcp=ctx.work / "wrapped.dcp", bit=ctx.work / "out.bit")

@backend
class VivadoPs(_Viv):
    """Project/BD flow for boards with a Zynq PS: sources + the design's block-design Tcl -> synth, impl, bitstream.
    Produces out.bit, out.hwh (hardware handoff) and out.xsa.  Takes the RTL, not an open-flow checkpoint, so it covers
    the whole synth..bitgen chain (select `bitgen: vivado_ps` in the project file)."""
    stage, name = "bitgen", "vivado_ps"
    def run(self, ctx):
        c = ctx.cfg
        if "bd_tcl" not in c: raise SystemExit("vivado_ps: set `bd_tcl:` (and `bd_name:`) in the design file")
        files = "\n".join(f"add_files -norecurse {{{f}}}" for f, _ in ctx.art["rtl"])
        xdc = "".join(f"add_files -fileset constrs_1 -norecurse {{{ctx.root / x}}}\n" for x in c.get("xdc", []))
        bd, jobs = c.get("bd_name", "design_1"), int(c.get("vivado_jobs", 8))
        V.run(ctx, f"create_project -force proj proj -part {ctx.target['part']}\n"
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
