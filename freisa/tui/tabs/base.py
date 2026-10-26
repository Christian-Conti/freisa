# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive interface: base class of a tab (its keys, its background command and log pane).
# Module   : base.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, textwrap, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from ... import cli, core, resolve, term as T
from ...stages import upload
from ..data import *
from ..draw import *
from ..jobs import *

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
        u = j.usage() if j.running else None
        res = f" · cpu {u[0]:.0f}% · mem {u[1]:.1f}G" if u else ""
        peak = f" · peak {j.peak:.1f}G" if getattr(j, "peak", 0) else ""
        st = (f"{SPIN[int(time.time() * 8) % 10]} {fmt(j.elapsed())}{res}{peak}" if j.running
              else ("✔" if j.rc == 0 else f"✘ {j.rc}") + f" in {fmt(j.elapsed())}{peak}")
        textpane(w, y, x, h, wd, list(j.lines), f"{title}: {j.title}  {st}", j.running, self.scroll)
