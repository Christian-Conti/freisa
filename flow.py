#!/usr/bin/env python3
"""RTL -> bitstream (any design: designs/*.yml, any board: targets/*.yml), modular. `flow.py doctor [-t T]` shows what each stage can do; `flow.py run -t T [--from S] [--to S]`."""
import argparse, json, pathlib, sys
from freisa import core, ui

HERE = pathlib.Path(__file__).parent

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "doctor"])
    ap.add_argument("-t", "--target", default="zcu106")
    ap.add_argument("-d", "--design", default="amaretto", help="designs/<name>.yml or a path")
    ap.add_argument("-p", "--profile", default=None, help="stage preset from defaults.yml: open|vivado|vivado_ps|yosys_vivado")
    ap.add_argument("--from", dest="frm", default=core.STAGES[0])
    ap.add_argument("--to", default=core.STAGES[-1])
    ap.add_argument("-j", "--jobs", type=int, default=4, help="parallel explore variants")
    ap.add_argument("-o", "--out", default=HERE / "build")
    a = ap.parse_args()
    core.load_backends()
    dpath = pathlib.Path(a.design) if a.design.endswith(".yml") else HERE / "designs" / f"{a.design}.yml"
    flow = {**core.load_yaml(HERE / "defaults.yml"), **core.load_yaml(dpath)}
    flow["stages"] = {**core.load_yaml(HERE / "defaults.yml")["stages"], **flow["stages"]} if "stages" in flow else flow["stages"]
    name = dpath.stem
    target = core.load_yaml(HERE / "targets" / f"{a.target}.yml")
    ctx = core.Ctx(target, flow, pathlib.Path(a.out) / name / a.target, (dpath.parent / flow["repo"]).resolve())
    sel = {s: core.pick(s, flow, target, a.profile) for s in core.STAGES}
    if a.cmd == "doctor":
        for s in core.STAGES:
            for n, cls in core.REGISTRY[s].items():
                why = cls().supports(target)
                print(f"{s:8} {n:16} {'*' if n == sel[s].name else ' '} {'ok' if not why else 'NO: ' + why}")
        return
    art = ctx.work / "artifacts.json"
    if a.frm != core.STAGES[0] and art.exists():  # resume: reload what earlier stages produced
        ctx.art = {k: ([tuple(x) for x in v] if k == "rtl" else pathlib.Path(v)) for k, v in json.loads(art.read_text()).items()}
    run = core.STAGES[core.STAGES.index(a.frm):core.STAGES.index(a.to) + 1]
    # preflight: fail before hours of work if a middle stage cannot run; a missing last step (e.g. Vivado bitgen) just ends the run early
    for s in run:
        why = sel[s].supports(target)
        if why and s == run[-1] and len(run) > 1: print(f"note: stopping before {s}/{sel[s].name}: {why}"); run = run[:-1]
        elif why: sys.exit(f"stage {s}/{sel[s].name} unavailable: {why}")
    mon = ui.Monitor(run, ctx, ctx.work / "flow.log"); mon.start()
    for s in run:
        b = sel[s]
        mon.begin(s, b.name)
        try:
            core.explore(s, b, ctx, flow["explore"][s], a.jobs) if s in flow.get("explore", {}) else b.run(ctx)
        except SystemExit as e:
            mon.finish(False); raise
        if s == "sources": core.apply_patches(ctx)
        art.write_text(json.dumps({k: v if k == "rtl" else str(v) for k, v in ctx.art.items()}))
        try: sc = b.score(ctx) if s in ("synth", "place", "route") else None
        except Exception: sc = None
        mon.end(s, f"score {sc}" if sc else "")
    mon.finish()
    mon.say("artifacts: " + ", ".join(f"{k}={v}" for k, v in ctx.art.items() if k != "rtl"))

main()
