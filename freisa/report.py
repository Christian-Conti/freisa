"""Per-run report folder  <work>/report/ :  reports/ (area, timing, routing, power...), artifacts/ (links to every generated
file), logs/, summary.md + summary.json.  Tool reports are collected after each stage; at the end a sign-off report of the
final checkpoint is generated with Vivado if present, else a RapidWright utilization report."""
import json, os, pathlib, shutil, sys
from .core import find_vivado

PATTERNS = ["*.rpt", "stats.txt", "*_best.json", "yosys.full.log"]

class Reporter:
    def __init__(self, ctx):
        self.ctx, self.rows = ctx, []
        self.dir = ctx.work / "report"
        shutil.rmtree(self.dir, ignore_errors=True)
        for sub in ("reports", "artifacts", "logs"): (self.dir / sub).mkdir(parents=True)

    def stage(self, name, backend, dt, cpu, mem, score, t0=0):
        """Collect the reports/logs a stage left in its work dirs (explore variants included)."""
        w = self.ctx.work
        for d in [w] + sorted(w.glob(f"{name}_v*")):
            tag = "" if d == w else f"{d.name}_"
            for pat in PATTERNS:
                for f in d.glob(pat):
                    if f.stat().st_mtime < t0: continue  # left over from an earlier run
                    if f.suffix == ".rpt" or f.name in ("stats.txt",) or f.name == f"{name}_best.json":
                        shutil.copy(f, self.dir / "reports" / f"{name}_{tag}{f.name}")
            for f in d.glob("*.log"):
                if f.stat().st_mtime >= t0: shutil.copy(f, self.dir / "logs" / f"{tag}{f.name}")
        self.rows.append(dict(stage=name, backend=backend, seconds=round(dt), avg_cpu_percent=round(cpu), peak_mem_gb=round(mem, 1), score=score))

    def finalize(self):
        ctx, art = self.ctx, self.ctx.art
        for k, v in art.items():
            if k == "rtl": continue
            p = pathlib.Path(v)
            if p.exists():
                link = self.dir / "artifacts" / p.name
                if link.exists() or link.is_symlink(): link.unlink()
                link.symlink_to(os.path.relpath(p, link.parent))
        dcp = art.get("dcp")
        if dcp and pathlib.Path(dcp).exists() and ctx.cfg.get("signoff", True):
            self._signoff(pathlib.Path(dcp))
        (self.dir / "summary.json").write_text(json.dumps(dict(design=ctx.cfg.get("top"), part=ctx.target["part"], stages=self.rows,
                                                               artifacts={k: os.path.relpath(v) for k, v in art.items() if k != "rtl"}), indent=1))
        md = [f"# {ctx.cfg.get('top')} on {ctx.target['part']}\n", "| stage | backend | time (s) | avg cpu % | peak mem GB | score |", "|---|---|---|---|---|---|"]
        md += [f"| {r['stage']} | {r['backend']} | {r['seconds']} | {r['avg_cpu_percent']} | {r['peak_mem_gb']} | {r['score']} |" for r in self.rows]
        md += ["", "## Artifacts"] + [f"- `{p.name}`" for p in sorted((self.dir / 'artifacts').iterdir())]
        md += ["", "## Reports"] + [f"- `reports/{p.name}`" for p in sorted((self.dir / 'reports').iterdir())]
        (self.dir / "summary.md").write_text("\n".join(md) + "\n")
        return self.dir

    def _signoff(self, dcp):
        r, ctx = self.dir / "reports", self.ctx
        try:
            if find_vivado():
                clocks = "".join(f"create_clock -period {p} -name {n} [get_ports {n}]\n" for n, p in ctx.cfg.get("clocks", {}).items())
                t = ctx.work / "signoff.tcl"
                t.write_text(f"open_checkpoint {{{dcp}}}\n{clocks}"
                             f"report_utilization -file {{{r}/signoff_utilization.rpt}}\nreport_utilization -hierarchical -file {{{r}/signoff_utilization_hier.rpt}}\n"
                             f"report_timing_summary -max_paths 20 -file {{{r}/signoff_timing_summary.rpt}}\nreport_clock_utilization -file {{{r}/signoff_clock_util.rpt}}\n"
                             f"report_route_status -file {{{r}/signoff_route_status.rpt}}\nreport_drc -file {{{r}/signoff_drc.rpt}}\nreport_power -file {{{r}/signoff_power.rpt}}\n")
                ctx.sh([find_vivado(), "-mode", "batch", "-nojournal", "-log", "signoff.vivado.log", "-source", t.name], "signoff", cwd=ctx.work)
            else:
                ctx.sh([sys.executable, pathlib.Path(__file__).parent / "rw" / "dcp_report.py", dcp], "signoff")
                shutil.copy(ctx.work / "signoff.log", r / "signoff_utilization.rpt")
        except SystemExit as e:  # a failed sign-off must not discard the run
            (r / "signoff_FAILED.txt").write_text(f"sign-off report failed: {e}\n")
