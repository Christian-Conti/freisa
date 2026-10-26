# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Source collection backends (files, FuseSoC core).
# Module   : sources.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import fnmatch, pathlib, yaml
from ..core import Backend, backend

@backend
class FusesocCore(Backend):
    """FuseSoC .core file (`core:`) and target (`core_target:`): `fusesoc run --setup` of that target (dependencies,
    generators, parameters resolved by FuseSoC) into the build folder, then its EDAM file is read as with `edam:`.
    `fusesoc: {conda, env, flags}`: env where fusesoc runs, extra variables, extra `fusesoc run` options."""
    stage, name = "sources", "core"
    def run(self, ctx):
        from ..core import project_env
        f = ctx.root / ctx.cfg["core"]
        vlnv = yaml.safe_load(open(f))["name"]
        o = ctx.cfg.get("fusesoc") or {}
        out = ctx.work / "fusesoc"
        ctx.sh(["fusesoc", "--cores-root", ctx.root, "run", "--setup", "--no-export", "--build-root", out,
                "--target", ctx.cfg.get("core_target", "default"), *o.get("flags", []), vlnv], "fusesoc_setup",
               cwd=ctx.root, env=project_env(o.get("conda"), o.get("env")))
        found = sorted(out.rglob("*.eda.yml"), key=lambda x: x.stat().st_mtime)
        if not found: raise SystemExit(f"fusesoc wrote no EDAM file under {out}")
        read_edam(ctx, found[-1])

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
class Edam(Backend):
    """FuseSoC EDAM file (`edam:` in the project, the <name>.eda.yml that `fusesoc run --setup` writes for a target):
    RTL in order, include dirs and `define parameters. Constraints stay in `xdc:` of the project (one list per board)."""
    stage, name = "sources", "edam"
    def run(self, ctx):
        found = sorted(ctx.root.glob(ctx.cfg["edam"]), key=lambda x: x.stat().st_mtime)  # a glob: the newest (e.g. any core version)
        f = found[-1].resolve() if found else ctx.root / ctx.cfg["edam"]
        if not f.exists(): raise SystemExit(f"EDAM file {f} not found (generate it first: fusesoc run --setup, e.g. in `prepare:`)")
        read_edam(ctx, f)

def read_edam(ctx, f):
    """EDAM file -> ctx.art rtl, incdirs, defines."""
    e, base = yaml.safe_load(open(f)), f.parent
    ext = {"systemVerilogSource": "systemVerilogSource", "verilogSource": "verilogSource", "vhdlSource": "vhdlSource",
           "vhdlSource-2008": "vhdlSource"}
    files, inc = [], []
    for x in e.get("files", []):
        p, ft = str((base / x["name"]).resolve()), x.get("file_type", "")
        if x.get("is_include_file"):
            ds = [str((base / x["include_path"]).resolve())] if x.get("include_path") else [str(pathlib.Path(p).parent)]
            # `include "lib/x.svh"` style: the enclosing include/ folder too (the EDAM file does not carry include_path)
            ds += [str(q) for q in pathlib.Path(p).parents if q.name == "include"][:1]
            inc += [d for d in ds if d not in inc]
        elif any(fnmatch.fnmatch(p, "*" + x) for x in ctx.cfg.get("exclude", [])): continue
        elif ft.split("-")[0] in ("systemVerilogSource", "verilogSource", "vhdlSource"): files.append((p, ext.get(ft, ft.split("-")[0])))
    # as FuseSoC passes them: only parameters with a value; a bool is defined when true
    defs = {k: ("1" if v["default"] is True else str(v["default"])) for k, v in (e.get("parameters") or {}).items()
            if v.get("paramtype") == "vlogdefine" and "default" in v and v["default"] is not False}
    ctx.art.update(rtl=files, incdirs=inc, defines={**defs, **ctx.cfg.get("defines", {})})


@backend
class NoNetlist(Backend):
    """No conversion: the synthesis already wrote the Interchange netlist (Vivado synthesis)."""
    stage, name = "netlist", "none"
    def run(self, ctx): pass
