# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Yosys synthesis backend.
# Module   : synth_yosys.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import pathlib
from ..core import Backend, backend

def _carry8_map():
    """Derive a CARRY8 techmap from the installed xilinx/arith_map.v (CARRY4 -> CARRY8 slices)."""
    import re, subprocess
    share = subprocess.check_output(["yosys-config", "--datdir"], text=True).strip()
    v = open(f"{share}/xilinx/arith_map.v").read()
    v = v.replace("CARRY4_COUNT", "CARRY8_COUNT").replace("+ 3) / 4", "+ 7) / 8").replace("COUNT * 4", "COUNT * 8")
    v = v.replace("*4 +: 4", "*8 +: 8").replace("*4 - 1", "*8 - 1")
    v = v.replace("CARRY4 carry4", 'CARRY8 #(.CARRY_TYPE("SINGLE_CY8")) carry8')
    v = re.sub(r"\.CYINIT\((\w+)\),\s*\.CI\s*\(1'd0\)", r".CI(\1), .CI_TOP(1'd0)", v)
    v = re.sub(r"\.CYINIT\(1'd0\),\s*\.CI\s*\((C \[i\*8 - 1\])\)", r".CI(\1), .CI_TOP(1'd0)", v)
    return v

@backend
class YosysSlang(Backend):
    """yosys-slang (SV/Verilog) + ghdl plugin (VHDL) -> synth_xilinx -> EDIF + JSON. Open source, any xc7/xcup design."""
    metric = "area"
    stage, name, tools = "synth", "yosys", ["yosys"]
    def run(self, ctx):
        t, c = ctx.target, ctx.cfg
        sv = [f for f, ft in ctx.art["rtl"] if ft != "vhdlSource"]
        vhd = [f for f, ft in ctx.art["rtl"] if ft == "vhdlSource"]
        defs = " ".join(f"-D {k}={v}" for k, v in c.get("defines", {}).items())
        pars = " ".join(f"-G {k}={v}" for k, v in c.get("params", {}).items())
        s = ["plugin -i slang"]
        if vhd:  # ghdl entities become yosys modules slang can instantiate
            s += ["plugin -i ghdl", f"ghdl --std=08 -fsynopsys {' '.join(vhd)} -e {c.get('vhdl_top', c['top'])}"]
        if sv: s += [f"read_slang {c.get('slang_args', '')} --top {c['top']} {defs} {pars} {' '.join(sv)}"]
        s += c.get("yosys_pre", [])  # raw yosys commands between read and synth
        base = f"synth_xilinx -top {c['top']} -family {t['yosys_family']} {c['synth_args']}"
        if t.get("legalize") == "dreamplace": base += " -nowidelut -noiopad -noclkbuf"  # placer has no MUXF7/8, and no fixed-IO sites without Vivado: OOC netlist
        if t.get("carry") == "none":  # placer has no carry-chain node type: adders become LUTs
            s += [base + " -nocarry"]
        elif t.get("carry") == "carry8":  # yosys only knows CARRY4 (7-series); UltraScale+ has CARRY8
            (ctx.work / "arith_map_carry8.v").write_text(_carry8_map())
            s += [base + " -run :fine", "techmap -D LUT_SIZE=6 -map arith_map_carry8.v", base + " -run fine:"]
        else:
            s += [base]
        if t.get("legalize") == "dreamplace":
            (ctx.work / "dp_legal.v").write_text((pathlib.Path(__file__).parent.parent / "yosys" / "dp_legal.v").read_text())
            s += ["techmap -map dp_legal.v", "opt_clean"]
        s += ["rename -enumerate -pattern n%",  # '$auto$' names are illegal in EDIF/bookshelf

              "hierarchy -top " + c["top"], "tee -o stats.txt stat", "write_edif -pvector bra out.edif", "write_json out.json"]
        (ctx.work / "synth.ys").write_text("\n".join(s) + "\n")
        ctx.sh(["yosys", "-l", "yosys.full.log", "-s", "synth.ys"], "synth", cwd=ctx.work)
        ctx.art["edif"], ctx.art["json"] = ctx.work / "out.edif", ctx.work / "out.json"

    def score(self, ctx):
        """Area proxy from stats.txt: LUTs + FFs, hard blocks weighted (lower is better)."""
        import re
        txt = (ctx.work / "stats.txt").read_text().split("design hierarchy")[-1]
        n = {m[1]: int(m[0]) for m in re.findall(r"^\s+(\d+)\s+(\w+)\s*$", txt, re.M)}
        return sum(v * (100 if k.startswith(("DSP", "RAMB", "URAM")) else 1) for k, v in n.items() if k.startswith(("LUT", "FD", "DSP", "RAMB", "URAM")))
