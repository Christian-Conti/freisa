# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Tab 4: boards.yml, install boards, see their files and settings.
# Module   : boards.py
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
