# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive interface: the application (header, tab bar, footer, keys, mouse, help) and main().
# Module   : app.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, textwrap, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from .. import cli, core, term as T
from .data import *
from .draw import *
from .jobs import *
from .tabs import TABS, Home, Flow, Builds, Boards, Hardware, Tools

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
    def flash(self, text, attr=0, secs=4): self.msg = (text, attr, time.time() + secs)
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
        lvl = next((l for l in (0, 1) if sum(len(label(i, t, l)) + 1 for i, t in enumerate(self.tabs)) < w - 26), 2)  # room left for the resources
        x = 1; self.tab_y, self.tab_x = y, []
        for i, t in enumerate(self.tabs):
            s = label(i, t, lvl)
            put(self.scr, y, x, s, C["tab"] if i == self.cur else (C["accent"] if busy(t) else C["dim"]))
            self.tab_x.append((x, x + len(s))); x += len(s) + 1
        text, attr, until = self.msg
        if not (text and time.time() < until):  # PC resources on every tab, unless a message is shown
            long, short, hot = pc_status()
            text = long if w - x - 4 > len(long) else short if w - x - 4 > len(short) else ""
            attr = C["bad"] if hot > 90 else C["dim"]
        if text and x + 4 < w: put(self.scr, y, max(x + 2, w - len(text) - 3), f" {text} ", attr | curses.A_BOLD, w - x - 3)
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

    def shutdown(self):
        """Stop running commands (they run in their own process group, Ctrl+C does not reach them) and close UARTs."""
        for j in self.jobs: j.kill()
        for j in self.jobs:
            try: j.p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try: os.killpg(j.p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
        for tb in self.tabs:
            if getattr(tb, "uart", None): tb.uart.close()
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
                 ("", ""), ("add a tab", "freisa/tui/tabs/<name>.py: subclass Tab, add it to TABS"), ("add a command", "one line in the tab's keys()")]
        own = [(k, hnt) for k, hnt, _ in self.tabs[self.cur].keys()]
        lines = [(f"{self.tabs[self.cur].title} tab", "")] + own + [("", "")] + lines
        modal_pick(self, "FREISA keys", [(f"{a:<20}", None, b, C["accent"]) for a, b in lines])
    def loop(self):
        while True:
            for j in self.jobs:  # a finished command says how it went, whatever tab is open
                if not j.running and not getattr(j, "told", False):
                    j.told = True
                    why = next((l for l in reversed(j.lines) if re.search(r"\bfail|\berror|✘", l, re.I) and not l.strip().startswith(("✘ exit", "make"))), "")
                    self.flash(f"✔ {j.title}" if j.rc == 0 else f"✘ {j.title}: {why.strip() or f'exit code {j.rc}'}", C["ok"] if j.rc == 0 else C["bad"], 4 if j.rc == 0 else 20)
            self.draw()
            k = self.scr.getch()
            if k == -1 or k == curses.KEY_RESIZE: continue
            t = self.tabs[self.cur]
            if t.capture: t.key(k); continue
            if k == ord("q"):
                run = [j for j in self.jobs if j.running]
                if not run or confirm(self, f"{len(run)} command(s) running: stop them and quit?"): return
            elif k == 9: self.cur = (self.cur + 1) % len(self.tabs)
            elif k == curses.KEY_BTAB: self.cur = (self.cur - 1) % len(self.tabs)
            elif ord("1") <= k < ord("1") + len(self.tabs): self.cur = k - ord("1")
            elif k == ord("?"): self.help()
            elif k == curses.KEY_MOUSE: self.mouse(t)
            else: t.key(k)

def main():
    os.environ.setdefault("ESCDELAY", "25")  # Esc reacts at once
    app = None
    def run(scr):
        nonlocal app
        app = App(scr); app.loop()
    try:
        curses.wrapper(run)
    except KeyboardInterrupt:  # Ctrl+C: leave like q, without the traceback
        pass
    finally:
        if app: app.shutdown()
