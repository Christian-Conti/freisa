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
os.environ["PATH"] = f"{HERE / 'install' / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"  # tools built by `make install`

class Resolved:
    def __init__(self, design, target_name):
        core.load_backends()
        # `design` may be a project name (any designs/**/<name>.yml), a relative or an absolute path to a yml
        d = design.strip('"')
        if d.startswith("designs//"): d = d[len("designs/"):]  # Makefile DESIGN_DIR prefix in front of an absolute path
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
        self.steps = {**(self.flow.get("steps") or {}), **((self.flow.get("boards") or {}).get(target_name) or {})}
        self.steps["sources"] = "core" if "core" in self.flow else "files"
        self.explore_all = sorted(s for s, v in self.steps.items() if v == "all")
        self.sel = {s: core.pick(s, "auto" if self.steps.get(s) == "all" else self.steps.get(s, "auto"), self.target) for s in core.STAGES + ["upload"]}
        # design overrides: `<board>` always, `<board>@<tool>` when that tool runs in some step
        pt = self.flow.get("per_target", {})
        self.flow.update(pt.get(target_name, {}))
        for tool in sorted({b.name for b in self.sel.values()}):
            self.flow.update(pt.get(f"{target_name}@{tool}", {}))
        r = (self.dpath.parent / self.flow["repo"]).resolve()
        self.root = r if r.exists() else (HERE / "designs" / self.flow["repo"]).resolve()
