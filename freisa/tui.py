# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive terminal interface (curses): browse the dashboard panels and run every make target from a menu.
#            Start it with `python freisa.py`. To add something, add one line to VIEWS, ACTIONS or PARAMS below.
# Module   : tui.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import curses, os, subprocess, yaml
from . import cli, term as T
from .core import STAGES

ROOT = cli.ROOT

# ------------------------------------------------------------------ what the menu offers (edit here)
# PARAMS: make variable -> function giving its choices (None: free text, empty = default)
def _designs(): return sorted(f.stem for f in (ROOT / "designs").rglob("*.yml"))
def _boards():  return list(((yaml.safe_load(open(ROOT / "boards.yml")) or {}).get("boards") or {}))
def _tools():   return [l.split()[0] for l in (ROOT / "tools.lock").read_text().splitlines() if l.strip() and not l.startswith("#")]
def _builds():  return sorted(f"{p.parent.name}/{p.name}" for p in (ROOT / "build").glob("*/*") if (p / "flow.log").exists())

PARAMS = {
    "DESIGN": _designs, "TARGET": _boards, "BOARD": _boards, "NAME": _tools,
    "FROM": lambda: STAGES, "TO": lambda: STAGES[::-1],
    "TOOL": lambda: ["openfpgaloader", "vivado"],
    "JTAG": None, "PORT": None, "BAUD": None, "REF": None, "BUILD": _builds,
}

# VIEWS: menu label -> function returning the text shown on the right
VIEWS = {
    "Environment": cli.env, "Tools": cli.tools, "Boards": cli.boards, "Projects": cli.projects, "Builds": lambda: cli.builds(50),
}

# ACTIONS: (menu label, make target, parameters asked, ask for confirmation)
ACTIONS = [
    ("Run flow",             "flow",           ["DESIGN", "TARGET", "FROM", "TO"], False),
    ("Check tools",          "check",          ["DESIGN", "TARGET"],               False),
    ("Doctor (all boards)",  "doctor",         ["DESIGN"],                         False),
    ("Synthesis only",       "synth",          ["DESIGN", "TARGET"],               False),
    ("Program board",        "upload",         ["DESIGN", "TARGET", "TOOL", "JTAG"], False),
    ("UART test",            "uart-test",      ["TARGET", "PORT", "BAUD"],         False),
    ("Install everything",   "install",        [],                                 True),
    ("Install boards",       "install-boards", ["BOARD"],                          False),
    ("Outdated tools",       "outdated",       [],                                 False),
    ("Update a tool",        "update",         ["NAME", "REF"],                    True),
    ("Remove build outputs", "clean",          [],                                 True),
]

# ------------------------------------------------------------------ interface
def _menu():
    items = [("head", "VIEW")] + [("view", k) for k in VIEWS] + [("view", "Build details")]
    return items + [("head", "RUN")] + [("act", a) for a in ACTIONS] + [("head", ""), ("quit", "Quit")]

def _label(kind, x): return x[0] if kind == "act" else x

def _pick(scr, title, choices):
    """Popup list; returns the choice, "" for the default, None on Esc."""
    choices = ["(default)"] + choices
    i = 0
    while True:
        h, w = scr.getmaxyx()
        n = min(len(choices), h - 4); bw = min(w - 4, max(len(title), *map(len, choices)) + 6)
        win = curses.newwin(n + 2, bw, (h - n - 2) // 2, (w - bw) // 2); win.keypad(True); win.box()
        win.addstr(0, 2, f" {title} ", curses.color_pair(1) | curses.A_BOLD)
        top = max(0, i - n + 1)
        for r, c in enumerate(choices[top:top + n]):
            win.addstr(r + 1, 2, c[:bw - 4], curses.A_REVERSE if top + r == i else 0)
        k = win.getch()
        if k in (curses.KEY_UP, ord("k")): i = (i - 1) % len(choices)
        elif k in (curses.KEY_DOWN, ord("j")): i = (i + 1) % len(choices)
        elif k in (10, 13, curses.KEY_ENTER): return "" if i == 0 else choices[i]
        elif k == 27: return None

def _ask(scr, title):
    """Popup text field; empty = default, None on Esc."""
    h, w = scr.getmaxyx(); bw = min(w - 4, 60)
    win = curses.newwin(3, bw, h // 2 - 1, (w - bw) // 2); win.box()
    win.addstr(0, 2, f" {title} (empty = default, Esc = cancel) "[:bw - 4], curses.color_pair(1) | curses.A_BOLD)
    curses.curs_set(1); s = ""
    while True:
        win.addstr(1, 2, s.ljust(bw - 4)[:bw - 4]); win.move(1, 2 + min(len(s), bw - 5))
        k = win.getch()
        if k == 27: curses.curs_set(0); return None
        if k in (10, 13): curses.curs_set(0); return s.strip()
        if k in (8, 127, curses.KEY_BACKSPACE): s = s[:-1]
        elif 32 <= k < 127: s += chr(k)

def _param(scr, name):
    src = PARAMS.get(name)
    return _pick(scr, name, src()) if src else _ask(scr, name)

def _run(scr, cmd):
    """Leave curses, run the command in the normal terminal (its own colors and progress), come back on Enter."""
    curses.endwin()
    print(T.orange("▶ ") + T.bold(" ".join(cmd)) + "\n", flush=True)
    rc = subprocess.call(cmd, cwd=ROOT)
    print("\n" + (T.OK + " done" if rc == 0 else T.FAIL + f" exit code {rc}"))
    input(T.dim("Enter to go back to FREISA "))
    scr.refresh()

def _content(kind, x):
    try:
        if kind == "view" and x in VIEWS: return VIEWS[x]()
        if kind == "view": return "Enter: choose a build and show its steps, area, timing and files."
        if kind == "act":
            label, target, ps, _ = x
            return f"make {target}" + "".join(f" {p}=…" for p in ps) + "\n\nEnter: choose the parameters and run it."
    except Exception as e:  # a broken view must not close the interface
        return f"cannot show this: {e}"
    return ""

def _draw(scr, items, sel, text, scroll):
    scr.erase(); h, w = scr.getmaxyx()
    for r, l in enumerate(cli.BANNER_PLAIN.strip("\n").splitlines()[:5]):
        scr.addstr(r, 1, l[:w - 2], curses.color_pair(1) | curses.A_BOLD)
    scr.addstr(5, 1, cli.TAGLINE[:w - 2], curses.A_DIM)
    mw = 26; y0 = 7
    for r, (kind, x) in enumerate(items[:h - y0 - 1]):
        if kind == "head": scr.addstr(y0 + r, 1, x, curses.color_pair(1) | curses.A_BOLD); continue
        attr = curses.A_REVERSE if r == sel else 0
        scr.addstr(y0 + r, 2, (" " + _label(kind, x)).ljust(mw - 2)[:mw - 2], attr)
    lines = T.plain(text).splitlines()
    for r, l in enumerate(lines[scroll:scroll + h - y0 - 1]):
        scr.addstr(y0 + r, mw + 1, l[:w - mw - 2])
    scr.addstr(h - 1, 1, "↑↓ move  Enter select  PgUp/PgDn scroll  r refresh  q quit"[:w - 2], curses.A_DIM)
    scr.refresh()

def _loop(scr):
    curses.curs_set(0); curses.use_default_colors()
    curses.init_pair(1, 214 if curses.COLORS >= 256 else curses.COLOR_YELLOW, -1)
    items = _menu(); sel = 1; scroll = 0; cache = {}
    while True:
        kind, x = items[sel]
        key = _label(kind, x)
        if key not in cache: cache[key] = _content(kind, x)
        _draw(scr, items, sel, cache[key], scroll)
        k = scr.getch()
        if k in (ord("q"), 27): return
        step = {curses.KEY_UP: -1, ord("k"): -1, curses.KEY_DOWN: 1, ord("j"): 1}.get(k)
        if step:
            sel = (sel + step) % len(items)
            while items[sel][0] == "head": sel = (sel + step) % len(items)
            scroll = 0
        elif k == curses.KEY_NPAGE: scroll += 10
        elif k == curses.KEY_PPAGE: scroll = max(0, scroll - 10)
        elif k == ord("r"): cache.clear()
        elif k in (10, 13, curses.KEY_ENTER):
            if kind == "quit": return
            if kind == "view" and x == "Build details":
                b = _pick(scr, "build", _builds())
                if b: cache[key] = cli.show(*b.split("/"))
            elif kind == "act":
                label, target, ps, confirm = x
                args = []
                for p in ps:
                    v = _param(scr, p)
                    if v is None: break
                    if v: args.append(f"{p}={v}")
                else:
                    if confirm and _pick(scr, f"{label}: sure?", ["yes"]) != "yes": continue
                    _run(scr, ["make", target, *args]); cache.clear()

def main():
    os.environ.setdefault("ESCDELAY", "25")  # Esc reacts at once
    curses.wrapper(_loop)
