# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Tab 2: choose design, board, steps and tools; run with live progress and logs.
# Module   : flow.py
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

class Flow(Tab):
    """Choose design, board, FROM/TO and the tool of every step; run with live progress and logs."""
    title, icon = "Flow", "⚙"
    ROWS = ["design", "board", "from", "to", "steps"]
    def __init__(self, app):
        super().__init__(app)
        self.design = "blinky" if "blinky" in designs() else next(iter(designs()), "")
        self.board = "pynq-z2" if "pynq-z2" in installed() else next(iter(installed()), "")
        self.frm, self.to, self.over, self.row, self.si, self.res, self.err = core.STAGES[0], core.STAGES[-1], {}, 0, 0, None, ""
        self.toollog, self.toollog_t, self.wide, self.logview = [], 0, True, "flow"
        self.resolve()
    def run_stages(self): return core.STAGES[core.STAGES.index(self.frm):core.STAGES.index(self.to) + 1]
    def resolve(self):
        try:
            self.res = resolve.Resolved(self.design, self.board, {k: v for k, v in self.over.items() if k != "upload"}); self.err = ""
            self.bad = {s: why for s, _, why in self.res.problems(self.run_stages())}
        except SystemExit as e:
            self.res, self.err, self.bad = None, T.plain(str(e)), {}
    def problem_with(self, s, v):
        """Why step s cannot run with value v (same rules as `freisa.py check`), or None."""
        if s == "upload": return core.REGISTRY["upload"][v]().supports(target(self.board)) if v in core.REGISTRY["upload"] else None
        try:
            r = resolve.Resolved(self.design, self.board, {**{k: x for k, x in self.over.items() if k != "upload"}, s: v})
        except SystemExit as e:
            return T.plain(str(e)).splitlines()[0]
        run = self.run_stages() if s in self.run_stages() else [s]
        return next((why for st, _, why in r.problems(run) if st == s), None)
    def options(self, s):
        """Every value of one step: auto/all/all_open and the tools, with availability on this board."""
        t = target(self.board); core.load_backends()
        auto = core.pick(s, "auto", t).label()
        out = [("auto", "auto", f"first open tool that works: {auto}", C["info"])]
        if s != "upload":
            out += [("all", "all", "every tool that works, keep the best", C["accent"]),
                    ("all_open", "all_open", "every open tool that works, keep the best", C["accent"])]
        for n, cls in core.REGISTRY[s].items():
            why = cls().supports(t) or self.problem_with(s, n)
            out.append((cls.label(), n, "✔ can run" if not why else f"✘ {why}", C["ok"] if not why else C["bad"]))
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
        return v, cls, (self.bad.get(s) or (cls().supports(target(self.board)) if cls else f"unknown tool {name}"))
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
        return [a for k, v in o.items() for a in ("--step", f"{k}={v}")]
    def base(self): return ["-d", self.design, "-t", self.board]
    def go(self, to=None):
        bad = {k: v for k, v in self.bad.items() if k in self.run_stages()[:self.run_stages().index(to) + 1 if to in self.run_stages() else None]}
        if bad and modal_pick(self.app, f"{', '.join(bad)} cannot run: run anyway?",
                              [("no", False, "", 0)] + [(f"  {k}:", None, v, C["bad"]) for k, v in bad.items()] + [("yes, run", True, "", C["warn"])]) is not True: return
        self.run([*FREISA, "run", *self.base(), "--from", self.frm, "--to", to or self.to, *self.steps_arg()],
                 f"flow {self.design} → {self.board}")
    def check(self): self.run([*FREISA, "check", *self.base(), "--from", self.frm, "--to", self.to, *self.steps_arg()], f"check {self.design} → {self.board}")
    def doctor(self): self.run([*FREISA, "doctor", *self.base()], f"doctor {self.board}")
    def upload(self):
        tool = self.over.get("upload")
        self.run([*FREISA, "upload", *self.base(), *(["--tool", tool] if tool and tool != "auto" else [])], f"upload {self.design} → {self.board}")
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
