<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : open_io: how FREISA gets an UltraScale+ bitstream with open tools for everything except write_bitstream.
  Module   : 8-open-io.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 8. open_io: UltraScale+ bitstream with open tools

`open_io` is the bitgen step that produces the bitstream on UltraScale+ boards (ZCU104, ZCU106) while letting the open
tools do almost everything. In `make check`, `make doctor` and during a run it is shown as `open_io (vivado)`, because
Vivado writes the final file.

## The problem it solves
The open tools for UltraScale+ (Yosys, RapidWright, DREAMPlaceFPGA, RWRoute) implement the design **out of context**, that
is without pins: DREAMPlaceFPGA cannot place I/O buffers, so synthesis leaves them out. Vivado refuses to write a
bitstream for a design without pins (DRC error `HDOOC-3`), and no open bitstream writer exists for UltraScale+
(see [Tools per step](5-tools.md#project-u-ray-ultrascale)). `open_io` adds the missing I/O with open tools and leaves
Vivado only the last step.

## What it does
```
.netlist + .phys (open placed and routed core)          Yosys JSON (ports)      XDC (pins)
          │                                                     │                    │
          └──────────────┬──────────────────────────────────────┴────────────────────┘
                         ▼
 1. ports and pins  ─  2. generated I/O wrapper (Yosys)  ─  3. assembly (RapidWright)
                         ─  4. routing of what is missing (RWRoute)  ─  5. write_bitstream only (Vivado)  ─▶  out.bit
```

1. **Reads ports and pins.** The ports of the design come from the Yosys netlist (`out.json`); the pins come from the
   project's XDC (`PACKAGE_PIN`/`LOC` and `IOSTANDARD`, also in `-dict` form). A port that drives flip-flop clock
   pins is a clock.
2. **Generates the I/O wrapper** (a small Verilog top synthesized by Yosys, with the core as a black box), with the
   right UltraScale+ primitives:

   | Port | Primitives |
   |------|-----------|
   | input | `INBUF` + `IBUFCTRL` |
   | differential input (`<port>_p` / `<port>_n` in the XDC) | `DIFFINBUF` + `IBUFCTRL` |
   | output | `OBUF` |
   | clock input | the above + `BUFGCE` (global clock buffer) |

   The macros Vivado would expand (`IBUF`, `IBUFDS`) are written directly as their primitives, so no expansion is needed.
3. **Assembles with RapidWright.** It inserts the core, already placed and routed by the open tools, into the wrapper
   (`makeBlackBox` + `populateBlackBox`), places the buffers on the physical sites of the pins, writes the constraints
   (`PACKAGE_PIN`, `IOSTANDARD`, `create_clock`) into the checkpoint, and aligns the netlist:
   - every primitive points to Vivado's canonical definition (`hdi_primitives`); merging two netlists otherwise renames
     some (`LUT2_parameterized0`) and Vivado would discard their placement;
   - one physical net per logical net (`makePhysNetNamesConsistent`).
4. **Routes with RWRoute only the missing connections**, keeping the routing of the core (`PartialRouter`): pads to
   buffers, buffers to the core, the global clock. If the partial routing does not converge within 15 iterations,
   RWRoute re-routes the whole design (the core routing then changes, still with open tools). At the end FREISA checks
   that no wire is used by two nets; if any is, it stops with an error instead of passing Vivado a broken design.
5. **Writes the bitstream with Vivado**: only `open_checkpoint` + `write_bitstream` (plus two read-only reports), no
   placement and no routing.

## Placement rules
| Cell | Site / BEL | How the site is found |
|------|-----------|----------------------|
| `INBUF`, `IBUFCTRL`, `OBUF` | IOB of the pin: `INBUF`, `IBUFCTRL`, `OUTBUF` | package pin → site (RapidWright device package) |
| `DIFFINBUF` | `HPIOBDIFFINBUF` / `HDIOBDIFFINBUF` of the pin pair | the one whose `PAD_RES_0` is wired to the P pad's `PAD_RES` |
| `BUFGCE` | a free `BUFGCE` (or `BUFGCE_HDIO`) site | same clock region as the clock pin |

The pad of a differential pair reaches `DIFFINBUF` through dedicated wires (`PAD_RES` → `PAD_RES_0`/`PAD_RES_1`), which
FREISA routes explicitly; a single-ended pad reaches `INBUF` inside the IOB site.

## How to use it
In the project file, choose it for the board and give the pins:
```yaml
boards:
  zcu104: {bitgen: open_io}
per_target:
  zcu104@open_io: {xdc: [zcu104.xdc], clocks: {clk: 3.333}}
```
The XDC needs, for every port bit, `PACKAGE_PIN` and `IOSTANDARD` with the port name (`led`, `data[3]`); a differential
clock is written as `clk_p`/`clk_n` while the design keeps one port `clk`. Board pins can be copied from
`boards/<board>/<board>/pins.xdc`. `clocks:` gives the period of each clock port.

`pins: auto` (instead of an XDC) assigns free pins automatically, clocks on clock-capable pins (`_GC`/`HDGC`): only to
check that a bitstream can be built. **Never load such a bitstream on a board.**

## What it produces
| File (in `build/<design>/<board>/`) | Content |
|-------------------------------------|---------|
| `out.bit` | the bitstream |
| `assembled.dcp` | the complete design (core + I/O), placed and routed by open tools |
| `io/io_wrap.v`, `io/io_wrap.edif` | the generated I/O wrapper |
| `io_assemble.log` | the assembly; look for the lines `I/O:` (inputs/outputs/clocks found) and `routing:` (core nets kept, re-routed, shared wires) |
| `bitgen_only.tcl`, `bitgen_only.vivado.log` | exactly what Vivado ran |
| `bitgen_route_status.rpt`, `bitgen_drc.rpt` | Vivado's read-only check of the open result (routing errors, DRC violations) |

Example from blinky on ZCU104:
```
I/O: 0 inputs, 1 differential inputs, 1 outputs, 1 clocks
routing: 45 of 45 routed core nets unchanged, 0 re-routed by RWRoute, 0 shared wires
```

## Tested
On ZCU104: blinky (differential clock + LED) and uart_loopback (PL UART) built and programmed, the UART echo verified
on hardware; counter, vhdl_blink, uart_tx and alu built with `pins: auto`. Vivado reported 0 routing errors and 0 DRC
violations on every one. A design with 66 automatic pins spread across the chip (lfsr_bank) failed: RWRoute stopped with
one shared wire.

## Limits
- `inout` ports and differential outputs are not supported yet.
- Every port needs `IOSTANDARD`; FREISA does not guess the bank voltage.
- The core inherits the limits of the open placer (no carry chains, wide multiplexers, LUTRAM, shift registers, DSPs:
  see [Tools per step](5-tools.md#limits-of-the-open-ultrascale-path-yosys-rapidwright-dreamplacefpga-rwroute)).
- Vivado is still needed for `write_bitstream`.
- A design that uses the PS needs `vivado_ps` instead.

## When it fails
| Message | Meaning / what to do |
|---------|----------------------|
| `port X has no PACKAGE_PIN in the constraints` | add the pin to the XDC (or `pins: auto` for a test build) |
| `port X: no IOSTANDARD in the constraints` | add `IOSTANDARD` for that port |
| `no DIFFINBUF site found for pads ...` | the two pins of `x_p`/`x_n` are not a differential pair |
| `no free BUFGCE in clock region ...` | too many clocks in the same region; move a clock to another pin |
| `RWRoute could not route the I/O without conflicts on ...` | routing did not converge: choose pins closer to the logic, or use `bitgen: vivado_wrap` |
| Vivado `HDOOC-3` / routing errors in `bitgen_route_status.rpt` | report it: the assembly should not hand Vivado such a design |
