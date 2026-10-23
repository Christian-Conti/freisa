# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Source collection backends (files, FuseSoC core).
# Module   : sources.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import yaml
from ..core import Backend, backend

@backend
class FusesocCore(Backend):
    """Resolve RTL file list from a FuseSoC .core target (no fusesoc needed)."""
    stage, name = "sources", "core"
    def run(self, ctx):
        core = yaml.safe_load(open(ctx.root / ctx.cfg["core"]))
        tgt = core["targets"][ctx.cfg.get("core_target", "default")]
        files = []
        for fs in tgt["filesets"]:
            for f in core["filesets"][fs]["files"]:
                path, ft = (f, core["filesets"][fs].get("file_type")) if isinstance(f, str) else (
                    list(f)[0], list(f.values())[0].get("file_type"))
                if ft in ("systemVerilogSource", "verilogSource", "vhdlSource"):
                    files.append((str(ctx.root / path), ft))
        ctx.art["rtl"] = files

@backend
class Files(Backend):
    """Plain glob list from the design file (`rtl: [...]`)."""
    stage, name = "sources", "files"
    def run(self, ctx):
        ext = {".v": "verilogSource", ".sv": "systemVerilogSource", ".vhd": "vhdlSource", ".vhdl": "vhdlSource"}
        fs = [f for g in ctx.cfg["rtl"] for f in sorted(ctx.root.glob(g))]
        if not fs: raise SystemExit(f"no RTL matched {ctx.cfg['rtl']} under {ctx.root}")
        ctx.art["rtl"] = [(str(f), ext[f.suffix]) for f in fs]

@backend
class FileList(Backend):
    """File list (`filelist:` in the project, e.g. the .vc/.f FuseSoC writes for Verilator): RTL files, +incdir+/-I and
    +define+/-D, paths relative to the list. `exclude:` globs drop files; non-RTL entries (.vlt, .cc, ...) are skipped."""
    stage, name = "sources", "filelist"
    def run(self, ctx):
        import fnmatch, shlex
        ext = {".v": "verilogSource", ".sv": "systemVerilogSource", ".svh": None, ".vh": None, ".vhd": "vhdlSource", ".vhdl": "vhdlSource"}
        lst = (ctx.root / ctx.cfg["filelist"]).resolve()
        if not lst.exists(): raise SystemExit(f"file list {lst} not found (generate it first, e.g. FuseSoC --setup)")
        base, files, inc, defs = lst.parent, [], [], {}
        for tok in shlex.split(lst.read_text(), comments=True):
            if tok.startswith("+incdir+"): inc += [str((base / d).resolve()) for d in tok[8:].split("+") if d]
            elif tok.startswith("+define+"):
                for d in tok[8:].split("+"):
                    if d: k, _, v = d.partition("="); defs[k] = v or "1"
            elif tok.startswith("-I"): inc.append(str((base / tok[2:]).resolve()))
            elif tok.startswith("-D"): k, _, v = tok[2:].partition("="); defs[k] = v or "1"
            elif not tok.startswith(("-", "+")):
                f = (base / tok).resolve()
                if ext.get(f.suffix) and not any(fnmatch.fnmatch(str(f), "*" + x) for x in ctx.cfg.get("exclude", [])):
                    files.append((str(f), ext[f.suffix]))
        for g in ctx.cfg.get("rtl", []):  # extra files from the project (e.g. FPGA replacements)
            for f in sorted(ctx.root.glob(g)): files.append((str(f), ext[f.suffix]))
        if not files: raise SystemExit(f"no RTL in {lst}")
        ctx.art.update(rtl=files, incdirs=inc, defines={**defs, **ctx.cfg.get("defines", {})})

@backend
class NoNetlist(Backend):
    stage, name = "netlist", "none"
    def run(self, ctx): pass
