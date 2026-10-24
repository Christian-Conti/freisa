# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive terminal interface (curses), started with `python freisa.py`. One tab per job: Home, Flow (choose
#            design, board and the tool of every step, run with live logs), Builds, Boards, Hardware (JTAG cables,
#            programming, reset, UART monitor) and Tools. Commands run in the background through the make targets.
#            To add a tab: subclass Tab and append it to TABS; to add a command to a tab: one line in its keys().
# Module   : tui.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from . import cli, core, resolve, term as T
from .stages import upload

ROOT = cli.ROOT
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
BAUDS = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
CHIP = ["  ┌┴┴┴┴┴┴┴┴┴┐ ",
        " ─┤ ▓▓▓▓▓▓▓ ├─",
        " ─┤ ▓ LUT ▓ ├─",
        " ─┤ ▓▓▓▓▓▓▓ ├─",
        "  └┬┬┬┬┬┬┬┬┬┘ "]

# ------------------------------------------------------------------ data
def designs():  return {f.stem: f for f in sorted((ROOT / "designs").rglob("*.yml"))}
def boards_cfg(): return (yaml.safe_load(open(ROOT / "boards.yml")) or {}).get("boards") or {}
def installed(): return sorted(p.stem for p in (ROOT / "targets").glob("*.yml"))
def target(name): return core.load_yaml(ROOT / "targets" / f"{name}.yml")
def rel(p): return os.path.relpath(p, ROOT)

def builds():
    """Build directories build/<design>/<board>, newest first."""
    ds = [p for p in (ROOT / "build").glob("*/*") if (p / "flow.log").exists()]
    return sorted(ds, key=lambda p: (p / "flow.log").stat().st_mtime, reverse=True)

def fpga_want(part):
    """Prefix of the FPGA model JTAG reports for this part (same rule as `make upload`)."""
    return re.sub(r"(ev|eg|cg|dr)$", "", upload._model(part))

def ports():
    """[(tty, usb serial, interface number)] of every USB serial port."""
    out = []
    for t in sorted(pathlib.Path("/sys/class/tty").glob("ttyUSB*"), key=lambda p: int(p.name[6:])):
        try:
            intf = (t / "device").resolve().parent
            out.append((f"/dev/{t.name}", (intf.parent / "serial").read_text().strip(), int((intf / "bInterfaceNumber").read_text(), 16)))
        except (OSError, ValueError):
            pass
    return out

def tail(path, n=400):
    """Last lines of a text file (reads only its end)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 64 * 1024))
            return [T.plain(l) for l in f.read().decode(errors="replace").splitlines()[-n:]]
    except OSError:
        return []

def fmt(s):
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"

# ------------------------------------------------------------------ drawing
C = {}

def init_colors():
    curses.start_color(); curses.use_default_colors()
    rich = curses.COLORS >= 256
    spec = {"accent": 214 if rich else curses.COLOR_YELLOW, "ok": curses.COLOR_GREEN, "bad": curses.COLOR_RED,
            "warn": curses.COLOR_YELLOW, "info": curses.COLOR_CYAN, "dim": 244 if rich else curses.COLOR_WHITE}
    for i, (k, c) in enumerate(spec.items(), 1):
        curses.init_pair(i, c, -1); C[k] = curses.color_pair(i)
    curses.init_pair(10, curses.COLOR_BLACK, spec["accent"]); C["tab"] = curses.color_pair(10) | curses.A_BOLD
    C["grad"] = []
    for i, g in enumerate([226, 220, 214, 208, 202, 196] if rich else [curses.COLOR_YELLOW] * 6):
        curses.init_pair(20 + i, g, -1); C["grad"].append(curses.color_pair(20 + i) | curses.A_BOLD)

def put(w, y, x, s, attr=0, n=None):
    """addstr clipped to the window (and to n columns); never raises."""
    H, W = w.getmaxyx()
    if y < 0 or y >= H or x < 0 or x >= W: return
    s = str(s)[:max(0, min(W - x, n if n is not None else W))]
    try: w.addstr(y, x, s, attr)
    except curses.error: pass  # the bottom-right cell raises after drawing

def box(w, y, x, h, wd, title="", focus=False):
    a = C["accent"] if focus else C["dim"]
    put(w, y, x, "╭" + "─" * (wd - 2) + "╮", a)
    for r in range(1, h - 1): put(w, y + r, x, "│", a); put(w, y + r, x + wd - 1, "│", a)
    put(w, y + h - 1, x, "╰" + "─" * (wd - 2) + "╯", a)
    if title: put(w, y, x + 2, f" {title} ", (C["accent"] | curses.A_BOLD) if focus else curses.A_BOLD, wd - 4)

def tone(line):
    """Color of a log line from its content."""
    l = line.lower().lstrip()
    if re.search(r"\bfail|\berror|✘|exit code [1-9]|traceback|denied", l): return C["bad"]
    if re.match(r"(ok|✔)\b", l) or re.search(r"finished|done in|programmed|echo matches|keeps v", l): return C["ok"]
    if l.startswith((">>", "▶", "$ ")): return C["accent"] | curses.A_BOLD
    if l.startswith(("!", "warning")) or "warning" in l: return C["warn"]
    if l.startswith(("│", "|")): return C["dim"]
    return 0

def textpane(w, y, x, h, wd, lines, title="", focus=False, scroll=0, colorize=True):
    """Box with lines; scroll = lines up from the end (0 = follow the end)."""
    box(w, y, x, h, wd, title, focus)
    n = h - 2
    end = max(n, len(lines) - scroll)
    for r, l in enumerate(lines[max(0, end - n):end]):
        put(w, y + 1 + r, x + 2, l, tone(l) if colorize else 0, wd - 4)
    if len(lines) > n:
        put(w, y + h - 1, x + wd - 14, f" {max(0, end - n) + 1}-{min(end, len(lines))}/{len(lines)} ", C["dim"])

WIDE = 110  # below this width panes are stacked instead of side by side

def split(y, x, h, wd, side, top):
    """Two areas (y, x, h, w): side by side when wide (left one `side` columns), stacked when narrow (top one `top` rows)."""
    if wd >= WIDE: return (y, x, h, side), (y, x + side, h, wd - side)
    top = max(3, min(top, h - 6))
    return (y, x, top, wd), (y + top, x, h - top, wd)

class ListView:
    """Selectable list: rows are lists of (text, attr) segments."""
    def __init__(self): self.i = 0
    def move(self, k, n):
        d = {curses.KEY_UP: -1, ord("k"): -1, curses.KEY_DOWN: 1, ord("j"): 1, curses.KEY_PPAGE: -10, curses.KEY_NPAGE: 10,
             curses.KEY_HOME: -10**6, curses.KEY_END: 10**6}.get(k)
        if d is None or not n: return False
        self.i = max(0, min(n - 1, self.i + d)); return True
    def draw(self, w, y, x, h, wd, rows, focus=True):
        self.i = max(0, min(self.i, len(rows) - 1))
        top = max(0, self.i - h + 1)
        for r, segs in enumerate(rows[top:top + h]):
            sel = top + r == self.i
            col = x
            if sel: put(w, y + r, x, " " * wd, curses.A_REVERSE if focus else C["dim"] | curses.A_REVERSE)
            for text, attr in segs:
                put(w, y + r, col, text, (attr | curses.A_REVERSE) if sel and focus else attr, x + wd - col)
                col += len(text)

# ------------------------------------------------------------------ background commands
class Job:
    """A command running in the background; its output is kept for the log panes."""
    def __init__(self, cmd, title):
        self.cmd, self.title, self.t0, self.t1, self.rc = [str(c) for c in cmd], title, time.time(), None, None
        self.lines = collections.deque(["$ " + " ".join(self.cmd)], maxlen=5000)
        self.p = subprocess.Popen(self.cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "NO_COLOR": "1", "COLUMNS": "160"}, start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()
    def _read(self):
        buf = b""
        for chunk in iter(lambda: self.p.stdout.read1(4096), b""):
            *done, buf = (buf + chunk).split(b"\n")
            for l in done:
                s = T.plain(l.rstrip(b"\r").split(b"\r")[-1].decode(errors="replace")).rstrip()  # \r: progress bars, keep the last
                if s: self.lines.append(s)
        self.rc = self.p.wait(); self.t1 = time.time()
        self.lines.append(("✔ done" if self.rc == 0 else f"✘ exit code {self.rc}") + f" in {fmt(self.t1 - self.t0)}")
    @property
    def running(self): return self.rc is None
    def elapsed(self): return (self.t1 or time.time()) - self.t0
    def kill(self):
        if self.running:
            try: os.killpg(self.p.pid, signal.SIGTERM)
            except ProcessLookupError: pass

class Uart:
    """Serial port monitor: a thread keeps the last 64 KB received."""
    def __init__(self, port, baud):
        import serial
        self.port, self.baud, self.err = port, baud, None
        self.s = serial.Serial(port, baud, timeout=0.1)
        self.data, self.sent, self.alive = bytearray(), 0, True
        threading.Thread(target=self._read, daemon=True).start()
    def _read(self):
        while self.alive:
            try: b = self.s.read(4096)
            except Exception as e: self.err = str(e); return
            if b: self.data += b; del self.data[:-65536]
    def send(self, b): self.s.write(b); self.sent += len(b)
    def close(self):
        self.alive = False; time.sleep(0.15); self.s.close()

# ------------------------------------------------------------------ popups
KEYNAMES = {"Enter": (10, 13, curses.KEY_ENTER), "Del": (curses.KEY_DC,), "Space": (32,)}

def modal_pick(app, title, options, current=None):
    """options: [(label, value, note, attr)]; returns the value or None (Esc)."""
    i = next((n for n, o in enumerate(options) if o[1] == current), 0)
    while True:
        h, w = app.scr.getmaxyx()
        lw = max([len(title) + 4] + [len(o[0]) + len(o[2]) + 6 for o in options]); bw = min(w - 4, lw + 4)
        n = min(len(options), h - 6); bh = n + 2
        y, x = (h - bh) // 2, (w - bw) // 2
        win = curses.newwin(bh, bw, y, x); win.keypad(True); win.erase()
        box(win, 0, 0, bh, bw, title, True)
        top = max(0, i - n + 1)
        for r, (label, _, note, attr) in enumerate(options[top:top + n]):
            sel = top + r == i
            put(win, r + 1, 1, " " * (bw - 2), curses.A_REVERSE if sel else 0)
            put(win, r + 1, 2, label, (attr or 0) | (curses.A_REVERSE if sel else 0), bw - 4)
            put(win, r + 1, 4 + len(label), note, C["dim"] | (curses.A_REVERSE if sel else 0), bw - 6 - len(label))
        win.refresh()
        k = win.getch()
        if k in (curses.KEY_UP, ord("k")): i = (i - 1) % len(options)
        elif k in (curses.KEY_DOWN, ord("j")): i = (i + 1) % len(options)
        elif k in KEYNAMES["Enter"]: return options[i][1]
        elif k in (27, ord("q")): return None

def modal_text(app, title, value=""):
    """One-line text field; returns the text or None (Esc)."""
    h, w = app.scr.getmaxyx(); bw = min(w - 4, max(60, len(title) + 8))
    win = curses.newwin(3, bw, h // 2 - 1, (w - bw) // 2); win.keypad(True)
    curses.curs_set(1); s = value
    try:
        while True:
            win.erase(); box(win, 0, 0, 3, bw, title + "  (Enter ok · Esc cancel)", True)
            put(win, 1, 2, s[-(bw - 5):]); win.move(1, 2 + min(len(s), bw - 5))
            k = win.get_wch()
            if k in ("\x1b",): return None
            if k in ("\n", "\r", curses.KEY_ENTER): return s
            if k in (curses.KEY_BACKSPACE, "\x7f", "\b"): s = s[:-1]
            elif isinstance(k, str) and k.isprintable(): s += k
    finally:
        curses.curs_set(0)

def confirm(app, msg):
    return modal_pick(app, msg, [("no", False, "", 0), ("yes", True, "", C["warn"] | curses.A_BOLD)]) is True

# ------------------------------------------------------------------ tabs
class Tab:
    """One tab. keys() lists the commands: (key, hint, function); the footer shows the hints."""
    title = icon = ""
    capture = False  # True while the tab reads text (every key goes to it)
    def __init__(self, app): self.app, self.job, self.scroll = app, None, 0
    def keys(self): return []
    def draw(self, w, y, x, h, wd): pass
    def key(self, k):
        if k in (curses.KEY_SR, ord("K")): self.scroll += 5; return True  # Shift+↑/↓ scroll the log
        if k in (curses.KEY_SF, ord("J")): self.scroll = max(0, self.scroll - 5); return True
        for kn, _, fn in self.keys():
            if k in (KEYNAMES[kn] if kn in KEYNAMES else (ord(kn),)): fn(); return True
        return False
    def run(self, cmd, title):
        if self.job and self.job.running and not confirm(self.app, f"'{self.job.title}' is running: stop it?"): return
        if self.job: self.job.kill()
        self.job = self.app.start(cmd, title); self.scroll = 0
    def stop(self):
        if self.job and self.job.running: self.job.kill(); self.app.flash("stopped", C["warn"])
    def log(self, w, y, x, h, wd, title="log"):
        j = self.job
        if j is None: textpane(w, y, x, h, wd, ["", "  nothing run yet"], title); return
        st = f"{SPIN[int(time.time() * 8) % 10]} {fmt(j.elapsed())}" if j.running else ("✔" if j.rc == 0 else f"✘ {j.rc}")
        textpane(w, y, x, h, wd, list(j.lines), f"{title}: {j.title}  {st}", j.running, self.scroll)

class Home(Tab):
    title, icon = "Home", "⌂"
    def draw(self, w, y, x, h, wd):
        a = self.app
        tools, bs, ds, bl = a.cache("tools", cli.tool_status), boards_cfg(), designs(), builds()
        inst = installed(); env = a.env
        viv = next((e for e in env or [] if e[0].startswith("Vivado")), None)
        hw = next((t for t in a.tabs if isinstance(t, Hardware)), None)
        found = sorted({b for c in (hw.cables if hw else []) for b in hw.boards_of(c)})
        cards = [("TOOLS", f"{sum(t['ok'] for t in tools)}/{len(tools)}", "fetched and built"),
                 ("BOARDS", f"{len([b for b in bs if b in inst])}/{len(bs)}", "installed"),
                 ("PROJECTS", str(len(ds)), "in designs/"),
                 ("BUILDS", str(len(bl)), f"{sum('FAILED' in T.plain(cli.build_info(d)[0]) for d in bl[:20])} failed"),
                 ("JTAG", "…" if hw and hw.scanning else f"{len(hw.cables) if hw else 0} cables", ", ".join(found) or "no known board"),
                 ("VIVADO", (viv[2] if viv and viv[1] else "none") if env else "…", "optional, closed")]
        per = len(cards) if wd >= WIDE else 3
        cw = (wd - 1) // per
        for i, (t, v, sub) in enumerate(cards):
            cx, cy = x + 1 + (i % per) * cw, y + (i // per) * 4
            box(w, cy, cx, 4, cw - 1, t, i == 0)
            put(w, cy + 1, cx + 2, v, C["accent"] | curses.A_BOLD, cw - 5)
            put(w, cy + 2, cx + 2, sub, C["dim"], cw - 5)
        # open flow per family, as `auto` resolves it on the installed boards
        yy = y + 4 * -(-len(cards) // per) + 1
        put(w, yy, x + 2, "OPEN FLOW", C["accent"] | curses.A_BOLD); put(w, yy, x + 12, "auto, per installed board family", C["dim"]); yy += 1
        seen = {}
        for b in inst:
            try: t = target(b)
            except Exception: continue
            core.load_backends()
            chain = tuple((b_.label(), b_.supports(t) is None) for b_ in (core.pick(s, "auto", t) for s in core.STAGES[1:] + ["upload"]))
            seen.setdefault(chain, []).append(b)
        for chain, bnames in seen.items():
            put(w, yy, x + 2, ", ".join(bnames), C["info"], wd - 4); yy += 1
            col = x + 4
            for i, (lb, ok) in enumerate((("RTL", True),) + chain):
                seg = f"[{lb}]"
                if col + len(seg) + 4 > x + wd: yy += 1; col = x + 6
                put(w, yy, col, seg, (C["ok"] if ok else C["bad"]) if i else C["dim"]); col += len(seg)
                if i < len(chain): put(w, yy, col, " ─▶ ", C["dim"]); col += 4
            yy += 2
        # latest builds
        n = max(0, h - (yy - y))
        if n >= 4:
            nw = max(16, min(34, wd - 40)); rows = []
            for d in bl[:n - 2]:
                st, bit, tm, ts = cli.build_info(d)
                st = T.plain(st)
                rows.append(f"{'✔' if st == 'finished' else '✘' if st == 'FAILED' else '…'} {(d.parent.name + '/' + d.name)[:nw]:<{nw}} {st:<9} "
                            f"{cli.ago(ts):<10} {'bit' if bit else '   '}  {tm}")
            textpane(w, yy, x + 1, min(n, len(rows) + 2), wd - 2, rows or ["no builds yet: tab 2 (Flow)"], "LATEST BUILDS")

class Flow(Tab):
    """Choose design, board, FROM/TO and the tool of every step; run with live progress and logs."""
    title, icon = "Flow", "⚙"
    ROWS = ["design", "board", "from", "to", "steps"]
    def __init__(self, app):
        super().__init__(app)
        self.design = "blinky" if "blinky" in designs() else next(iter(designs()), "")
        self.board = "xc7z020" if "xc7z020" in installed() else next(iter(installed()), "")
        self.frm, self.to, self.over, self.row, self.si, self.res, self.err = core.STAGES[0], core.STAGES[-1], {}, 0, 0, None, ""
        self.toollog, self.toollog_t, self.wide, self.logview = [], 0, True, "flow"
        self.resolve()
    def resolve(self):
        try:
            self.res = resolve.Resolved(self.design, self.board, {k: v for k, v in self.over.items() if k != "upload"}); self.err = ""
        except SystemExit as e:
            self.res, self.err = None, T.plain(str(e))
    def options(self, s):
        """Every value of one step: auto/all/all_open and the tools, with availability on this board."""
        t = target(self.board); core.load_backends()
        auto = core.pick(s, "auto", t).label()
        out = [("auto", "auto", f"first open tool that works: {auto}", C["info"])]
        if s != "upload":
            out += [("all", "all", "every tool that works, keep the best", C["accent"]),
                    ("all_open", "all_open", "every open tool that works, keep the best", C["accent"])]
        for n, cls in core.REGISTRY[s].items():
            why = cls().supports(t)
            out.append((cls.label(), n, "✔ available" if not why else f"✘ {why}", C["ok"] if not why else C["bad"]))
        return out
    def value(self, s):
        if s == "upload": return self.over.get("upload") or (self.res.steps.get("upload", "auto") if self.res else "auto")
        return self.over.get(s) or (self.res.steps.get(s, "auto") if self.res else "auto")
    def stages(self): return core.STAGES[1:] + ["upload"]
    def status(self, s):
        """(value, tool that runs, reason it cannot run or None) of one step."""
        v = self.value(s)
        if not self.res: return v, None, self.err or "?"
        name = self.res.sel[s].name if v in ("auto", "all", "all_open") else v
        cls = core.REGISTRY.get(s, {}).get(name)
        return v, cls, (cls().supports(target(self.board)) if cls else f"unknown tool {name}")
    def cycle(self, d):
        r = self.ROWS[self.row]
        if r == "design": ds = list(designs()); self.design = ds[(ds.index(self.design) + d) % len(ds)] if self.design in ds else ds[0]; self.over = {}
        elif r == "board": bs = installed(); self.board = bs[(bs.index(self.board) + d) % len(bs)] if self.board in bs else bs[0]; self.over = {}
        elif r == "from":
            i = (core.STAGES.index(self.frm) + d) % len(core.STAGES); self.frm = core.STAGES[i]
            if i > core.STAGES.index(self.to): self.to = self.frm
        elif r == "to":
            i = (core.STAGES.index(self.to) + d) % len(core.STAGES); self.to = core.STAGES[i]
            if i < core.STAGES.index(self.frm): self.frm = self.to
        elif r == "steps": self.si = (self.si + d) % len(self.stages()); return
        self.resolve()
    def enter(self):
        r = self.ROWS[self.row]
        if r == "design":
            v = modal_pick(self.app, "design", [(k, k, rel(p), 0) for k, p in designs().items()], self.design)
            if v: self.design, self.over = v, {}
        elif r == "board":
            bs = boards_cfg()
            v = modal_pick(self.app, "board", [(b, b, bs.get(b, {}).get("part", ""), 0) for b in installed()], self.board)
            if v: self.board, self.over = v, {}
        elif r == "steps":
            s = self.stages()[self.si]
            v = modal_pick(self.app, f"tool for {s} on {self.board}", self.options(s), self.value(s))
            if v: self.over[s] = v
        else: self.cycle(1); return
        self.resolve()
    def steps_arg(self):
        o = {k: v for k, v in self.over.items() if k != "upload"}
        return [f"STEPS={' '.join(f'{k}={v}' for k, v in o.items())}"] if o else []
    def base(self): return [f"DESIGN={self.design}", f"TARGET={self.board}"]
    def go(self, to=None):
        self.run(["make", "flow", *self.base(), f"FROM={self.frm}", f"TO={to or self.to}", *self.steps_arg()],
                 f"flow {self.design} → {self.board}")
    def check(self): self.run(["make", "check", *self.base(), f"FROM={self.frm}", f"TO={self.to}", *self.steps_arg()], f"check {self.design} → {self.board}")
    def doctor(self): self.run(["make", "doctor", *self.base()], f"doctor {self.board}")
    def upload(self):
        tool = self.over.get("upload")
        self.run(["make", "upload", *self.base(), *([f"TOOL={tool}"] if tool and tool != "auto" else [])], f"upload {self.design} → {self.board}")
    def edit(self):
        p = designs().get(self.design)
        if p: self.app.edit(p); self.resolve()
    def keys(self):
        return [("Enter", "choose", self.enter), ("r", "run", self.go), ("s", "synth only", lambda: self.go("synth")),
                ("c", "check", self.check), ("u", "upload", self.upload), ("d", "doctor", self.doctor), ("e", "edit project", self.edit),
                ("0", "reset tools", lambda: (self.over.clear(), self.resolve())),
                ("l", "flow/tool log", lambda: setattr(self, "logview", "tool" if self.logview == "flow" else "flow")), ("x", "stop", self.stop)]
    def key(self, k):
        if k in (curses.KEY_UP, curses.KEY_DOWN):
            d = 1 if k == curses.KEY_DOWN else -1
            if self.ROWS[self.row] == "steps" and not self.wide and 0 <= self.si + d < len(self.stages()):
                self.si += d; return True  # narrow: steps are a vertical list
            self.row = (self.row + d) % len(self.ROWS)
            if self.ROWS[self.row] == "steps" and not self.wide: self.si = 0 if d > 0 else len(self.stages()) - 1
            return True
        if k in (curses.KEY_LEFT, curses.KEY_RIGHT): self.cycle(1 if k == curses.KEY_RIGHT else -1); return True
        return super().key(k)

    def progress(self):
        """(started, done) stages parsed from the flow output."""
        ls = list(self.job.lines) if self.job else []
        st = [m.group(1) for l in ls if (m := re.match(r"\s*(?:>>|▶)\s+(\w+)\s", l)) and m.group(1) in core.STAGES]
        dn = [m.group(1) for l in ls if (m := re.match(r"\s*(?:ok|✔)\s+(\w+)\s+done in", l))]
        return st, dn
    def draw(self, w, y, x, h, wd):
        bcfg = boards_cfg().get(self.board, {})
        p = designs().get(self.design)
        lab = lambda r, t: put(w, yy, x + 2, f" {t:<7}", (C["tab"] if self.row == self.ROWS.index(r) else curses.A_BOLD))
        val = lambda v: put(w, yy, x + 11, f"◀ {v} ▶", C["accent"] | curses.A_BOLD)
        yy = y; box(w, y, x, 6, wd, "CONFIGURATION  ↑↓ field · ←→ change · Enter list", self.row < 4)
        yy += 1; lab("design", "design"); val(self.design); put(w, yy, x + 17 + len(self.design), rel(p) if p else "", C["dim"], wd - 19 - len(self.design))
        yy += 1; lab("board", "board"); val(self.board)
        put(w, yy, x + 17 + len(self.board), f"{bcfg.get('part', '')}  {bcfg.get('description', '')}", C["dim"], wd - 19 - len(self.board))
        yy += 1; lab("from", "from"); val(self.frm)
        yy += 1; lab("to", "to"); val(self.to)
        run = core.STAGES[core.STAGES.index(self.frm):core.STAGES.index(self.to) + 1]
        put(w, yy - 1, x + 30, "runs", C["dim"]); put(w, yy, x + 30, " → ".join(run), C["info"], wd - 32)
        # steps: one box per step when wide, one line per step when narrow
        self.wide = wd >= 100
        yy = y + 6; ss = self.stages(); focus = self.ROWS[self.row] == "steps"
        sh = 7 if self.wide else len(ss) + 3
        box(w, yy, x, sh, wd, "STEPS  " + ("←→" if self.wide else "↑↓") + " step · Enter tool · 0 project file", focus)
        st, dn = self.progress()
        bw = max(10, (wd - 4 - 3 * (len(ss) - 1)) // len(ss))
        for i, s in enumerate(ss):
            v, cls, why = self.status(s)
            name = f"auto:{cls.name}" if v == "auto" and cls else v
            col = C["accent"] if v in ("all", "all_open") else C["ok"] if not why else C["bad"]
            if s in dn: mark, mc = "✔", C["ok"]
            elif self.job and self.job.running and st and st[-1] == s: mark, mc = SPIN[int(time.time() * 8) % 10], C["accent"]
            elif self.job and not self.job.running and self.job.rc and st and st[-1] == s: mark, mc = "✘", C["bad"]
            else: mark, mc = "·", C["dim"]
            sel = focus and i == self.si
            if self.wide:
                bx = x + 2 + i * (bw + 3)
                box(w, yy + 1, bx, 4, bw, "", sel)
                put(w, yy + 2, bx + 2, f"{mark} {s}", (mc if s in dn or mark != "·" else 0) | curses.A_BOLD, bw - 3)
                put(w, yy + 3, bx + 2, name + (" *" if s in self.over else ""), col, bw - 3)
                if i < len(ss) - 1: put(w, yy + 3, bx + bw, " ▶ ", C["dim"])
            else:
                ry, rv = yy + 1 + i, curses.A_REVERSE if sel else 0
                put(w, ry, x + 1, " " * (wd - 2), rv)
                put(w, ry, x + 2, mark, mc | rv); put(w, ry, x + 4, f"{s:<8}", curses.A_BOLD | rv)
                nm = (name + (" *" if s in self.over else ""))[:24]
                put(w, ry, x + 13, f"{nm:<25}", col | rv)
                put(w, ry, x + 39, "✔ can run" if not why else f"✘ {why}", (C["ok"] if not why else C["bad"]) | rv, wd - 41)
        s = ss[self.si]; v, cls, why = self.status(s)
        info = self.err or (f"{s}: {v}" + (f" → {cls.label()}" if cls and v != cls.name else "") + ("   ✔ can run" if not why else f"   ✘ {why}"))
        put(w, yy + sh - 2, x + 2, info, C["bad"] if (self.err or why) else C["dim"], wd - 4)
        # logs: flow output, and the log of the tool running now
        ly = yy + sh; lh = h - (ly - y)
        if lh < 4: return
        if time.time() - self.toollog_t > 1.5:
            self.toollog_t = time.time(); d = ROOT / "build" / self.design / self.board
            logs = [q for q in d.rglob("*.log") if q.name != "flow.log"] if d.exists() else []
            newest = max(logs, key=lambda q: q.stat().st_mtime, default=None)
            self.toollog = ([f"── {rel(newest)}"] + tail(newest)) if newest else []
        tl = lambda X, W, t: textpane(w, ly, X, lh, W, self.toollog or ["", "  no tool log yet"], t, False, self.scroll if self.logview == "tool" else 0)
        if wd >= 120:
            lw = wd // 2
            self.log(w, ly, x, lh, lw, "flow"); tl(x + lw, wd - lw, "tool log")
        elif self.logview == "tool": tl(x, wd, "tool log  (l: flow log)")
        else: self.log(w, ly, x, lh, wd, "flow  (l: tool log)")

class Builds(Tab):
    """Every build: steps, area, timing, flow log; program its bitstream."""
    title, icon = "Builds", "▤"
    VIEWS = ["summary", "flow.log", "area", "timing", "summary.md"]
    def __init__(self, app): super().__init__(app); self.lv, self.view = ListView(), 0
    def cur(self):
        bl = builds(); return bl[self.lv.i] if bl and self.lv.i < len(bl) else None
    def text(self, d):
        rp = d / "report"
        v = self.VIEWS[self.view]
        if v == "summary":
            os.environ["COLUMNS"] = str(self.width)  # cli panels size themselves to the terminal: here, to this pane
            try: return T.plain(cli.show(d.parent.name, d.name, banner=False)).splitlines()
            finally: os.environ.pop("COLUMNS", None)
        f = {"flow.log": d / "flow.log", "area": rp / "reports" / "area.rpt", "timing": rp / "reports" / "timing.rpt", "summary.md": rp / "summary.md"}[v]
        return tail(f, 2000) or [f"no {rel(f)}"]
    def upload(self):
        d = self.cur()
        if not d: return
        bit = cli.build_info(d)[1]
        if not bit: self.app.flash("this build has no bitstream", C["bad"]); return
        design = d.parent.name if d.parent.name in designs() else next(iter(designs()))
        self.run(["make", "upload", f"DESIGN={design}", f"TARGET={d.name}", f"BIT={rel(bit)}"], f"upload {d.parent.name} → {d.name}")
    def rerun(self):
        d = self.cur()
        if d and d.parent.name in designs():
            self.run(["make", "flow", f"DESIGN={d.parent.name}", f"TARGET={d.name}"], f"flow {d.parent.name} → {d.name}")
    def keys(self):
        return [("v", "next view", lambda: setattr(self, "view", (self.view + 1) % len(self.VIEWS))),
                ("u", "program board", self.upload), ("r", "run again", self.rerun), ("x", "stop", self.stop)]
    def key(self, k):
        if k in (curses.KEY_LEFT, curses.KEY_RIGHT): self.view = (self.view + (1 if k == curses.KEY_RIGHT else -1)) % len(self.VIEWS); self.scroll = 0; return True
        if self.lv.move(k, len(builds())): self.scroll = 0; return True
        return super().key(k)
    def draw(self, w, y, x, h, wd):
        bl = builds()
        (ly, lx, lh, lw), (ry, rx, rh, rw) = split(y, x, h, wd, min(52, wd // 3), min(len(bl) + 2, max(5, h // 3)))
        box(w, ly, lx, lh, lw, f"BUILDS ({len(bl)})  ↑↓", True)
        rows = []
        for d in bl:
            st, bit, _, ts = cli.build_info(d); st = T.plain(st)
            ic, c = ("✔", C["ok"]) if st == "finished" else ("✘", C["bad"]) if st == "FAILED" else ("…", C["warn"])
            rows.append([(f" {ic} ", c), (f"{d.parent.name}/{d.name}"[:lw - 21].ljust(lw - 21), 0), (cli.ago(ts).replace(" ago", "").rjust(9), C["dim"]), (" ◆" if bit else "  ", C["accent"])])
        self.lv.draw(w, ly + 1, lx + 1, lh - 2, lw - 2, rows or [[(" no builds yet", C["dim"])]])
        d = self.cur(); self.width = rw - 4
        tabs = " ".join(f"[{v}]" if i == self.view else v for i, v in enumerate(self.VIEWS))
        jh = min(12, rh // 3) if self.job else 0
        if d: textpane(w, ry, rx, rh - jh, rw, self.text(d), f"←→ {tabs}", False, self.scroll, self.VIEWS[self.view] != "summary.md")
        if self.job: self.log(w, ry + rh - jh, rx, jh, rw)

class Boards(Tab):
    """boards.yml: install boards, see their files and settings, edit the list."""
    title, icon = "Boards", "▣"
    def __init__(self, app): super().__init__(app); self.lv = ListView()
    def cur(self): bs = list(boards_cfg()); return bs[self.lv.i] if bs else None
    def keys(self):
        return [("i", "install this board", lambda: self.cur() and self.run(["make", "install-boards", f"BOARD={self.cur()}"], f"install {self.cur()}")),
                ("a", "install all", lambda: self.run(["make", "install-boards"], "install all boards")),
                ("e", "edit boards.yml", lambda: self.app.edit(ROOT / "boards.yml")),
                ("d", "doctor", lambda: self.cur() and self.run(["make", "doctor", f"TARGET={self.cur()}"], f"doctor {self.cur()}")),
                ("x", "stop", self.stop)]
    def key(self, k):
        if self.lv.move(k, len(boards_cfg())): return True
        return super().key(k)
    def draw(self, w, y, x, h, wd):
        bs = boards_cfg(); inst = installed()
        (ly, lx, lh, lw), (ry, rx, rh, rw) = split(y, x, h, wd, min(46, wd // 3), len(bs) + 2)
        box(w, ly, lx, lh, lw, f"BOARDS.YML ({len([b for b in bs if b in inst])}/{len(bs)} installed)", True)
        rows = [[(" ● " if b in inst else " ○ ", C["ok"] if b in inst else C["bad"]), (b.ljust(14), curses.A_BOLD), (c.get("part", "")[:lw - 20], C["dim"]),
                 (("  " + c.get("description", "")) if wd < WIDE else "", C["dim"])] for b, c in bs.items()]
        self.lv.draw(w, ly + 1, lx + 1, lh - 2, lw - 2, rows)
        name = self.cur()
        if not name: return
        c = bs[name]; src = c.get("source", {})
        part = c.get("part", "")
        lines = [f"{name}  ·  {c.get('description', '')}", "",
                 f"part        {part}",
                 f"installed   {'yes' if name in inst else 'no: i installs it'}",
                 f"bitstream   {'open (prjxray)' if part.startswith('xc7') else 'open place and route; Vivado only writes it (open_io)'}",
                 f"source      {'XilinxBoardStore: ' + ', '.join([src['store']] if isinstance(src.get('store'), str) else src.get('store', [])) if src.get('store') else src.get('git', '-')}"]
        if src.get("path"): lines.append(f"            path {src['path']}" + (f", xdc {src['xdc']}" if src.get("xdc") else ""))
        extra = {k: v for k, v in c.items() if k not in ("source", "part", "description")}
        if extra: lines += ["", "board settings"] + [f"  {k}: {v}" for k, v in extra.items()]
        if name in inst:
            files = sorted(rel(p) for p in (ROOT / "boards" / name).rglob("*") if p.is_file())
            lines += ["", f"targets/{name}.yml"] + ["  " + l for l in (ROOT / "targets" / f"{name}.yml").read_text().splitlines() if l and not l.startswith("#")]
            lines += ["", "board files"] + [f"  {f}" for f in files]
        jh = min(12, rh // 2) if self.job else 0
        textpane(w, ry, rx, rh - jh, rw, lines, name, False, self.scroll if not self.job else 0, colorize=False)
        if self.job: self.log(w, ry + rh - jh, rx, jh, rw)

class Hardware(Tab):
    """JTAG cables (scan, program, reset) and the UART monitor of their serial ports."""
    title, icon = "Hardware", "⚡"
    def __init__(self, app):
        super().__init__(app)
        self.lv, self.cables, self.scanning, self.uart, self.baud, self.hex, self.line = ListView(), [], False, None, 115200, False, ""
        self.scan()
    def scan(self):
        if self.scanning: return
        self.scanning = True
        def go():
            try: self.cables = upload._scan()
            finally: self.scanning = False
        threading.Thread(target=go, daemon=True).start()
    def items(self):
        """Cables and, under each, its serial ports: [(kind, cable, port)]."""
        out, ps = [], ports()
        for c in self.cables:
            out.append(("cable", c, None))
            out += [("port", c, p) for p in ps if p[1] == c["serial"]]
        known = {c["serial"] for c in self.cables}
        out += [("port", None, p) for p in ps if p[1] not in known]
        return out
    def sel(self):
        it = self.items(); return it[self.lv.i] if it and self.lv.i < len(it) else (None, None, None)
    def boards_of(self, c):
        """Installed boards whose FPGA this cable reports."""
        out = []
        for b in installed():
            try:
                if any(m.startswith(fpga_want(target(b)["part"])) for m in c["models"]): out.append(b)
            except Exception: pass
        return out
    def uart_name(self, c, p):
        for b in self.boards_of(c) if c else []:
            if str(target(b).get("uart_channel", "")) == str(p[2]): return f"PL UART of {b}"
        return ""
    def program(self):
        k, c, _ = self.sel()
        if not c: self.app.flash("select a JTAG cable", C["warn"]); return
        bs = self.boards_of(c)
        opts = []
        for d in builds():
            bit = cli.build_info(d)[1]
            if bit and (d.name in bs or not bs): opts.append((f"{d.parent.name}/{d.name}", str(bit), rel(bit), 0))
        opts.append(("other file…", "", "type a path", C["dim"]))
        v = modal_pick(self.app, f"bitstream for {c['serial']} ({', '.join(c['models']) or '?'})", opts)
        if v == "": v = modal_text(self.app, "bitstream file")
        if v: self.run(["openFPGALoader", "-c", c["cable"], "--busdev-num", c["busdev"], v], f"program {c['serial']}")
    def reset_pl(self):
        k, c, _ = self.sel()
        if c and confirm(self.app, f"reset the FPGA on {c['serial']}? (clears the loaded bitstream)"):
            self.run(["openFPGALoader", "-c", c["cable"], "--busdev-num", c["busdev"], "--reset"], f"reset PL {c['serial']}")
    def reset_sys(self):
        k, c, _ = self.sel()
        viv = core.find_vivado()
        xsdb = shutil.which("xsdb") or (str(pathlib.Path(shutil.which(viv) or viv).parent / "xsdb") if viv else None)
        if not c or not xsdb or not os.path.exists(xsdb): self.app.flash("system reset needs a cable and Vivado's xsdb", C["bad"]); return
        if not confirm(self.app, f"reset the whole board (PS and PL) on {c['serial']}? (xsdb, vivado)"): return
        tcl = pathlib.Path(tempfile.mkdtemp()) / "reset.tcl"
        tcl.write_text("connect\n"
                       f"targets -set -nocase -filter {{jtag_cable_serial =~ \"*{c['serial'].rstrip('A')}*\" && (name =~ \"PSU\" || name =~ \"APU\")}}\n"
                       "rst -system\nafter 500\ndisconnect\n")
        self.run([xsdb, tcl], f"reset system {c['serial']} (vivado)")
    def toggle_uart(self):
        if self.uart: self.uart.close(); self.uart = None; return
        k, c, p = self.sel()
        if k != "port": self.app.flash("select a serial port (under its cable)", C["warn"]); return
        try: self.uart = Uart(p[0], self.baud)
        except Exception as e: self.app.flash(f"cannot open {p[0]}: {e}", C["bad"])
    def set_baud(self):
        v = modal_pick(self.app, "baud rate", [(str(b), b, "", 0) for b in BAUDS], self.baud)
        if v:
            self.baud = v
            if self.uart: p = self.uart.port; self.uart.close(); self.uart = Uart(p, v)
    def loopback(self):
        k, c, p = self.sel()
        if self.uart: self.uart.close(); self.uart = None  # the test opens the port itself
        self.run(["make", "uart-test", *([f"PORT={p[0]}"] if p else []), f"BAUD={self.baud}"], "uart loopback test")
    def keys(self):
        return [("s", "scan", self.scan), ("p", "program", self.program), ("R", "reset PL", self.reset_pl), ("Y", "reset system (vivado)", self.reset_sys),
                ("o", "open/close UART", self.toggle_uart), ("b", "baud", self.set_baud), ("i", "type", self.typing),
                ("h", "hex", lambda: setattr(self, "hex", not self.hex)), ("t", "loopback test", self.loopback),
                ("C", "clear", lambda: self.uart and self.uart.data.clear()), ("x", "stop", self.stop)]
    def typing(self):
        if not self.uart: self.app.flash("open a UART first (o)", C["warn"]); return
        self.capture, self.line = True, ""
    def key(self, k):
        if self.capture:
            if k == 27: self.capture = False
            elif k in KEYNAMES["Enter"]: self.uart.send((self.line + "\n").encode()); self.line = ""
            elif k in (curses.KEY_BACKSPACE, 127, 8): self.line = self.line[:-1]
            elif 32 <= k < 127: self.line += chr(k)
            return True
        if self.lv.move(k, len(self.items())): return True
        return super().key(k)
    def draw(self, w, y, x, h, wd):
        its = self.items()
        rows = []
        for kind, c, p in its:
            if kind == "cable":
                ok = bool(c["models"])
                rows.append([(" ◆ ", C["accent"] if ok else C["bad"]), (c["serial"].ljust(14), curses.A_BOLD), (", ".join(c["models"]) or ("no access: permissions?" if re.search(r"denied|usb_open|claim", c["err"]) else "no FPGA answered"), C["ok"] if ok else C["bad"])])
                bs = self.boards_of(c)
                rows.append([("     ", 0), (f"{c['product'][:22]} · USB {c['busdev']}" + (f" · {', '.join(bs)}" if bs else ""), C["dim"])])
            else:
                u = self.uart_name(c, p) if c else ""
                rows.append([("   └ ", C["dim"]), (p[0].ljust(14), C["info"]), (f"if {p[2]}  {u}", C["ok"] if u else C["dim"])])
        (ly, lx, lh, lw), (ry, rx, rh, rw) = split(y, x, h, wd, min(60, wd // 2 - 4), min(len(rows) + 2, h // 2))
        box(w, ly, lx, lh, lw, ("JTAG " + SPIN[int(time.time() * 8) % 10] + " scanning") if self.scanning else f"JTAG CABLES ({len(self.cables)})  ↑↓", True)
        # the list moves on items; cable rows take two lines: map the selection to the drawn rows
        sel_row, r = 0, 0
        for i, (kind, _, _) in enumerate(its):
            if i == self.lv.i: sel_row = r
            r += 2 if kind == "cable" else 1
        lv = ListView(); lv.i = sel_row
        lv.draw(w, ly + 1, lx + 1, lh - 2, lw - 2, rows or [[(" no FTDI JTAG cable found (s rescans)" if not self.scanning else " scanning USB…", C["dim"])]])
        # UART monitor above, JTAG command log below
        jh = 10 if wd >= WIDE else max(5, min(8, rh // 3)); uh = rh - jh
        if self.uart:
            data = bytes(self.uart.data)
            if self.hex: lines = [" ".join(f"{b:02x}" for b in data[i:i + 16]) + "  " + "".join(chr(b) if 32 <= b < 127 else "." for b in data[i:i + 16]) for i in range(max(0, len(data) - 16 * 400), len(data), 16)]
            else: lines = data.decode(errors="replace").replace("\r\n", "\n").replace("\r", "\n").split("\n")[-2000:]
            title = f"UART {self.uart.port} · {self.baud} · rx {len(data)} B · tx {self.uart.sent} B" + (" · HEX" if self.hex else "") + (f"  ✘ {self.uart.err}" if self.uart.err else "")
            textpane(w, ry, rx, uh - 3, rw, lines, title, True, self.scroll, colorize=False)
            box(w, ry + uh - 3, rx, 3, rw, "send: i to type" if not self.capture else "typing: Enter sends · Esc stops", self.capture)
            put(w, ry + uh - 2, rx + 2, ("› " + self.line + ("█" if self.capture else "")), C["accent"] if self.capture else C["dim"], rw - 4)
        else:
            textpane(w, ry, rx, uh, rw, ["UART closed: select a port under its cable and press o", f"baud {self.baud} (b changes it)",
                                         "'PL UART of <board>' ports are wired to the FPGA"], "UART", False, colorize=False)
        self.log(w, ry + uh, rx, jh, rw, "jtag")

class Tools(Tab):
    """tools.lock: status, install, update to the latest version; environment; doctor."""
    title, icon = "Tools", "⚒"
    INSTALL = {"prjxray": "install-xc7", "prjxray-db": "install-xc7", "nextpnr-xilinx": "install-xc7", "dreamplacefpga": "install-dreamplace",
               "nextpnr-fpga-interchange": "install-interchange", "python-fpga-interchange": "install-interchange",
               "fpga-interchange-schema": "install-interchange", "prjuray": "install-prjuray", "prjuray-db": "install-prjuray"}
    def __init__(self, app): super().__init__(app); self.lv = ListView()
    def cur(self):
        ts = self.app.cache("tools", cli.tool_status); return ts[self.lv.i] if ts else None
    def install(self):
        t = self.cur()
        if t: self.run(["make", self.INSTALL.get(t["name"], "install")], f"{self.INSTALL.get(t['name'], 'install')} ({t['name']})"); self.app.uncache("tools")
    def update(self):
        t = self.cur()
        if t and confirm(self.app, f"move {t['name']} to its latest upstream commit in tools.lock?"):
            self.run(["make", "update", f"NAME={t['name']}"], f"update {t['name']}"); self.app.uncache("tools")
    def keys(self):
        return [("i", "install this", self.install),
                ("I", "install everything", lambda: confirm(self.app, "run make install (long)?") and self.run(["make", "install"], "install everything")),
                ("o", "outdated", lambda: self.run(["make", "outdated"], "outdated tools")), ("u", "update", self.update),
                ("k", "check deps", lambda: self.run(["make", "check-deps"], "check deps")),
                ("d", "doctor", lambda: self.run(["make", "doctor"], "doctor, all boards")),
                ("r", "refresh", lambda: (self.app.uncache("tools"), self.app.load_env())), ("x", "stop", self.stop)]
    def key(self, k):
        if self.lv.move(k, len(self.app.cache("tools", cli.tool_status))): return True
        return super().key(k)
    def draw(self, w, y, x, h, wd):
        ts = self.app.cache("tools", cli.tool_status)
        env = self.app.env
        er = [f"{'●' if ok else '○'} {n:<18} {v:<10} {wh.replace(os.path.expanduser('~'), '~')}" for n, ok, v, wh in env] if env else ["  checking…"]
        lh = len(ts) + 2; wide = wd >= WIDE; lw = min(64, wd // 2) if wide else wd
        box(w, y, x, lh, lw, "TOOLS.LOCK  ↑↓", True)
        rows = [[(" ● " if t["ok"] else " ○ ", C["ok"] if t["ok"] else C["bad"]), (t["name"].ljust(26), curses.A_BOLD),
                 ((t["sha"] or "-").ljust(11), C["dim"]), ("pinned" if t["pinned"] else "latest", C["warn"] if t["pinned"] else C["info"]),
                 (("  " + t["role"]) if not wide else "", C["dim"])] for t in ts]
        self.lv.draw(w, y + 1, x + 1, lh - 2, lw - 2, rows)
        t = self.cur()
        follows = lambda t: f"pinned {t['ref'][:12]} (on purpose)" if t["pinned"] else "latest commit of the default branch"
        if wide:
            if t:
                info = [f"{t['name']}", f"  role      {t['role']}", f"  source    {t['url']}", f"  follows   {follows(t)}",
                        f"  checkout  {t['sha'] or 'not fetched'}", f"  status    {'ready' if t['ok'] else 'missing: i installs it'}",
                        f"  install   make {self.INSTALL.get(t['name'], 'install')}"]
                textpane(w, y + lh, x, min(len(info) + 2, h - lh), lw, info, "DETAILS", False, colorize=False)
            textpane(w, y, x + lw, len(er) + 2, wd - lw, er, "ENVIRONMENT", False, colorize=False)
            self.log(w, y + len(er) + 2, x + lw, h - len(er) - 2, wd - lw)
            return
        yy = y + lh
        if t and h - (yy - y) >= 9:
            info = [f"{t['url']}", f"{follows(t)} · install: make {self.INSTALL.get(t['name'], 'install')}"]
            textpane(w, yy, x, 4, wd, info, t["name"], False, colorize=False); yy += 4
        if h - (yy - y) >= len(er) + 6:
            textpane(w, yy, x, len(er) + 2, wd, er, "ENVIRONMENT", False, colorize=False); yy += len(er) + 2
        if h - (yy - y) >= 4: self.log(w, yy, x, h - (yy - y), wd)

TABS = [Home, Flow, Builds, Boards, Hardware, Tools]  # add a tab here

# ------------------------------------------------------------------ application
class App:
    def __init__(self, scr):
        self.scr, self.jobs, self.msg, self._cache, self.env = scr, [], ("", 0, 0), {}, None
        init_colors(); curses.curs_set(0); scr.keypad(True); scr.timeout(200)
        curses.mousemask(curses.ALL_MOUSE_EVENTS); curses.mouseinterval(0)  # click a tab, wheel scrolls (Shift+drag still selects text)
        self.tab_y, self.tab_x = -1, []
        self.sha = cli.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"])
        self.load_env()
        self.tabs = [cls(self) for cls in TABS]; self.cur = 0
    def load_env(self):
        def go(): self.env = cli.env_status()
        threading.Thread(target=go, daemon=True).start()
    def cache(self, k, fn):
        if k not in self._cache: self._cache[k] = fn()
        return self._cache[k]
    def uncache(self, k): self._cache.pop(k, None)
    def start(self, cmd, title):
        j = Job(cmd, title); self.jobs.append(j); self.flash(f"▶ {title}", C["accent"]); return j
    def flash(self, text, attr=0): self.msg = (text, attr, time.time())
    def edit(self, path):
        """Open a file in $EDITOR (outside curses), then come back."""
        curses.endwin()
        subprocess.call([os.environ.get("EDITOR") or shutil.which("nano") or "vi", str(path)])
        self.scr.refresh(); self._cache.clear()
    def header(self, w):
        h = self.scr.getmaxyx()[0]
        if h < 40 or w < 100:  # compact: one line
            put(self.scr, 0, 1, "◆ FREISA", C["accent"] | curses.A_BOLD)
            put(self.scr, 0, 11, cli.TAGLINE if w >= 100 else "open RTL → bitstream", C["dim"], w - 22)
            put(self.scr, 0, w - 10, f"{self.sha or '':>8}", C["dim"])
            return 1
        art = cli.BANNER.strip("\n").splitlines()
        for r, l in enumerate(art):
            for c0 in range(0, len(l), 8):  # gradient left to right
                put(self.scr, r, 2 + c0, l[c0:c0 + 8], C["grad"][min(5, c0 // 8)])
        ax = 2 + max(map(len, art)) + 3
        if w > ax + 60:
            for r, l in enumerate(CHIP): put(self.scr, r, ax, l, C["dim"])
            ax += 18
        put(self.scr, 1, ax, cli.TAGLINE, curses.A_BOLD, w - ax - 1)
        put(self.scr, 2, ax, "open-source RTL → bitstream, step by step, on FPGA Interchange", C["dim"], w - ax - 1)
        put(self.scr, 4, ax, f"{str(ROOT).replace(os.path.expanduser('~'), '~')}  ·  commit {self.sha or '-'}", C["dim"], w - ax - 1)
        return len(art) + 1

    def tabbar(self, y, w):
        busy = lambda t: t.job and t.job.running
        def label(i, t, lvl):  # lvl 0: icon and title, 1: title, 2: short title (narrow terminals)
            name = t.title if lvl < 2 or i == self.cur else t.title[:3]
            return f" {i + 1}{(' ' + t.icon) if lvl == 0 else ''} {name}{' ' + SPIN[int(time.time() * 8) % 10] if busy(t) else ''} "
        lvl = next((l for l in (0, 1) if sum(len(label(i, t, l)) + 1 for i, t in enumerate(self.tabs)) < w - 2), 2)
        x = 1; self.tab_y, self.tab_x = y, []
        for i, t in enumerate(self.tabs):
            s = label(i, t, lvl)
            put(self.scr, y, x, s, C["tab"] if i == self.cur else (C["accent"] if busy(t) else C["dim"]))
            self.tab_x.append((x, x + len(s))); x += len(s) + 1
        text, attr, ts = self.msg
        if text and time.time() - ts < 4 and x + 4 < w: put(self.scr, y, max(x + 2, w - len(text) - 3), f" {text} ", attr | curses.A_BOLD, w - x - 3)
        put(self.scr, y + 1, 0, "─" * w, C["accent"])

    def footer(self, y, w):
        """Key hints of the tab (and the global keys if they fit) on two lines: y and y + 1."""
        t = self.tabs[self.cur]
        own = [(k, hnt) for k, hnt, _ in t.keys()]
        def wrap(parts, gap):
            lines, cur = [[]], 1
            for k, hnt in parts:
                n = len(k) + len(hnt) + 3 + gap  # " k " + " hint" + gap
                if cur + n > w - 1: lines.append([]); cur = 1
                lines[-1].append((k, hnt)); cur += n
            return lines
        for parts, gap in ((own + [("Tab", "tabs"), ("?", "help"), ("q", "quit")], 2), (own + [("?", "help")], 2), (own, 1)):
            lines = wrap(parts, gap)
            if len(lines) <= 2: break
        lines = lines[:2]  # still too long: the rest is in the help (?)
        for r, ln in enumerate(lines):
            x = 1; yy = y + r + (2 - len(lines))
            for k, hnt in ln:
                put(self.scr, yy, x, f" {k} ", C["tab"]); x += len(k) + 2
                put(self.scr, yy, x, f" {hnt}" + " " * gap, C["dim"]); x += len(hnt) + 1 + gap
    def draw(self):
        s = self.scr; s.erase(); h, w = s.getmaxyx()
        if h < 20 or w < 60:
            put(s, 0, 0, f"FREISA needs at least 60x20 (now {w}x{h})", C["warn"]); s.refresh(); return
        y = self.header(w); self.tabbar(y, w); y += 2
        try:
            self.tabs[self.cur].draw(s, y, 0, h - y - 2, w)
        except Exception as e:  # a broken tab must not close the interface
            put(s, y + 1, 2, f"cannot draw this tab: {type(e).__name__}: {e}", C["bad"], w - 4)
        self.footer(h - 2, w); s.refresh()

    def mouse(self, t):
        try: _, mx, my, _, b = curses.getmouse()
        except curses.error: return
        if my == self.tab_y:
            for i, (x0, x1) in enumerate(self.tab_x):
                if x0 <= mx < x1: self.cur = i
        elif b & curses.BUTTON4_PRESSED: t.scroll += 3
        elif b & getattr(curses, "BUTTON5_PRESSED", 0): t.scroll = max(0, t.scroll - 3)
    def help(self):
        lines = [("1-6, Tab, Shift+Tab", "switch tab (or click it)"), ("mouse wheel", "scroll the log or the text"), ("↑↓ / j k", "move in lists"), ("Shift+↑↓ / J K", "scroll the log or the text"),
                 ("Enter", "choose"), ("x", "stop the command of this tab"), ("q", "quit (stops running commands)"),
                 ("", ""), ("add a tab", "freisa/tui.py: subclass Tab, add it to TABS"), ("add a command", "one line in the tab's keys()")]
        own = [(k, hnt) for k, hnt, _ in self.tabs[self.cur].keys()]
        lines = [(f"{self.tabs[self.cur].title} tab", "")] + own + [("", "")] + lines
        modal_pick(self, "FREISA keys", [(f"{a:<20}", None, b, C["accent"]) for a, b in lines])
    def loop(self):
        while True:
            self.draw()
            k = self.scr.getch()
            if k == -1 or k == curses.KEY_RESIZE: continue
            t = self.tabs[self.cur]
            if t.capture: t.key(k); continue
            if k == ord("q"):
                run = [j for j in self.jobs if j.running]
                if not run or confirm(self, f"{len(run)} command(s) running: stop them and quit?"):
                    for j in run: j.kill()
                    for tb in self.tabs:
                        if getattr(tb, "uart", None): tb.uart.close()
                    return
            elif k == 9: self.cur = (self.cur + 1) % len(self.tabs)
            elif k == curses.KEY_BTAB: self.cur = (self.cur - 1) % len(self.tabs)
            elif ord("1") <= k < ord("1") + len(self.tabs): self.cur = k - ord("1")
            elif k == ord("?"): self.help()
            elif k == curses.KEY_MOUSE: self.mouse(t)
            else: t.key(k)

def main():
    os.environ.setdefault("ESCDELAY", "25")  # Esc reacts at once
    curses.wrapper(lambda scr: App(scr).loop())
