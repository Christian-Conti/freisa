# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Tab 1: overview cards, the open flow per board family, every build (reports, program, rerun, delete).
# Module   : home.py
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
from .builds import Builds
from .hardware import Hardware

class Home(Tab):
    title, icon = "Home", "⌂"
    def __init__(self, app): super().__init__(app); self.lv = ListView()
    def builds_tab(self):
        """The build selected here, acted on by the Builds tab (same commands, one place)."""
        b = next(t for t in self.app.tabs if isinstance(t, Builds)); b.lv.i = self.lv.i; return b
    def open(self): self.builds_tab(); self.app.cur = next(i for i, t in enumerate(self.app.tabs) if isinstance(t, Builds))
    def act(self, fn):
        b = self.builds_tab(); fn(b); self.lv.i = b.lv.i
        if b.job: self.job = b.job
    def keys(self):
        return [("Enter", "reports of build", self.open), ("u", "program board", lambda: self.act(Builds.upload)),
                ("r", "run again", lambda: self.act(Builds.rerun)), ("D", "delete build", lambda: self.act(Builds.delete))]
    def key(self, k):
        if self.lv.move(k, len(builds())): return True
        return super().key(k)
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
        # builds: select one, then Enter (reports), u, r, D
        n = max(0, h - (yy - y))
        if n >= 4:
            jh = min(8, n // 3) if self.job else 0
            nw = max(16, min(34, wd - 40)); rows = []
            for d in bl:
                st, bit, tm, ts = cli.build_info(d)
                st = T.plain(st)
                ic, c = ("✔", C["ok"]) if st == "finished" else ("✘", C["bad"]) if st == "FAILED" else ("…", C["warn"])
                rows.append([(f" {ic} ", c), (f"{(d.parent.name + '/' + d.name)[:nw]:<{nw}} ", curses.A_BOLD), (f"{st:<9} {cli.ago(ts):<10} ", C["dim"]),
                             ("◆ bit " if bit else "      ", C["accent"]), (tm, C["dim"])])
            bh = min(n - jh, len(rows) + 2)
            box(w, yy, x + 1, bh, wd - 2, f"BUILDS ({len(bl)})  ↑↓ · Enter reports · u program · r rerun · D delete", True)
            self.lv.draw(w, yy + 1, x + 2, bh - 2, wd - 4, rows or [[(" no builds yet: tab 2 (Flow)", C["dim"])]])
            if self.job: self.log(w, yy + bh, x + 1, jh, wd - 2)
