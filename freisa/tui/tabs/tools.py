# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Tab 6: tools.lock, install and update tools, environment, doctor.
# Module   : tools.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, textwrap, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from ... import cli, core, resolve, term as T
from ...stages import upload
from ..data import *
from ..draw import *
from ..jobs import *
from .base import Tab

class Tools(Tab):
    """tools.lock: status, install, update to the latest version; environment; doctor."""
    title, icon = "Tools", "⚒"
    INSTALL = {"prjxray": "xc7", "prjxray-db": "xc7", "nextpnr-xilinx": "xc7", "dreamplacefpga": "dreamplace",
               "nextpnr-fpga-interchange": "interchange", "python-fpga-interchange": "interchange",
               "fpga-interchange-schema": "interchange", "prjuray": "prjuray", "prjuray-db": "prjuray"}  # tool -> `freisa.py install` part
    def __init__(self, app): super().__init__(app); self.lv = ListView()
    def cur(self):
        ts = self.app.cache("tools", cli.tool_status); return ts[self.lv.i] if ts else None
    def install(self):
        t = self.cur()
        if t: part = self.INSTALL.get(t["name"], "all"); self.run([*FREISA, "install", part], f"install {part} ({t['name']})"); self.app.uncache("tools")
    def update(self):
        t = self.cur()
        if t and confirm(self.app, f"move {t['name']} to its latest upstream commit in tools.lock?"):
            self.run([*FREISA, "update", t["name"]], f"update {t['name']}"); self.app.uncache("tools")
    def keys(self):
        return [("i", "install this", self.install),
                ("I", "install everything", lambda: confirm(self.app, "install everything (long)?") and self.run([*FREISA, "install"], "install everything")),
                ("o", "outdated", lambda: self.run([*FREISA, "outdated"], "outdated tools")), ("u", "update", self.update),
                ("k", "check deps", lambda: self.run([*FREISA, "install", "deps"], "check deps")),
                ("d", "doctor", lambda: self.run([*FREISA, "doctor"], "doctor, all boards")),
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
                        f"  install   python freisa.py install {self.INSTALL.get(t['name'], 'all')}"]
                textpane(w, y + lh, x, min(len(info) + 2, h - lh), lw, info, "DETAILS", False, colorize=False)
            textpane(w, y, x + lw, len(er) + 2, wd - lw, er, "ENVIRONMENT", False, colorize=False)
            self.log(w, y + len(er) + 2, x + lw, h - len(er) - 2, wd - lw)
            return
        yy = y + lh
        if t and h - (yy - y) >= 9:
            info = [f"{t['url']}", f"{follows(t)} · install: python freisa.py install {self.INSTALL.get(t['name'], 'all')}"]
            textpane(w, yy, x, 4, wd, info, t["name"], False, colorize=False); yy += 4
        if h - (yy - y) >= len(er) + 6:
            textpane(w, yy, x, len(er) + 2, wd, er, "ENVIRONMENT", False, colorize=False); yy += len(er) + 2
        if h - (yy - y) >= 4: self.log(w, yy, x, h - (yy - y), wd)
