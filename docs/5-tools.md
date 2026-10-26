<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : Every tool of every step: input and output (FPGA Interchange), what it does, its limits.
  Module   : 5-tools.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 5. Tools per step

## The exchange format: FPGA Interchange
After synthesis every step receives and returns the same files, in the open
[FPGA Interchange Format](https://github.com/chipsalliance/fpga-interchange-schema):
`.netlist` (logical netlist) and `.phys` (placement and routing, partial or complete). Each tool is a black box with
these inputs and outputs; tools that use another format convert at their own edges (listed in the table). Adding or
swapping a tool therefore never changes the neighbouring steps.

```
RTL ─ synth ─ .json/.edif ─ netlist ─ .netlist ─ place ─ .phys ─ route ─ .phys ─ bitgen ─ .bit ─ upload
```

A name followed by `(vivado)` uses Vivado for part of its work; everything else is open source.

## Tools
| Step | Name | Tool | In → out | Conversion at the edges |
|------|------|------|----------|-------------------------|
| sources | `files` / `core` | — | project file → RTL list | |
| synth | `yosys` | Yosys + slang + ghdl | RTL → `.json`, `.edif` | |
| synth | `vivado` | Vivado `synth_design` | RTL → `.netlist` + `.phys` | DCP → Interchange (RapidWright) |
| netlist | `yosys_json_if` | python-fpga-interchange | `.json` → `.netlist` | (xc7) |
| netlist | `rapidwright_if` | RapidWright | `.edif` → `.netlist` | (UltraScale+) |
| netlist | `vivado_link` | Vivado `link_design` | `.edif` → `.netlist` + `.phys` | DCP → Interchange |
| netlist | `none` | — | nothing to do (Vivado synthesis already wrote `.netlist`) | |
| place | `dreamplacefpga` | DREAMPlaceFPGA | `.netlist` → `.phys` (placed) | (UltraScale+) |
| place | `in_route` | — | placement happens in the route step (nextpnr) | (xc7) |
| place | `vivado` | Vivado `opt_design`, `place_design` | `.netlist` + `.phys` → `.phys` | Interchange ↔ DCP |
| route | `nextpnr_interchange` | nextpnr-fpga_interchange | `.netlist` → `.phys` (placed and routed) | (xc7) |
| route | `nextpnr_xilinx` | nextpnr-xilinx | Yosys `.json` → FASM | (xc7) alternative with an open chip database (prjxray-db); writes FASM directly, no `.phys` |
| route | `rwroute` | RapidWright RWRoute | `.netlist` + `.phys` → `.phys` (routed) | RWRoute writes a DCP, converted back (UltraScale+) |
| route | `vivado` | Vivado `route_design` | `.netlist` + `.phys` → `.phys` | Interchange ↔ DCP |
| bitgen | `prjxray` | python-fpga-interchange + prjxray | `.netlist` + `.phys` → FASM → `.bit` | open, xc7 |
| bitgen | `prjuray` | Project U-Ray (`fasm2bit`) + prjuray-db | FASM → `.bit` | open, UltraScale+; see below for what is missing |
| bitgen | `vivado_wrap (vivado)` | Vivado | open core `.phys` + hand-written I/O wrapper (`wrap:`) → `.bit` | Vivado places and routes only the wrapper around the locked open core |
| bitgen | `open_io (vivado)` | RapidWright + RWRoute, Vivado `write_bitstream` | `.netlist` + `.phys` → `.bit` | open I/O assembly; Vivado only writes the file ([details](8-open-io.md)) |
| bitgen | `vivado_wrap (vivado)` | Vivado | `.netlist` + `.phys` → `.bit` | Vivado implements an I/O wrapper around the open design |
| bitgen | `vivado` | Vivado `write_bitstream` | `.netlist` + `.phys` → `.bit` | needs pins and Vivado placement |
| bitgen | `vivado_ps (vivado)` | Vivado project + block design | RTL → `.bit`, `.hwh`, `.xsa` | for designs that use the PS |
| upload | `openfpgaloader` | openFPGALoader | `.bit` → board | |
| upload | `vivado` | Vivado hardware manager | `.bit` → board | |

Constraints (pins, clocks) do not travel inside the Interchange files: every step that needs them reads `xdc:` from the
project file.

## Bitstream: which boards are fully open
| Chip | Boards | Open bitstream | How |
|------|--------|----------------|-----|
| pynq-z2 | PYNQ-Z1, PYNQ-Z2 | yes | prjxray (database prjxray-db) |
| xczu7ev | ZCU104, ZCU106 | no | `open_io (vivado)`: only `write_bitstream` is Vivado |
| xck26 | KV260 | no | `open_io (vivado)`, but blinky has no PL clock there |
| xczu3eg | AUP-ZU3 8 GB | no | `open_io (vivado)`; no PL clock oscillator for blinky. Its part is in prjuray-db (see below) |

### Project U-Ray (UltraScale+)
[Project U-Ray](https://github.com/f4pga/prjuray) documents the UltraScale+ bitstream and turns a FASM file into a
bitstream (`fasm2bit`, installed as `prjuray-fasm2bit`, with `xcframes2bit`). Its database
[prjuray-db](https://github.com/f4pga/prjuray-db) (`zynqusp`, 2020) describes these parts completely enough to write a bitstream:

| Part in prjuray-db | Boards using it |
|--------------------|-----------------|
| xczu3eg-sbva484-1-e | Ultra96, Ultra96-V2 |
| xczu3eg-sfvc784-1-e | AUP-ZU3 (`aup-zu3-8gb`, speed grade -2: same tile grid), xczu3eg modules in the sfvc784 package (e.g. Trenz TE0820) |

Tested here: an (empty) FASM for xczu3eg-sbva484 gives a bitstream. Two pieces are still missing for a design:
1. a generator from Interchange `.phys` to Project U-Ray FASM for UltraScale+ (python-fpga-interchange only has xc7 and Nexus);
2. a tile grid for the other parts: xczu7ev (ZCU104, ZCU106) and xck26 (KV260) are not in prjuray-db. Project U-Ray
   builds it with its fuzzers, which run Vivado to produce test bitstreams (once, to build the database, not in the flow).
`make doctor` shows `prjuray` as `no` with the reason; `make install-prjuray` installs the tools and the database.

## Limits of the open UltraScale+ path (Yosys, RapidWright, DREAMPlaceFPGA, RWRoute)
- The design is implemented out of context (no I/O buffers, no PS); `open_io` adds the I/O afterwards.
- DREAMPlaceFPGA places LUTs, FDRE flip-flops, RAMB36E2 and clock buffers. Synthesis for these boards therefore runs
  without carry chains, wide multiplexers, LUTRAM, shift registers and DSPs (board keys `carry: none`, `legalize: dreamplace`).
- The number of placement iterations is scaled with the design size (`dreamplace_iterations`); a diverging placement is
  stopped as soon as it shows in the log and retried with a smaller step (`dreamplace_retries`).
- RWRoute routes without timing (`rwroute_args` changes it); the timing of the result is reported by RapidWright's timing
  model in `timing.rpt` (and by Vivado with `signoff: vivado`).

## Limits of the open xc7 path (Yosys, nextpnr-fpga_interchange, prjxray)
- Two nextpnr versions can place and route xc7: `nextpnr_interchange` (default; chip database from the RapidWright/AMD
  device description, Interchange in and out) and `nextpnr_xilinx` (chip database from prjxray-db, the open
  documentation; reads the Yosys JSON and writes FASM directly, the one exception to the Interchange contract).
  Choose with `route:` in the project file, or compare them with `route: all`.
- nextpnr-fpga_interchange is pinned to the last nextpnr commit that has it (the architecture was removed upstream in 2024).
- Synthesis runs without LUTRAM, shift registers, wide multiplexers and DSPs (board key `legalize: nextpnr_if`), and
  macro primitives such as differential I/O buffers are not supported yet by nextpnr-fpga_interchange.
- python-fpga-interchange needs older Python packages than the rest of FREISA: it runs in its own conda env `freisa-if`.

## Vivado
Vivado is used only where the project file selects it. It is found through `$VIVADO`, `PATH`, or
`/eda/Xilinx/Vivado/<version>/bin/vivado` (`VIVADO_ROOT`, `VIVADO_VERSION`; 2024.1 preferred).
A design that uses the PS needs a block design (`bd_tcl:`, `bd_name:` in the project file) and `bitgen: vivado_ps`,
which writes `out.bit`, `out.hwh` (hardware handoff) and `out.xsa`. `vivado_ps` has not been tested on hardware yet.

## Tools that were evaluated and not integrated
OpenPARF and AMF-Placer (contest architectures only, or need Vivado), f4pga (7-series wrapper for Artix-7 and xc7z010;
programs through openFPGALoader, already used here), the FPL'26 contest agent (Vivado-driven).
