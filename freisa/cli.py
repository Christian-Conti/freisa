# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : FREISA status interface: environment, tools, boards, projects and builds at a glance.
#            python freisa.py status [env|tools|boards|projects|builds], python freisa.py show <design> <board>
# Module   : cli.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import datetime, json, os, pathlib, re, shutil, subprocess, sys
import yaml
from . import term as T

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.environ["PATH"] = f"{ROOT / 'install' / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"

BANNER = r"""
   ███████╗██████╗ ███████╗██╗███████╗ █████╗
   ██╔════╝██╔══██╗██╔════╝██║██╔════╝██╔══██╗
   █████╗  ██████╔╝█████╗  ██║███████╗███████║
   ██╔══╝  ██╔══██╗██╔══╝  ██║╚════██║██╔══██║
   ██║     ██║  ██║███████╗██║███████║██║  ██║
   ╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝╚══════╝╚═╝  ╚═╝"""
BANNER_PLAIN = r"""
    _____ ____  _____ ___ ____    _
   |  ___|  _ \| ____|_ _/ ___|  / \
   | |_  | |_) |  _|  | |\___ \ / _ \
   |  _| |  _ <| |___ | | ___) / ___ \
   |_|   |_| \_\_____|___|____/_/   \_\ """
TAGLINE = "FPGA Reusable and Extensible Infrastructure for Synthesis Automation"

# ------------------------------------------------------------------ drawing
def width():
    return max(60, min(shutil.get_terminal_size((110, 30)).columns, 130))

def vis(s):
    return len(T.plain(s))

def fit(s, n):
    """Pad or cut a (possibly colored) string to n visible characters."""
    p = T.plain(s)
    if len(p) <= n: return s + " " * (n - len(p))
    return p[:max(0, n - 1)] + "…"

def panel(title, rows, cols=None):
    """Box with a title; rows are lists of cells (a table, columns sized to fit) or plain strings."""
    W = width(); inner = W - 4
    out = [T.orange("╭─ ") + T.bold(T.orange(title)) + T.orange(" " + "─" * max(0, W - vis(title) - 5) + "╮")]
    table = [r for r in rows if isinstance(r, (list, tuple))] + ([list(cols)] if cols else [])  # column widths: rows and header
    if table:
        n = max(len(r) for r in table)
        w = [max(vis(str(r[i])) if i < len(r) else 0 for r in table) for i in range(n)]
        while sum(w) + 2 * (n - 1) > inner and max(w) > 8: w[w.index(max(w))] -= 1  # shrink the widest column
    if cols:
        line = "  ".join(fit(T.dim(c), w[i]) for i, c in enumerate(cols))
        out.append(T.orange("│ ") + fit(line, inner) + T.orange(" │"))
    for r in rows:
        line = r if isinstance(r, str) else "  ".join(fit(str(c), w[i]) for i, c in enumerate(r))
        out.append(T.orange("│ ") + fit(line, inner) + T.orange(" │"))
    out.append(T.orange("╰" + "─" * (W - 2) + "╯"))
    return "\n".join(out)

YES, NO = (T.green("●"), T.red("○")) if T.OK != "ok" else ("yes", "no")

def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip()  # java -version prints on stderr
    except (OSError, subprocess.TimeoutExpired):
        return ""

def ago(ts):
    d = datetime.datetime.now() - datetime.datetime.fromtimestamp(ts)
    if d.days: return f"{d.days}d ago"
    h, m = d.seconds // 3600, d.seconds % 3600 // 60
    return f"{h}h {m}m ago" if h else f"{m}m ago"

# ------------------------------------------------------------------ sections
def env_status():
    """[(name, found, version, where)] of the programs FREISA runs."""
    from .core import find_vivado
    viv = find_vivado()
    vver = re.search(r"/(\d{4}\.\d)/", viv or "")
    rw = run([sys.executable, "-c", "import importlib.metadata as m; print(m.version('rapidwright'))"])
    return [
        ("conda env", True, os.environ.get("CONDA_DEFAULT_ENV", "-"), sys.executable),
        ("Yosys", bool(shutil.which("yosys")), (run(["yosys", "-V"]).split(" (")[0] or "-").replace("Yosys ", ""), shutil.which("yosys") or "not on PATH"),
        ("Java", bool(shutil.which("java")), (re.findall(r'"([^"]+)"', run(["java", "-version"])) or ["-"])[0], "RapidWright " + (rw or "?")),
        ("openFPGALoader", bool(shutil.which("openFPGALoader")), (run(["openFPGALoader", "-V"]).split() or ["-"])[-1], "board programming"),
        ("Vivado (optional)", bool(viv), vver.group(1) if vver else "-", viv or "not found: open tools only"),
    ]

def env():
    return panel("Environment", [[n, YES if ok else NO, v, w] for n, ok, v, w in env_status()], ["", "", "version", "where"])

TOOL_BIN = {  # tools.lock name -> what shows it is built
    "dreamplacefpga": "third_party/dreamplacefpga/install/dreamplacefpga/Placer.py",
    "nextpnr-fpga-interchange": "install/bin/nextpnr-fpga_interchange",
    "nextpnr-xilinx": "install/bin/nextpnr-xilinx",
    "prjxray": "install/bin/xc7frames2bit", "prjuray": "install/bin/xcframes2bit",
    "python-fpga-interchange": None, "fpga-interchange-schema": None, "prjxray-db": None, "prjuray-db": None,
}
TOOL_ROLE = {"dreamplacefpga": "place (UltraScale+)", "nextpnr-fpga-interchange": "place+route (xc7)", "nextpnr-xilinx": "place+route (xc7)",
             "prjxray": "bitstream (xc7)", "prjxray-db": "xc7 bitstream database", "python-fpga-interchange": "Interchange (xc7, FASM)",
             "fpga-interchange-schema": "Interchange schemas", "prjuray": "bitstream (UltraScale+)", "prjuray-db": "UltraScale+ database"}

def tool_status():
    """One dict per tools.lock entry: name, url, ref, sha (checked out), ok (fetched and built), pinned, role."""
    from . import ifx
    out = []
    for line in (ROOT / "tools.lock").read_text().splitlines():
        if not line.strip() or line.startswith("#"): continue
        name, url, ref = line.split()[:3]
        d = ROOT / "third_party" / name
        sha = run(["git", "-C", str(d), "rev-parse", "--short=10", "HEAD"]) if (d / ".git").exists() else ""
        built = TOOL_BIN.get(name)
        ok = (d / ".git").exists() and (built is None or (ROOT / built).exists())
        if name == "python-fpga-interchange": ok = ok and ifx.if_python() is not None
        out.append(dict(name=name, url=url, ref=ref, sha=sha, ok=ok, pinned=bool(re.fullmatch(r"[0-9a-f]{40}", ref)), role=TOOL_ROLE.get(name, "")))
    return out

def tools():
    rows = [[t["name"], YES if t["ok"] else NO, t["sha"] or "-", T.yellow("pinned") if t["pinned"] else T.cyan("latest"), t["role"]]
            for t in tool_status()]
    return panel("Tools  (tools.lock)", rows, ["", "", "commit", "follows", "role"])

def boards():
    cfg = (yaml.safe_load(open(ROOT / "boards.yml")) or {}).get("boards") or {}
    rows = []
    for name, b in cfg.items():
        installed = (ROOT / "targets" / f"{name}.yml").exists() and (ROOT / "boards" / name).exists()
        p = b.get("part", "")
        bit = T.green("open") if p.startswith("xc7") else T.yellow("vivado write only")
        rows.append([name, YES if installed else NO, p, bit, b.get("description", "")])
    return panel("Boards  (boards.yml)", rows, ["", "", "part", "bitstream", ""])

def projects():
    rows = []
    for f in sorted((ROOT / "designs").rglob("*.yml")):
        y = yaml.safe_load(open(f)) or {}
        boards_ = sorted({k.split("@")[0] for k in (y.get("per_target") or {})} | set(y.get("boards") or {}))
        rows.append([f.stem, y.get("top", "-"), os.path.relpath(f, ROOT), ", ".join(boards_) or "-"])
    return panel("Projects  (designs/)", rows or ["no project files"], ["", "top", "file", "boards with settings"])

def build_info(d):
    """Status of one build directory build/<design>/<board>."""
    log = d / "flow.log"
    txt = log.read_text(errors="replace") if log.exists() else ""
    state = T.green("finished") if re.search(r"finished in", txt) else T.red("FAILED") if "FAILED" in txt else T.yellow("running?") if txt else "-"
    bit = next(iter(sorted(d.rglob("out.bit"), key=lambda p: p.stat().st_mtime, reverse=True)), None)
    summ = d / "report" / "summary.md"
    timing = ""
    if summ.exists():
        m = re.search(r"## Timing\n```\n(.*?)```", summ.read_text(), re.S)
        if m:
            lines = [l for l in m.group(1).splitlines() if l.strip() and l.strip() != "-"]
            timing = next((l for l in lines if "frequency" in l or "MHz" in l), lines[0] if lines else "")
    return state, bit, timing, (log.stat().st_mtime if log.exists() else 0)

def builds(limit=12):
    dirs = [p for p in (ROOT / "build").glob("*/*") if (p / "flow.log").exists()]
    dirs.sort(key=lambda p: (p / "flow.log").stat().st_mtime, reverse=True)
    rows = []
    for d in dirs[:limit]:
        state, bit, timing, ts = build_info(d)
        rows.append([d.parent.name, d.name, state, ago(ts), YES if bit else NO, timing or "-"])
    return panel(f"Builds  (latest {min(limit, len(dirs))} of {len(dirs)})", rows or ["no builds yet: python freisa.py run"],
                 ["design", "board", "result", "when", ".bit", "timing"])

def show(design, board, banner=True):
    d = ROOT / "build" / design / board
    if not d.exists(): sys.exit(T.error(f"no build {os.path.relpath(d, ROOT)}"))
    state, bit, timing, ts = build_info(d)
    out = [header(), ""] if banner else []
    sj = d / "report" / "summary.json"
    rows = []
    if sj.exists():
        s = json.loads(sj.read_text())
        for r in s.get("stages", []):
            rows.append([r["stage"], r["backend"], f"{r['seconds']} s", f"{r['avg_cpu_percent']}%", f"{r['peak_mem_gb']} GB", r.get("score") or "-"])
    out.append(panel(f"{design} on {board}: {T.plain(state)}, {ago(ts)}", rows or ["no step summary"], ["step", "tool", "time", "cpu", "peak mem", "score"]))
    md = (d / "report" / "summary.md").read_text() if (d / "report" / "summary.md").exists() else ""
    for sec in ("Area", "Timing"):
        m = re.search(rf"## {sec}\n```\n(.*?)```", md, re.S)
        lines = [l for l in (m.group(1).splitlines() if m else []) if l.strip()]
        out.append(panel(sec, lines or ["-"]))
    arts = sorted((d / "report" / "artifacts").iterdir()) if (d / "report" / "artifacts").exists() else []
    out.append(panel("Files", [[a.name, os.path.relpath(a.resolve(), ROOT)] for a in arts] or ["-"]
                     + [f"reports: {os.path.relpath(d / 'report' / 'reports', ROOT)}/  logs: {os.path.relpath(d / 'report' / 'logs', ROOT)}/"]))
    return "\n".join(out)

def header():
    art = BANNER if T.OK != "ok" else BANNER_PLAIN
    lines = [T.orange(l) for l in art.strip("\n").splitlines()]
    sha = run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"])
    lines += ["", "   " + T.bold(TAGLINE), "   " + T.dim(f"{str(ROOT).replace(os.path.expanduser('~'), '~')}  ·  commit {sha or '-'}")]
    return "\n".join(lines)

def main():
    a = sys.argv[1:] or ["status"]
    cmd = a[0]
    if cmd in ("-h", "--help", "help"):
        print(header() + "\n\n  python freisa.py status [env|tools|boards|projects|builds]   python freisa.py show <design> <board>\n"
              "  all commands: python freisa.py help"); return
    if cmd == "show":
        if len(a) < 3: sys.exit(T.error("usage: python freisa.py show <design> <board>"))
        print(show(a[1], a[2])); return
    parts = {"env": env, "tools": tools, "boards": boards, "projects": projects, "builds": builds}
    if cmd == "status":
        print(header() + "\n")
        for f in parts.values(): print(f() + "\n")
        print("  " + T.dim("details: python freisa.py show <design> <board>   ·   run: python freisa.py run -d <design> -t <board>   ·   all commands: python freisa.py help"))
    elif cmd in parts:
        print(parts[cmd]())
    else:
        sys.exit(T.error(f"unknown command {cmd}: python freisa.py help"))

if __name__ == "__main__":
    main()
