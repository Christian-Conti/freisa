# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Open I/O assembly for UltraScale+: puts an open placed-and-routed (out-of-context) core inside generated I/O
#            buffers placed on the board pins, routes what is missing with RWRoute, and writes a complete checkpoint.
#            Vivado then only has to run write_bitstream on it.
# Module   : io_assemble.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
"""Usage: io_assemble.py <core.dcp> <core.json> <top> <part> <workdir> <out.dcp> [--xdc f ...] [--auto-pins] [--clock port=ns ...]

Inputs per core port bit: single-ended input -> INBUF + IBUFCTRL (+ BUFGCE if it is a clock), differential input
(ports <name>_p/<name>_n in the XDC) -> DIFFINBUF + IBUFCTRL (+ BUFGCE), output -> OBUF. Pins come from the XDC
(PACKAGE_PIN / IOSTANDARD) or, with --auto-pins, are picked automatically (test only: never load such a bitstream)."""
import argparse, json, pathlib, re, subprocess, sys

ap = argparse.ArgumentParser()
for a in ("core_dcp", "core_json", "top", "part", "work", "out"): ap.add_argument(a)
ap.add_argument("--xdc", nargs="*", default=[]); ap.add_argument("--auto-pins", action="store_true")
ap.add_argument("--clock", nargs="*", default=[])
a = ap.parse_args()
work = pathlib.Path(a.work); work.mkdir(parents=True, exist_ok=True)
log = lambda *m: print("   ", *m, flush=True)

# ---------- 1. core ports and clocks (Yosys netlist) ----------
mod = json.load(open(a.core_json))["modules"][a.top]
ports = {n: (p["direction"], p["bits"]) for n, p in mod["ports"].items()}
clock_bits = set()
for c in mod["cells"].values():
    if re.match(r"(FD|RAMB|DSP|SRL|LUTRAM|RAM)", c["type"]):
        for pin in ("C", "CLK", "CLKARDCLK", "CLKBWRCLK", "WCLK"):
            clock_bits.update(b for b in c["connections"].get(pin, []) if isinstance(b, int))
def key(n, i, w): return n if w == 1 else f"{n}[{i}]"
bits = []  # (port, index, width, dir, is_clock)
for n, (d, bs) in ports.items():
    if d == "inout": sys.exit(f"inout port {n}: not supported by the open I/O assembly")
    for i, b in enumerate(bs): bits.append((n, i, len(bs), d, b in clock_bits))

# ---------- 2. pins ----------
pin, std, term = {}, {}, {}
for f in a.xdc:
    for line in open(f):
        for m in re.finditer(r"set_property\s+(PACKAGE_PIN|LOC|IOSTANDARD|DIFF_TERM_ADV)\s+(\S+)\s+\[get_ports\s+\{?([^\]\}]+?)\}?\]", line):
            prop, val, names = m.groups()
            for nm in names.split():
                {"IOSTANDARD": std, "DIFF_TERM_ADV": term}.get(prop, pin)[nm] = val
        m = re.search(r"-dict\s+\{([^}]*)\}\s+\[get_ports\s+\{?([^\]\}]+?)\}?\]", line)
        if m:
            kv = dict(zip(m.group(1).split()[::2], m.group(1).split()[1::2]))
            for nm in m.group(2).split():
                if "PACKAGE_PIN" in kv: pin[nm] = kv["PACKAGE_PIN"]
                if "IOSTANDARD" in kv: std[nm] = kv["IOSTANDARD"]

import rapidwright  # noqa: E402  (starts the JVM)
from com.xilinx.rapidwright.design import Design, DesignTools, Unisim
from com.xilinx.rapidwright.device import SiteTypeEnum
from com.xilinx.rapidwright.edif import EDIFTools
from com.xilinx.rapidwright.rwroute import PartialRouter

tmp = Design("probe", a.part); dev = tmp.getDevice(); pkg = dev.getActivePackage()
used = set(pin.values())
def free_pin(clock):
    for p in sorted(pkg.getPackagePinMap().values(), key=lambda p: str(p.getName())):
        if p.getSite() is None or str(p.getName()) in used or not p.isGeneralPurpose(): continue
        if p.isVref() or p.isVrn() or p.isVrp(): continue
        st = str(p.getSiteTypeEnum())
        if not st.startswith(("HPIOB", "HDIOB")) or st.endswith("SNGL"): continue
        # clock-capable pins: function names like IO_L12P_T1U_N10_GC_64 / IO_L5P_HDGC_24 (isGlobalClk() is not populated)
        if clock and not re.search(r"L\d+P_.*(_GC|HDGC)", str(p.getPinFunction())): continue
        used.add(str(p.getName())); return str(p.getName()), ("LVCMOS18" if st.startswith("HPIOB") else "LVCMOS33")
    sys.exit("no free pin left for automatic assignment")

io = []  # dicts: kind (se_in|diff_in|out), port, idx, width, clock, pins, std
for n, i, w, d, clk in bits:
    k = key(n, i, w)
    if k in pin:
        io.append(dict(kind="se_in" if d == "input" else "out", port=n, idx=i, w=w, clock=clk, pins=[pin[k]], std=std.get(k)))
    elif w == 1 and d == "input" and f"{n}_p" in pin and f"{n}_n" in pin:
        io.append(dict(kind="diff_in", port=n, idx=i, w=w, clock=clk, pins=[pin[f"{n}_p"], pin[f"{n}_n"]], std=std.get(f"{n}_p")))
    elif a.auto_pins:
        p, s = free_pin(clk and d == "input")
        io.append(dict(kind="se_in" if d == "input" else "out", port=n, idx=i, w=w, clock=clk, pins=[p], std=s))
    else:
        sys.exit(f"port {k} has no PACKAGE_PIN in the constraints (add it to `xdc:`, or `pins: auto` for a test build)")
    if io[-1]["std"] is None: sys.exit(f"port {k}: no IOSTANDARD in the constraints")
log(f"I/O: {sum(x['kind'] == 'se_in' for x in io)} inputs, {sum(x['kind'] == 'diff_in' for x in io)} differential inputs, "
    f"{sum(x['kind'] == 'out' for x in io)} outputs, {sum(x['clock'] for x in io)} clocks" + (" (pins: auto)" if a.auto_pins else ""))

# ---------- 3. wrapper RTL + Yosys ----------
top_io = a.top + "_io"
def outer(x): return (f"{x['port']}_p", f"{x['port']}_n") if x["kind"] == "diff_in" else (x["port"] if x["w"] == 1 else f"{x['port']}[{x['idx']}]",)
decl, body = [], []
for n, (d, bs) in ports.items():
    rng = f"[{len(bs) - 1}:0] " if len(bs) > 1 else ""
    if any(x["port"] == n and x["kind"] == "diff_in" for x in io): decl += [f"input {n}_p", f"input {n}_n"]
    else: decl.append(f"{'input' if d == 'input' else 'output'} {rng}{n}")
    body.append(f"  wire {rng}w_{n};")
for j, x in enumerate(io):
    t = f"w_{x['port']}" + (f"[{x['idx']}]" if x["w"] > 1 else ""); s = f"io{j}"
    if x["kind"] == "out":
        body.append(f"  OBUF {s}_ob (.I({t}), .O({outer(x)[0]}));")
        continue
    src = f"{s}_pad"
    body.append(f"  wire {src}, {s}_c;")
    if x["kind"] == "se_in": body.append(f"  INBUF {s}_ib (.PAD({outer(x)[0]}), .O({src}));")
    else: body.append(f"  DIFFINBUF {s}_db (.DIFF_IN_P({outer(x)[0]}), .DIFF_IN_N({outer(x)[1]}), .O({src}), .O_B());")
    body.append(f"  IBUFCTRL {s}_ic (.I({src}), .O({s}_c));")
    body.append(f"  BUFGCE {s}_bg (.I({s}_c), .CE(1'b1), .O({t}));" if x["clock"] else f"  assign {t} = {s}_c;")
conns = ", ".join(f".{n}(w_{n})" for n in ports)
(work / "io_wrap.v").write_text(
    f"module {top_io}({', '.join(decl)});\n" + "\n".join(body) + f"\n  {a.top} core ({conns});\nendmodule\n"
    "(* blackbox *) module INBUF(input PAD, input [3:0] OSC, input OSC_EN, input VREF, output O); endmodule\n"
    "(* blackbox *) module IBUFCTRL(input I, input IBUFDISABLE, input T, output O); endmodule\n"
    "(* blackbox *) module DIFFINBUF(input DIFF_IN_P, input DIFF_IN_N, input [3:0] OSC, input [1:0] OSC_EN, input VREF, output O, output O_B); endmodule\n")
stub = ", ".join(f"{'input' if d == 'input' else 'output'} {f'[{len(bs) - 1}:0] ' if len(bs) > 1 else ''}{n}" for n, (d, bs) in ports.items())
(work / "io_core_stub.v").write_text(f"(* blackbox *) module {a.top}({stub}); endmodule\n")
(work / "io_wrap.ys").write_text(f"read_verilog -lib io_core_stub.v\nread_verilog io_wrap.v\n"
                                 f"synth_xilinx -top {top_io} -family xcup -flatten -noiopad -noclkbuf\nopt_clean\nwrite_edif -pvector bra io_wrap.edif\n")
r = subprocess.run(["yosys", "-q", "-l", "io_wrap.log", "-s", "io_wrap.ys"], cwd=work)
if r.returncode: sys.exit(f"yosys failed on the I/O wrapper, see {work}/io_wrap.log")

# ---------- 4. RapidWright assembly ----------
top = Design(top_io, a.part)
top.setNetlist(EDIFTools.readEdifFile(str(work / "io_wrap.edif")))
top.setAutoIOBuffers(False)
DesignTools.makeBlackBox(top, "core")
DesignTools.populateBlackBox(top, "core", Design.readCheckpoint(a.core_dcp))
n = top.getNetlist(); tc = n.getTopCell(); dev = top.getDevice(); pkg = dev.getActivePackage()
def walk(cell):  # one netlist: every primitive instance -> Vivado's canonical hdi_primitives cell
    for inst in list(cell.getCellInsts()):
        ct = inst.getCellType(); base = re.sub(r"(_parameterized\d+|_RW_id\d+)+$", "", str(ct.getName()))
        try: u = Unisim.valueOf(base)
        except Exception: u = None
        if u is not None:
            if str(ct.getLibrary().getName()) != "hdi_primitives" or str(ct.getName()) != base: inst.setCellType(n.getHDIPrimitive(u))
        elif not ct.isLeafCellOrBlackBox(): walk(ct)
walk(tc)
DesignTools.makePhysNetNamesConsistent(top)  # one physical net per logical net (the merge leaves e.g. "busy" + "core/busy")

def place(inst, site, bel):
    c = top.createCell(inst, tc.getCellInst(inst))
    if not top.placeCell(c, site, site.getBEL(bel)): sys.exit(f"cannot place {inst} on {site}/{bel}")
def pad(port_net, site, to_bel_pin, sink_site=None, sink_pin=None):
    net = top.getNet(port_net) or top.createNet(port_net)
    si = top.getSiteInstFromSite(site) or top.createSiteInst(site)
    if sink_site is None:
        si.routeIntraSiteNet(net, site.getBEL("PAD").getPin("PAD"), to_bel_pin); return
    si.routeIntraSiteNet(net, site.getBEL("PAD").getPin("PAD"), site.getBELPin("PAD_RES"))
    net.createPin("PAD_RES", si)
    dsi = top.getSiteInstFromSite(sink_site); net.createPin(sink_pin, dsi)
    dsi.routeIntraSiteNet(net, sink_site.getBELPin(sink_pin), to_bel_pin)
def diff_site(p_site, n_site):
    """DIFFINBUF site wired to this pin pair: its PAD_RES_0/1 nodes are reached from the pads' PAD_RES."""
    def nodes(s, pinname):
        nd = s.getConnectedNode(s.getPinIndex(pinname)) if s.getPinIndex(pinname) >= 0 else None
        return {str(x) for x in ([nd] + list(nd.getAllDownhillNodes())) } if nd is not None else set()
    want = nodes(p_site, "PAD_RES")
    for s in p_site.getTile().getSites():
        if "DIFFINBUF" in str(s.getSiteTypeEnum()):
            nd = s.getConnectedNode(s.getPinIndex("PAD_RES_0"))
            if nd is not None and str(nd) in want: return s
    sys.exit(f"no DIFFINBUF site found for pads {p_site}/{n_site}")
used_bufg, xdc, se_pads = set(), [], []
def bufg_site(ref):
    cr = ref.getTile().getClockRegion()
    for st in (SiteTypeEnum.BUFGCE, SiteTypeEnum.BUFGCE_HDIO):
        for s in sorted(dev.getAllSitesOfType(st), key=str):
            if s.getTile().getClockRegion() == cr and str(s) not in used_bufg: used_bufg.add(str(s)); return s
    sys.exit(f"no free BUFGCE in clock region {cr}")
for j, x in enumerate(io):
    s = f"io{j}"
    sites = [pkg.getPackagePin(p).getSite() for p in x["pins"]]
    names = outer(x)
    for nm, p in zip(names, x["pins"]):
        xdc += [f"set_property PACKAGE_PIN {p} [get_ports {{{nm}}}]", f"set_property IOSTANDARD {x['std']} [get_ports {{{nm}}}]"]
    # differential input termination: as in the XDC; LVDS-type standards need it set (Vivado's own default: none),
    # the SSTL/HSTL ones do not accept it
    if x["kind"] == "diff_in" and (names[0] in term or x["std"].startswith(("LVDS", "SLVS", "SUB_LVDS", "MIPI"))):
        xdc.append(f"set_property DIFF_TERM_ADV {term.get(names[0], 'TERM_NONE')} [get_ports {{{names[0]}}}]")
    if x["kind"] == "out":
        top.placeIOB(tc.getCellInst(f"{s}_ob"), x["pins"][0], x["std"]); continue
    place(f"{s}_ic", sites[0], "IBUFCTRL")
    if x["kind"] == "se_in":
        place(f"{s}_ib", sites[0], "INBUF")
        pad(names[0], sites[0], sites[0].getBEL("INBUF").getPin("PAD"))
        se_pads.append(names[0])
    else:
        ds = diff_site(*sites); place(f"{s}_db", ds, "DIFFINBUF")
        pad(names[0], sites[0], ds.getBEL("DIFFINBUF").getPin("DIFF_IN_P"), ds, "PAD_RES_0")
        pad(names[1], sites[1], ds.getBEL("DIFFINBUF").getPin("DIFF_IN_N"), ds, "PAD_RES_1")
    if x["clock"]:
        place(f"{s}_bg", bufg_site(sites[0]), "BUFCE")
        period = dict(c.split("=") for c in a.clock).get(x["port"], "10.0")
        xdc.append(f"create_clock -period {period} -name {x['port']} [get_ports {{{names[0]}}}]")
top.addXDCConstraint(xdc)

DesignTools.createMissingSitePinInsts(top)
top.routeSites()
for nm in se_pads:  # pad -> INBUF is inside the IOB site: the IO site pin RapidWright adds needs no routing
    nt = top.getNet(nm)
    for spi in [p for p in nt.getPins() if str(p.getName()) == "IO"] if nt else []: nt.removePin(spi, True)
from com.xilinx.rapidwright.rwroute import RWRoute
def overlaps():
    """Wires used by more than one net (RWRoute can stop at its iteration limit and still leave some)."""
    owner, clash = {}, set()
    for nt in top.getNets():
        for pp in nt.getPIPs():
            nd = str(pp.getEndNode())
            if owner.setdefault(nd, str(nt.getName())) != str(nt.getName()): clash.add(nd)
    return clash
before = {str(nt.getName()): nt.getPIPs().size() for nt in top.getNets() if nt.getPIPs().size() and not nt.isStaticNet()}
# keep the open routing, route only what is missing; few iterations: if it does not converge, the full re-route below is faster
PartialRouter.routeDesignWithUserDefinedArguments(top, ["--nonTimingDriven", "--maxIterations", "15"], None, True)
clash = overlaps()
if clash:
    log(f"partial routing left {len(clash)} shared wires: full re-route with RWRoute (the core routing changes, still open tools)")
    RWRoute.routeDesignFullNonTimingDriven(top)
    clash = overlaps()
moved = [k for k, v in before.items() if top.getNet(k) is None or top.getNet(k).getPIPs().size() != v]
log(f"routing: {len(before) - len(moved)} of {len(before)} routed core nets unchanged, {len(moved)} re-routed by RWRoute, {len(clash)} shared wires")
if clash: sys.exit("RWRoute could not route the I/O without conflicts on: " + ", ".join(sorted(clash)[:5]))
top.writeCheckpoint(a.out)
