# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Bitstream upload backends.
# Module   : upload.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import os, shutil
from ..core import Backend, backend, find_vivado

@backend
class OpenFpgaLoader(Backend):
    """openFPGALoader (open; the loader f4pga itself uses). Board name from `ofl_board` in the board file, cable from `ofl_cable`."""
    stage, name, tools = "upload", "openfpgaloader", ["openFPGALoader"]
    def run(self, ctx):
        t = ctx.target
        cmd = ["openFPGALoader"]
        if "ofl_board" in t: cmd += ["-b", t["ofl_board"]]
        if "ofl_cable" in t: cmd += ["-c", t["ofl_cable"]]
        if "ofl_board" not in t: cmd += ["--fpga-part", t["part"].split("-")[0]]
        ctx.sh(cmd + [ctx.art["bit"]], "upload")

@backend
class VivadoHw(Backend):
    """Vivado hardware manager (program_hw_devices). `hw_device` pattern in the board file (default derived from the part)."""
    stage, name = "upload", "vivado"
    def supports(self, target):
        return None if find_vivado() else "Vivado not found (PATH, $VIVADO, or /eda/Xilinx/Vivado/<version>/bin/vivado)"
    def run(self, ctx):
        t = ctx.target
        pat = t.get("hw_device") or (t["part"][:5] if t["part"].startswith("xczu") else t["part"][:7]) + "*"
        tcl = ctx.work / "upload.tcl"
        tcl.write_text(f"open_hw_manager\nconnect_hw_server\nopen_hw_target\nset dev [lindex [get_hw_devices {{{pat}}}] 0]\n"
                       f"current_hw_device $dev\nset_property PROGRAM.FILE {{{ctx.art['bit']}}} $dev\nprogram_hw_devices $dev\nclose_hw_manager\n")
        ctx.sh([find_vivado(), "-mode", "batch", "-nojournal", "-log", "upload.vivado.log", "-source", tcl.name], "upload", cwd=ctx.work)
