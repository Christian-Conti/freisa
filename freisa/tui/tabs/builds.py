# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Tab 3: every build with its summary, logs and reports; program, rerun, delete.
# Module   : builds.py
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
        self.run([*FREISA, "upload", "-d", design, "-t", d.name, "--bit", rel(bit)], f"upload {d.parent.name} → {d.name}")
    def rerun(self):
        d = self.cur()
        if d and d.parent.name in designs():
            self.run([*FREISA, "run", "-d", d.parent.name, "-t", d.name], f"flow {d.parent.name} → {d.name}")
    def keys(self):
        return [("v", "next view", lambda: setattr(self, "view", (self.view + 1) % len(self.VIEWS))),
                ("u", "program board", self.upload), ("r", "run again", self.rerun), ("D", "delete build", self.delete), ("x", "stop", self.stop)]
    def delete(self):
        d = self.cur()
        if d and confirm(self.app, f"delete {rel(d)} (every file of this build)?"):
            shutil.rmtree(d); self.app.flash(f"deleted {rel(d)}", C["warn"])
            if not any(d.parent.iterdir()): d.parent.rmdir()
            self.lv.i = max(0, min(self.lv.i, len(builds()) - 1))
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
