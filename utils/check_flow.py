#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Checks that every tool selected for a design/board in the project file is available; if not it stops (exit 1) and suggests how to change the command.
# Module   : check_flow.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

"""Usage: check_flow.py -d <design> -t <board> [--from S] [--to S] [--upload]

Checks the tool chosen in the project file for every step of the run on this board. Exit 0 if all can run; otherwise exit 1 with,
for each blocked step, why, how to install the tool, and the tools that do work there (as the line to put in the project file)."""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from freisa import core, resolve, term as T

HINTS = [  # (substring of the reason, how to fix it)
    ("DREAMPlaceFPGA", "make install-dreamplace"),
    ("nextpnr-fpga_interchange", "make install-interchange"),
    ("python-fpga-interchange", "make install-interchange"),
    ("prjuray not installed", "make install-prjuray"),
    ("fasm2frames", "make install-xc7"),
    ("xc7frames2bit", "make install-xc7"),
    ("Vivado not found", "install Vivado or point to it: VIVADO=/path/to/vivado, or VIVADO_ROOT=/path/to/vivado (VIVADO_VERSION=2024.1)"),
    ("openFPGALoader", "put openFPGALoader on PATH (OSS CAD Suite)"),
    ("yosys", "put Yosys on PATH (OSS CAD Suite)"),
    ("java", "install a JRE (RapidWright needs Java 11+)"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--design", default="blinky"); ap.add_argument("-t", "--target", default="xc7z020")
    ap.add_argument("--from", dest="frm", default=core.STAGES[0]); ap.add_argument("--to", default=core.STAGES[-1])
    ap.add_argument("--upload", action="store_true", help="check the upload step only")
    ap.add_argument("--tool", help="upload tool overriding the project file")
    ap.add_argument("--step", action="append", default=[], metavar="STAGE=TOOL", help="tool of one step, overriding the project file")
    a = ap.parse_args()
    r = resolve.Resolved(a.design, a.target, dict(s.split("=", 1) for s in a.step))
    if a.tool: r.sel["upload"] = core.pick("upload", a.tool, r.target); r.steps["upload"] = a.tool
    run = ["upload"] if a.upload else core.STAGES[core.STAGES.index(a.frm):core.STAGES.index(a.to) + 1]
    print(f"{T.ARROW} {T.bold('check'.ljust(8))} {T.cyan(r.name)} → {T.cyan(a.target)}  {T.dim('tools from ' + __import__('os').path.relpath(r.dpath))}")
    bad = r.problems(run)
    for s in run:
        b = r.sel[s]; why = next((w for st, _, w in bad if st == s), None)
        chosen = r.steps.get(s, "auto")
        tag = T.dim(" auto") if chosen == "auto" else T.dim(f" {chosen}/explore") if chosen in ("all", "all_open") else ""
        lb = b.label()
        print(f"    {s:8} {lb}{tag}{' ' * max(1, 26 - len(lb) - len(T.plain(tag)))}{T.OK if not why else T.FAIL + ' ' + T.red('cannot run')}")
    if not bad:
        print(f"  {T.OK} {T.green('all tools available')}"); return
    dfile = __import__("os").path.relpath(r.dpath)
    print(f"\n{T.FAIL} {T.red(T.bold('cannot run'))} {T.dim('— change the tools in')} {dfile} {T.dim('under')} boards: {{{a.target}: ...}} {T.dim('(this board) or')} steps: {T.dim('(every board)')}")
    for s, n, why in bad:
        print(f"  {T.bold(s)}: {T.red(n)} {T.dim('—')} {why}")
        h = next((h for k, h in HINTS if k in why), None)
        if h: print(f"      {T.yellow('install')}    {h}")
        alt = [x for x in core.REGISTRY[s] if x != n and core.REGISTRY[s][x]().supports(r.target) is None]
        viv_ok = all(x in core.REGISTRY[st] and core.REGISTRY[st][x]().supports(r.target) is None
                     for st, x in (("synth", "vivado"), ("place", "vivado"), ("route", "vivado"), ("bitgen", "vivado")))
        if s == "bitgen" and viv_ok and n not in ("vivado_wrap", "open_io"):
            print(f"      {T.yellow('option 1')}   open tools for everything, Vivado only writes the file ({dfile}):")
            print("                 " + T.cyan(f"boards: {{{a.target}: {{bitgen: open_io}}}}") + T.dim("  + pin constraints in the design (xdc:)"))
            print(f"      {T.yellow('option 2')}   everything in Vivado:")
            print("                 " + T.cyan(f"boards: {{{a.target}: {{synth: vivado, netlist: none, place: vivado, route: vivado, bitgen: vivado}}}}"))
            if not r.flow.get("xdc") and not (r.flow.get("per_target", {}).get(f"{a.target}@vivado") or {}).get("xdc"): print("                 " + T.dim(f"and give the design pin constraints (per_target: {{{a.target}@vivado: {{xdc: [...]}}}})"))
        elif alt:
            print(f"      {T.yellow('available')}  " + T.dim(" | ").join(T.cyan(f"{s}: {x}") for x in alt))
        if s == "bitgen" and len(run) > 1:
            print(f"      {T.yellow('option 3')}   no bitstream, open tools up to the routed checkpoint: " + T.cyan(f"TO={run[run.index(s) - 1]}"))
    sys.exit(1)

main()
