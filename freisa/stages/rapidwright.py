# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : UltraScale+ steps on the FPGA Interchange format: EDIF -> .netlist (RapidWright), placement .netlist -> .phys
#            (DREAMPlaceFPGA), routing .phys -> .phys (RWRoute), and open_io (open I/O assembly, Vivado write_bitstream only).
# Module   : rapidwright.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import json, os, pathlib, re, shutil, sys
from .. import term as _term
from ..core import Backend, backend
from .. import ifx
from ..ifx import rw

US_PLUS = ("xczu", "xcvu", "xcku")  # families RapidWright/DREAMPlaceFPGA IF models cover (UltraScale+)

class _UsPlus(Backend):
    def supports(self, target):
        if target.get("family") not in US_PLUS:
            return f"UltraScale+ only (target family {target.get('family')})"
        return super().supports(target)

@backend
class RwNetlist(_UsPlus):
    """Yosys EDIF -> Interchange .netlist (+ empty .phys) through RapidWright (no Vivado)."""
    stage, name, tools = "netlist", "rapidwright_if", ["java"]
    def run(self, ctx):
        ctx.sh([sys.executable, pathlib.Path(__file__).parent.parent / "rw" / "edif2dcp.py", ctx.art["edif"], ctx.target["part"], ctx.work / "linked.dcp"], "edif2dcp")
        ifx.from_dcp(ctx, ctx.work / "linked.dcp", "linked")

@backend
class DreamPlaceFpga(_UsPlus):
    """.netlist -> Bookshelf -> DREAMPlaceFPGA (gpu or cpu) -> placed .phys."""
    metric = "hpwl"
    stage, name, tools = "place", "dreamplacefpga", ["java"]
    def supports(self, target):
        return super().supports(target) or (None if self._root() else "build DREAMPlaceFPGA: `make install-dreamplace` (or set DREAMPLACEFPGA_ROOT)")
    def _root(self):
        r = pathlib.Path(os.environ.get("DREAMPLACEFPGA_ROOT", pathlib.Path(__file__).parents[2] / "third_party/dreamplacefpga"))
        return r if (r / "install" / "dreamplacefpga" / "Placer.py").exists() else None
    def run(self, ctx):
        root, w, d = self._root(), ctx.work, ctx.work / "dp"
        d.mkdir(exist_ok=True); base = f"design_{abs(hash(str(w))) % 10**8}"  # unique: bookshelf dir is shared under the DREAMPlace root
        shutil.copy(ctx.art["netlist"], d / f"{base}.netlist")
        part = ctx.target["part"]
        if not (root / "IFsupport" / f"{part}.device").exists():  # large; generated once per part
            rw(ctx, "interchange.DeviceResourcesExample", [part], "device", cwd=root / "IFsupport")
        # IF2bookshelf hardcodes xcvu3p; run a patched copy for the target part
        patched = root / "IFsupport" / f"IF2bookshelf_{part}.py"  # schema dir is script-relative
        patched.write_text((root / "IFsupport/IF2bookshelf.py").read_text().replace("xcvu3p-ffvc1517-2-e", part)
                            # top-level port refs have no instance; upstream reuses the previous cell for them
                            .replace("                    if port_inst.which() == 'inst':", "                    if port_inst.which() != 'inst':\n                        continue\n                    if port_inst.which() == 'inst':")
                            # flip-flops with async clear/preset or sync set sit on the same sites as FDRE: placed as FDRE,
                            # their reset/set pin as R; the placement written back keeps their real type and pins
                            .replace("        # database for design.nodes",
                                     "        for _t in ('FDCE', 'FDPE', 'FDSE'):\n"
                                     "            if _t in self.cell_ports and 'FDRE' not in self.cell_ports:\n"
                                     "                self.cell_ports['FDRE'] = [('R' if n in ('CLR', 'PRE', 'S') else n, d) for n, d in self.cell_ports[_t]]\n"
                                     "        # database for design.nodes")
                            .replace("                self.nodes[cell_name] = cell_type",
                                     "                self.nodes[cell_name] = 'FDRE' if cell_type in ('FDCE', 'FDPE', 'FDSE') else cell_type\n"
                                     "                if cell_type in ('FDCE', 'FDPE', 'FDSE'): self.__dict__.setdefault('_ff', set()).add(cell_name)")
                            .replace("                        self.nets[net_name].append((cell, port_name))",
                                     "                        self.nets[net_name].append((cell, 'R' if cell in self.__dict__.get('_ff', ()) and port_name in ('CLR', 'PRE', 'S') else port_name))"))
        py = [sys.executable]
        ctx.sh(py + [patched, "--netlist", d / f"{base}.netlist"], "if2bookshelf", cwd=root)
        cfg = {**json.loads((pathlib.Path(__file__).parent.parent / "rw" / "dp_template.json").read_text()),  # settings from RapidWright's tutorial
               "aux_input": f"benchmarks/IF2bookshelf/{base}/design.aux", "gpu": int(ctx.cfg.get("gpu", 0)),
               "part_name": ctx.target["part"], "num_threads": int(ctx.cfg.get("threads", 4)), "result_dir": str(d / "results"),
               **ctx.cfg.get("dreamplace", {})}
        # the default 2000-iteration schedule is sized for big designs; a few hundred cells never reach the stop criterion
        # (overflow stays high because the density force is dominated by filler cells), so scale the schedule with design size
        if "global_place_stages" not in ctx.cfg.get("dreamplace", {}):
            n = sum(1 for _ in open(root / f"benchmarks/IF2bookshelf/{base}/design.nodes"))
            its = int(ctx.cfg.get("dreamplace_iterations", 150 if n < 1000 else 500 if n < 10000 else 2000))
            for st in cfg.get("global_place_stages", []): st["iteration"] = its
            print("    " + _term.dim(f"dreamplace: {n} nodes → {its} iterations"), flush=True)
        # tiny designs can make the optimizer diverge (HPWL -inf/nan, then a crash): retry with a smaller step and another seed
        for attempt in range(int(ctx.cfg.get("dreamplace_retries", 3))):
            c = json.loads(json.dumps(cfg)); shutil.rmtree(d / "results", ignore_errors=True)
            c["random_seed"] = cfg["random_seed"] + attempt
            for st in c.get("global_place_stages", []): st["learning_rate"] = st.get("learning_rate", 0.01) / 2 ** attempt
            (d / "dp.json").write_text(json.dumps(c, indent=1))
            try:
                ctx.sh(py + [root / "install/dreamplacefpga/Placer.py", d / "dp.json"], "dreamplace", cwd=root, watch=r"HPWL\s+-?(inf|nan)")
                ok = not re.search(r"HPWL\s+-?(inf|nan)", (ctx.work / "dreamplace.log").read_text(), re.I) and any((d / "results").rglob("*.phys"))
            except SystemExit:
                ok = False
            if ok: break
            print("    " + _term.note(f"dreamplace attempt {attempt + 1} diverged or crashed; retrying with a smaller step"), flush=True)
        else:
            raise SystemExit(f"[dreamplace] failed after {attempt + 1} attempts, see {os.path.relpath(ctx.work / 'dreamplace.log')}")
        shutil.copy(next((d / "results").rglob("*.phys")), w / "placed.phys")
        ctx.art["phys"] = w / "placed.phys"
    def score(self, ctx):  # final HPWL printed by DREAMPlaceFPGA
        import re
        m = re.findall(r"HPWL\s*[:=]?\s*([0-9.eE+]+)", (ctx.work / "dreamplace.log").read_text())
        return float(m[-1]) if m else None

@backend
class RwRoute(_UsPlus):
    """RWRoute: open router for UltraScale+: .netlist + placed .phys -> routed .phys (RWRoute writes a DCP, converted back)."""
    metric = "wirelength"
    stage, name, tools = "route", "rwroute", ["java"]
    def run(self, ctx):
        _, phys = ifx.pair(ctx, "route_in")  # RWRoute wants .netlist and .phys with the same root name
        rw(ctx, "rwroute.RWRoute", [phys, ctx.work / "routed.dcp", *ctx.cfg.get("rwroute_args", ["--nonTimingDriven", "--outOfContext"])], "rwroute")  # timing-driven needs clock constraints
        ifx.from_dcp(ctx, ctx.work / "routed.dcp", "routed")
    def score(self, ctx):  # total wirelength reported by RWRoute; unrouted/failed -> None
        import re
        m = re.findall(r"[Tt]otal wirelength:?\s*([0-9]+)", (ctx.work / "rwroute.log").read_text())
        return int(m[-1]) if m else (ctx.work / "routed.dcp").stat().st_size

@backend
class OpenIo(_UsPlus):
    """Bitstream with the I/O done by open tools: RapidWright places the I/O buffers (from `xdc:` pins, or `pins: auto`
    for test builds) and the clock buffers around the open placed-and-routed design, RWRoute routes only what is missing,
    and Vivado runs nothing but `open_checkpoint` + `write_bitstream` (no open UltraScale+ bitstream writer exists)."""
    stage, name, tools = "bitgen", "open_io", ["java", "yosys"]
    vendor = "vivado"  # write_bitstream only
    def supports(self, target):
        from ..core import find_vivado
        return super().supports(target) or (None if find_vivado() else "needs Vivado for write_bitstream only (no open UltraScale+ bitstream writer)")
    def run(self, ctx):
        from ..core import find_vivado
        c = ctx.cfg
        core = ifx.to_dcp(ctx, "core")  # the open-routed design (Interchange) as a checkpoint for the assembly
        args = [sys.executable, pathlib.Path(__file__).parent.parent / "rw" / "io_assemble.py", core, ctx.art["json"],
                c["top"], ctx.target["part"], ctx.work / "io", ctx.work / "assembled.dcp"]
        if c.get("xdc"): args += ["--xdc", *[ctx.root / x for x in c["xdc"]]]
        if c.get("pins") == "auto": args.append("--auto-pins")
        if c.get("clocks"): args += ["--clock", *[f"{k}={v}" for k, v in c["clocks"].items()]]
        ctx.sh(args, "io_assemble")
        (ctx.work / "bitgen_only.tcl").write_text("open_checkpoint assembled.dcp\nreport_route_status -file bitgen_route_status.rpt\n"
                                                  "report_drc -file bitgen_drc.rpt\nwrite_bitstream -force out.bit\n")
        ctx.sh([find_vivado(), "-mode", "batch", "-nojournal", "-log", "bitgen_only.vivado.log", "-source", "bitgen_only.tcl"], "bitgen_only", cwd=ctx.work)
        ctx.art.update(dcp=ctx.work / "assembled.dcp", bit=ctx.work / "out.bit")
