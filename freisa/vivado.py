# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Vivado helpers shared by the Vivado steps: running a Tcl script, constraints, reading reports, EDIF for Vivado.
# Module   : vivado.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import pathlib, re
from .core import find_vivado

def run(ctx, body, log, cwd=None):
    """Run `body` as a Vivado batch script; <log>.tcl, <log>.vivado.log and <log>.log in `cwd` (default: the build folder)."""
    cwd = cwd or ctx.work
    (cwd / f"{log}.tcl").write_text(body)
    ctx.sh([find_vivado(), "-mode", "batch", "-nojournal", "-log", f"{log}.vivado.log", "-source", f"{log}.tcl"], log, cwd=cwd)

def xdc(ctx):
    """read_xdc lines of the project's constraints (they do not travel inside the Interchange files)."""
    return "".join(f"read_xdc {{{ctx.root / x}}}\n" for x in ctx.cfg.get("xdc", []))

def ooc(ctx):
    return ctx.cfg.get("ooc", not ctx.cfg.get("xdc"))  # no pin constraints -> out of context

def wns(rpt):
    """Worst negative slack from a report_timing_summary file (None if absent)."""
    try:
        m = re.search(r"WNS\(ns\).*?\n.*?\n\s*(-?[0-9.]+)", pathlib.Path(rpt).read_text(), re.S)
        return float(m.group(1)) if m else None
    except OSError:
        return None

def edif_for_vivado(ctx, edif):
    """Copy of a Yosys EDIF that Vivado can link: named after the top (<top>.edf, as Vivado requires), and without the
    duplicate declaration of the top that Yosys also writes into its primitive library (external LIB)."""
    txt, top = pathlib.Path(edif).read_text(), ctx.cfg["top"]
    lib = max(txt.find("(external LIB"), txt.find("(library LIB"))
    end_lib = txt.find("(library DESIGN")
    i = txt.find(f"(cell {top}\n", lib) if lib >= 0 else -1
    if i >= 0 and (end_lib < 0 or i < end_lib):
        depth, j = 0, i
        while True:  # end of the balanced (cell ...) block
            depth += (txt[j] == "(") - (txt[j] == ")"); j += 1
            if depth == 0: break
        txt = txt[:i] + txt[j:]
    out = ctx.work / f"{top}.edf"
    out.write_text(txt)
    return out
