# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive interface: colors and drawing helpers (text, boxes, panes, lists) and the popups.
# Module   : draw.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, textwrap, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from .data import *

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

def wrap(line, n):
    """A long line as several rows of n columns; continuation rows keep the indentation (+2)."""
    if len(line) <= n or n < 10: return [line]
    ind = " " * min(len(line) - len(line.lstrip()) + 2, n // 3)
    return textwrap.wrap(line, n, subsequent_indent=ind, break_on_hyphens=False) or [line]

def textpane(w, y, x, h, wd, lines, title="", focus=False, scroll=0, colorize=True):
    """Box with lines (long ones wrapped); scroll = rows up from the end (0 = follow the end)."""
    box(w, y, x, h, wd, title, focus)
    n = h - 2
    rows = [(r, tone(l) if colorize else 0) for l in lines for r in wrap(l, wd - 4)]
    end = max(n, len(rows) - scroll)
    for i, (l, a) in enumerate(rows[max(0, end - n):end]):
        put(w, y + 1 + i, x + 2, l, a, wd - 4)
    if len(rows) > n:
        put(w, y + h - 1, x + wd - 14, f" {max(0, end - n) + 1}-{min(end, len(rows))}/{len(rows)} ", C["dim"])

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
