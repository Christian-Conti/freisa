#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Command-line entry point: run, doctor and upload.
# Module   : flow.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import argparse, json, os, pathlib, sys
from freisa import core, ui, report, resolve, term

HERE = pathlib.Path(__file__).parent

def doctor(r, board):
    """Every tool of every step for one board: available or not (and why); ◀ marks the one the project file selects."""
    print(term.banner(f"FREISA doctor  {r.name} → {board}  ({r.target.get('part')})", "every tool of every step; ◀ = chosen by the project file"))
    for s in core.STAGES + ["upload"]:
        for n, cls in core.REGISTRY[s].items():
            why = cls().supports(r.target)
            sel = n == r.sel[s].name; lb = cls.label()
            print(f"  {s:8} {(term.bold(lb) if sel else lb) + ' ' * max(1, 26 - len(lb))} {(term.orange('◀ selected') if sel else '          ')} {term.green('yes') if not why else term.red('no')}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "doctor", "upload"])
    ap.add_argument("-t", "--target", default="xc7z020")
    ap.add_argument("-d", "--design", default="blinky", help="designs/<name>.yml or a path")
    ap.add_argument("--tool", default=None, help="upload: openfpgaloader | vivado (default: `upload` in the project file)")
    ap.add_argument("--bit", help="upload: bitstream (default: build/<design>/<board>/out.bit)")
    ap.add_argument("--from", dest="frm", default=core.STAGES[0])
    ap.add_argument("--to", default=core.STAGES[-1])
    ap.add_argument("-j", "--jobs", type=int, default=4, help="parallel explore variants")
    ap.add_argument("-o", "--out", default=HERE / "build")
    ap.add_argument("--all-boards", action="store_true", help="doctor: every board in targets/")
    a = ap.parse_args()
    if a.cmd == "doctor" and a.all_boards:  # one table per board
        for tf in sorted((HERE / "targets").glob("*.yml")):
            doctor(resolve.Resolved(a.design, tf.stem), tf.stem); print()
        return
    r = resolve.Resolved(a.design, a.target)
    flow, target, name = r.flow, r.target, r.name
    ctx = core.Ctx(target, flow, pathlib.Path(a.out) / name / a.target, r.root)
    if a.cmd == "upload":
        b = core.pick("upload", a.tool, target) if a.tool else r.sel["upload"]
        why = b.supports(target)
        if why: sys.exit(term.error(f"upload/{b.name} unavailable: {why}"))
        ctx.art["bit"] = pathlib.Path(a.bit) if a.bit else ctx.work / "out.bit"
        if not ctx.art["bit"].exists(): sys.exit(term.error(f"no bitstream at {os.path.relpath(ctx.art['bit'])}: run the flow first or pass BIT="))
        print(f"{term.ARROW} {term.bold('upload')}   {term.cyan(b.label())}  {term.dim(os.path.relpath(ctx.art['bit']))}")
        b.run(ctx); print(f"  {term.OK} {term.green('programmed')} {os.path.relpath(ctx.art['bit'])} {term.dim('with ' + b.label())}"); return
    sel = r.sel
    if a.cmd == "doctor":
        doctor(r, a.target); return
    art = ctx.work / "artifacts.json"
    if a.frm != core.STAGES[0] and art.exists():  # resume: reload what earlier stages produced
        ctx.art = {k: ([tuple(x) for x in v] if k == "rtl" else pathlib.Path(v)) for k, v in json.loads(art.read_text()).items()}
    flow["explore"] = {**flow.get("explore", {}), **{s: "all" for s in r.explore_all}}  # `all` in steps = explore every tool
    run = core.STAGES[core.STAGES.index(a.frm):core.STAGES.index(a.to) + 1]
    # preflight: fail before hours of work if a middle stage cannot run; a missing last step (e.g. Vivado bitgen) just ends the run early
    if run[-1] == "bitgen" and sel["bitgen"].name == "vivado" and flow.get("ooc", not flow.get("xdc")) and len(run) > 1:
        print(term.note("stopping before bitgen: out-of-context design (no `xdc:` pins), Vivado cannot write its bitstream")); run = run[:-1]
    for s in run:
        why = sel[s].supports(target)
        if why and s == run[-1] and len(run) > 1: print(term.note(f"stopping before {s}/{sel[s].label()}: {why}")); run = run[:-1]
        elif why: sys.exit(term.error(f"stage {s}/{sel[s].label()} unavailable: {why}"))
    mon = ui.Monitor(run, ctx, ctx.work / "flow.log"); mon.start(); rep = report.Reporter(ctx)
    for s in run:
        b = sel[s]
        mon.begin(s, b.label())
        try:
            core.explore(s, b, ctx, flow["explore"][s], a.jobs) if s in flow.get("explore", {}) else b.run(ctx)
        except SystemExit as e:
            mon.finish(False); raise
        if s == "sources": core.apply_patches(ctx)
        art.write_text(json.dumps({k: v if k == "rtl" else str(v) for k, v in ctx.art.items()}))
        best = ctx.work / f"{s}_best.json"
        try: sc = json.loads(best.read_text())["score"] if s in flow.get("explore", {}) else (b.score(ctx) if s in ("synth", "place", "route") else None)
        except Exception: sc = None
        mon.end(s, f"score {sc}" if sc else "", rep)
    rdir = os.path.relpath(rep.finalize())
    mon.say(f"\n{term.bold('results')}  {term.dim(os.path.relpath(ctx.work))}")
    for k, v in ctx.art.items():
        if k != "rtl": mon.say(f"  {term.orange(k.ljust(6))} {os.path.relpath(v)}")
    mon.say(f"  {term.orange('report'.ljust(6))} {rdir}/summary.md  {term.dim('(+ reports/, logs/, artifacts/)')}")
    mon.finish()

main()
