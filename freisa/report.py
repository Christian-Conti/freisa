# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Collects tool reports and writes the run summary.
# Module   : report.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import json, os, pathlib, re, shutil, sys
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
            if not isinstance(v, (str, pathlib.Path)): continue  # files only (rtl, include dirs, defines, ... are lists)
            p = pathlib.Path(v)
            if p.exists():
                link = self.dir / "artifacts" / p.name
                if link.exists() or link.is_symlink(): link.unlink()
                link.symlink_to(os.path.relpath(p, link.parent))
        area, timing = self._open_reports()
        dcp = art.get("dcp")
        if ctx.cfg.get("signoff") == "vivado" and dcp and pathlib.Path(dcp).exists():  # Vivado reports only on request
            self._signoff(pathlib.Path(dcp))
        (self.dir / "summary.json").write_text(json.dumps(dict(design=ctx.cfg.get("top"), part=ctx.target["part"], stages=self.rows,
                                                               artifacts={k: os.path.relpath(v) for k, v in art.items() if isinstance(v, (str, pathlib.Path))}), indent=1))
        md = [f"# {ctx.cfg.get('top')} on {ctx.target['part']}\n", "| stage | backend | time (s) | avg cpu % | peak mem GB | score |", "|---|---|---|---|---|---|"]
        md += [f"| {r['stage']} | {r['backend']} | {r['seconds']} | {r['avg_cpu_percent']} | {r['peak_mem_gb']} | {r['score']} |" for r in self.rows]
        md += ["", "## Area", "```"] + area + ["```", "", "## Timing", "```"] + timing + ["```"]
        md += ["", "## Artifacts"] + [f"- `{p.name}`" for p in sorted((self.dir / 'artifacts').iterdir())]
        md += ["", "## Reports"] + [f"- `reports/{p.name}`" for p in sorted((self.dir / 'reports').iterdir())]
        (self.dir / "summary.md").write_text("\n".join(md) + "\n")
        return self.dir

    # ------------------------------------------------------------------ open reports (always)
    def _log(self, *names):
        for n in names:
            p = self.ctx.work / n
            if p.exists(): return p.read_text(errors="replace")
        return None

    def _open_reports(self):
        """reports/area.rpt and reports/timing.rpt from open tools; returns short summaries for summary.md."""
        ctx, r = self.ctx, self.dir / "reports"
        area, timing, a_sum, t_sum = [], [], [], []
        # area after synthesis (Yosys)
        st = ctx.work / "stats.txt"
        if st.exists():
            cells = re.findall(r"^\s+(\d+)\s+([A-Z][A-Z0-9_]+)\s*$", st.read_text().split("design hierarchy")[-1], re.M)
            area += ["== After synthesis (Yosys): cells by type"] + [f"  {t:<16} {n}" for n, t in cells] + [""]
            for n, t in cells:
                if t.startswith(("LUT", "FD", "RAMB", "URAM", "DSP", "CARRY")): a_sum.append(f"synth {t}: {n}")
        # area and timing after implementation
        nx = self._log("nextpnr_xilinx.log", "nextpnr_interchange.log")
        if nx:
            util = re.findall(r"Info:\s+([A-Za-z0-9_]+):\s+(\d+)/\s*(\d+)\s+(\d+)%", nx.split("Device utilisation:")[-1].split("Info: Placed")[0])
            used = [(n, u, t, pc) for n, u, t, pc in util if int(u) > 0]
            area += ["== After place and route (nextpnr): used resources"] + [f"  {n:<26} {u:>8} / {t:<8} {pc}%" for n, u, t, pc in used]
            a_sum += [f"{n}: {u}/{t} ({pc}%)" for n, u, t, pc in used if not n.startswith(("PSEUDO", "HARD"))]
            fm = re.findall(r"Max frequency for clock '([^']+)': ([0-9.]+) MHz \((PASS|FAIL)[^)]*\)", nx)
            if fm:
                last = {c: (f, ok) for c, f, ok in fm}
                timing += ["== nextpnr timing (after routing)"] + [f"  clock {c}: max frequency {f} MHz ({ok})" for c, (f, ok) in last.items()]
                cp = nx.split("Critical path report")[-1].split("\n\n")[0] if "Critical path report" in nx else ""
                timing += ["", "== Critical path", "Critical path report" + cp] if cp else []
                t_sum += [f"clock {c}: {f} MHz ({ok})" for c, (f, ok) in last.items()]
            else:
                timing += ["nextpnr-fpga_interchange has no timing model: no timing analysis for this route.",
                           "For timing on xc7 choose `route: nextpnr_xilinx` in the project file."]
                t_sum.append("no timing model in nextpnr-fpga_interchange (use route: nextpnr_xilinx)")
        elif ctx.target.get("family") in ("xczu", "xcvu", "xcku") and ("dcp" in ctx.art or "phys" in ctx.art):
            try:
                from . import ifx
                dcp = ctx.art.get("dcp") if ctx.art.get("dcp") and pathlib.Path(ctx.art["dcp"]).exists() else ifx.to_dcp(ctx, "report")
                ctx.sh([sys.executable, pathlib.Path(__file__).parent / "rw" / "dcp_report.py", dcp], "report_area")
                noise = re.compile(r"^\$|^\s*\(|Reading DCP|XML Parse|Read Netlist|\*Total\*|^-+$|^=+|XDEF|EDIF Parse|Write ")
                impl = [l for l in (ctx.work / "report_area.log").read_text().splitlines() if l.strip() and not noise.search(l)]
                area += ["== After implementation (RapidWright): cells and sites"] + impl
                ifx.rw(ctx, "rwroute.TimingAndWirelengthReport", [dcp], "report_timing")
                tl = [l for l in (ctx.work / "report_timing.log").read_text().splitlines() if l.strip() and not noise.search(l)]
                timing += ["== RapidWright timing model (after routing)"] + tl
                for key in ("Timing requirement (ps)", "Critical path delay (ps)", "Slack (ps)"):
                    m = next((l for l in tl if l.strip().startswith(key)), None)
                    if m: t_sum.append(" ".join(m.split()))
                cp = next((l for l in tl if l.strip().startswith("Critical path delay (ps)")), None)
                if cp:
                    ps = int(float(cp.split()[-1])); t_sum.append(f"max frequency: {1e6 / ps:.1f} MHz" if ps else "")
                for l in impl:
                    m = re.match(r"\s*(cells|sites used|LUT6|LUT5|LUT4|LUT3|LUT2|LUT1|FDRE|RAMB36E2|RAMB18E2|DSP48E2|URAM288|BUFGCE)\s+(\d+)", l)
                    if m: a_sum.append(f"impl {m.group(1)}: {m.group(2)}")
            except SystemExit as e:
                timing.append(f"timing/area report failed: {e}")
        (r / "area.rpt").write_text("\n".join(area or ["no area information for this run"]) + "\n")
        (r / "timing.rpt").write_text("\n".join(timing or ["no timing information for this run"]) + "\n")
        return a_sum or ["-"], [t for t in t_sum if t] or ["-"]

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
