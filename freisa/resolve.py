# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Resolves project file + board into the configuration and the selected backends (shared by flow.py and check_flow.py).
# Module   : resolve.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import os, pathlib, sys
from . import core

HERE = pathlib.Path(__file__).resolve().parent.parent
os.environ["PATH"] = f"{HERE / 'install' / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"  # tools built by `freisa.py install`

class Resolved:
    def __init__(self, design, target_name, steps=None):
        core.load_backends()
        # `design` may be a project name (any designs/**/<name>.yml), a relative or an absolute path to a yml
        d = design.strip('"')
        nm = pathlib.Path(d).stem if d.endswith(".yml") else pathlib.Path(d).name
        found = sorted((HERE / "designs").rglob(f"{nm}.yml"))
        self.dpath = pathlib.Path(d) if pathlib.Path(d).is_file() else (found[0] if found else None)
        if self.dpath is None:
            known = ", ".join(sorted(p.stem for p in (HERE / "designs").rglob("*.yml")))
            sys.exit(f"design '{design}' not found under designs/; available: {known}")
        tpath = HERE / "targets" / f"{target_name}.yml"
        if not tpath.is_file():
            sys.exit(f"board '{target_name}' not found; supported: {', '.join(sorted(p.stem for p in (HERE / 'targets').glob('*.yml')))}")
        defaults = core.load_yaml(HERE / "defaults.yml")
        self.flow = {**defaults, **core.load_yaml(self.dpath)}
        self.target = core.load_yaml(tpath)
        self.target_name, self.name = target_name, self.dpath.stem
        # tools per step come from the project file: `steps` (all boards), then `boards.<target>` (this board);
        # a step not listed is `auto` (first open tool that works on the board); `all` explores every tool that works
        self.steps = {**(self.flow.get("steps") or {}), **((self.flow.get("boards") or {}).get(target_name) or {}), **(steps or {})}  # steps: command line (STEPS=)
        self.steps["sources"] = "edam" if "edam" in self.flow else "filelist" if "filelist" in self.flow else "core" if "core" in self.flow else "files"
        # `all`: every tool that works on the board; `all_open`: the same without tools that use a vendor tool (Vivado)
        self.explore_all = {s: v for s, v in self.steps.items() if v in ("all", "all_open")}
        self.sel = {s: core.pick(s, "auto" if self.steps.get(s) in ("all", "all_open") else self.steps.get(s, "auto"), self.target) for s in core.STAGES + ["upload"]}
        # design overrides: `<board>` always, `<board>@<tool>` when that tool runs in some step
        pt = self.flow.get("per_target", {})
        self.flow.update(pt.get(target_name, {}))
        for tool in sorted({b.name for b in self.sel.values()}):
            self.flow.update(pt.get(f"{target_name}@{tool}", {}))
        self.flow["_place"] = self.sel["place"].name  # synthesis adapts its netlist to the placer that follows
        # sources from the merged settings (`edam:` / `filelist:` may be per board)
        self.steps["sources"] = "edam" if "edam" in self.flow else "filelist" if "filelist" in self.flow else "core" if "core" in self.flow else "files"
        self.sel["sources"] = core.pick("sources", self.steps["sources"], self.target)
        r = (self.dpath.parent / self.flow["repo"]).resolve()
        self.root = r if r.exists() else (HERE / "designs" / self.flow["repo"]).resolve()

    def problems(self, run):
        """[(step, tool, reason)] that stop the flow over the steps in `run`: tools that cannot run on this board, and the
        rules between steps (shared by `freisa.py check` and the interactive interface)."""
        bad = [(s, self.sel[s].name, why) for s in run if (why := self.sel[s].supports(self.target))]
        if "sources" in run and not any(k in self.flow for k in ("rtl", "core", "edam", "filelist")):  # sources only per board
            boards = ", ".join(k for k in self.flow.get("per_target", {}) if "@" not in k)
            bad.insert(0, ("sources", self.sel["sources"].name, f"the project has no sources for this board (it has them for: {boards or 'none'})"))
        if "place" in run and self.sel["synth"].name == "vivado" and self.sel["place"].name != "vivado" and not bad:
            bad.append(("place", self.sel["place"].name, "the Vivado netlist has cells the open placers cannot place (I/O and clock "
                        "buffers, wide muxes, ...): after synth: vivado use place, route and bitgen: vivado, or synth: yosys"))
        if "bitgen" in run and not bad:  # Vivado only writes bitstreams of in-context designs (pins in `xdc:`, Vivado placement)
            b = self.sel["bitgen"].name
            if b == "vivado" and not self.flow.get("xdc"):
                bad.append(("bitgen", b, "the design has no pin constraints (`xdc:`) for this board: Vivado refuses bitstreams of out-of-context designs"))
            elif b == "vivado" and self.sel["place"].name != "vivado":
                bad.append(("bitgen", b, f"place uses {self.sel['place'].name}, which builds the design without I/O; Vivado needs to place and route it"))
            elif b == "open_io" and not self.flow.get("xdc") and self.flow.get("pins") != "auto":
                bad.append(("bitgen", b, "the design has no pin constraints (`xdc:` with PACKAGE_PIN/IOSTANDARD per port); `pins: auto` only for test builds"))
            elif b == "vivado_wrap" and not self.flow.get("wrap"):
                bad.append(("bitgen", b, "the design has no `wrap:` (I/O wrapper top, its rtl, and the core instance name)"))
        return bad
