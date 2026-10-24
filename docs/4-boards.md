<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : Supported chips and boards, tools per step, adding a board.
  Module   : 4-boards.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 4. Boards

## Supported chips and tools per step
The first tool of each cell is the one `auto` selects in a project file (open tools).

| Chip | Boards (`TARGET`) | Synthesis | Netlist | Placement | Routing | Bitstream | Programming |
|------|-------------------|-----------|---------|-----------|---------|-----------|-------------|
| xc7z020 (Zynq-7000) | PYNQ-Z1, PYNQ-Z2 (`xc7z020`) | Yosys, Vivado | python-fpga-interchange, Vivado | (in routing), Vivado | nextpnr-fpga_interchange, nextpnr-xilinx, Vivado | prjxray, Vivado | openFPGALoader, Vivado |
| xczu7ev (Zynq UltraScale+) | ZCU104 (`zcu104`), ZCU106 (`zcu106`) | Yosys, Vivado | RapidWright, Vivado | DREAMPlaceFPGA, Vivado | RWRoute, Vivado | open_io (vivado), Vivado; prjuray: not this part | openFPGALoader, Vivado |
| xck26 (Zynq UltraScale+) | Kria KV260 (`kv260`) | Yosys, Vivado | RapidWright, Vivado | DREAMPlaceFPGA, Vivado | RWRoute, Vivado | open_io (vivado), Vivado; prjuray: not this part | openFPGALoader, Vivado |
| xczu3eg (Zynq UltraScale+) | AUP-ZU3 8 GB (`aup-zu3-8gb`) | Yosys, Vivado | RapidWright, Vivado | DREAMPlaceFPGA, Vivado | RWRoute, Vivado | open_io (vivado), Vivado; prjuray: part covered by prjuray-db, FASM generator missing | openFPGALoader, Vivado |

What this means in practice:
- **xc7z020**: the whole flow, bitstream included, runs with open tools.
- **UltraScale+**: open tools go up to the routed checkpoint, out of context (no I/O pins), because the open placer cannot
  place I/O and no open bitstream writer exists for these chips yet. `bitgen: vivado_wrap` lets Vivado add only the I/O
  wrapper and write the bitstream, keeping the open placement and routing. `bitgen: open_io` goes further: the I/O is also
  done by open tools and Vivado only writes the file. Alternatively every step can run in Vivado.
- **KV260, AUP-ZU3**: no PL clock oscillator in the board files; the PL clock comes from the PS, so a running design
  needs a block design with the PS (`bitgen: vivado_ps`). Blinky stops at the routed design there (`TO=route`).
- **AUP-ZU3**: its chip (xczu3eg-sfvc784) is one of the two parts in prjuray-db, the open UltraScale+ bitstream database:
  the first candidate for a fully open UltraScale+ bitstream once a `.phys` → FASM generator exists.

## Adding a board: boards.yml
Boards are listed in one file, `boards.yml`, at the top of the repository. For each board you write its name, its FPGA
part and where its board files come from; `make install-boards` does the rest:
```yaml
boards:
  aup-zu3-8gb:
    description: AMD/RealDigital AUP-ZU3, 8 GB
    part: xczu3eg-sfvc784-2-e
    source: {git: https://github.com/RealDigitalOrg/aup-zu3-bsp.git, path: board-files/aup-zu3-8gb, xdc: hw/constraints/mpsoc.xdc}
  zcu104:
    part: xczu7ev-ffvc1156-2-e
    source: {store: Xilinx/zcu104}
    ofl_cable: ft4232       # extra keys are copied to the board file
    uart_channel: 3
```
| Key | Meaning |
|-----|---------|
| `part` | FPGA part (Vivado name); family, synthesis settings and databases are derived from it |
| `source: {store: <Vendor>/<board>}` | board of [XilinxBoardStore](https://github.com/Xilinx/XilinxBoardStore) (a list for boards made of several, e.g. KV260) |
| `source: {git: <url>, path: <dir>}` | any git repository: the folder holding `board.xml` / `part0_pins.xml`; `xdc:` copies the board's own constraint file |
| `source: {..., ref: <branch>}` | optional; default: the repository's default branch (its latest version) |
| `description` | optional |
| other keys | copied unchanged to `targets/<name>.yml`: `ofl_board`, `ofl_cable`, `uart_channel`, `jtag_serial`, `hw_device` |

```sh
make install-boards                      # every board of boards.yml
make install-boards BOARD=aup-zu3-8gb    # one board
make doctor TARGET=aup-zu3-8gb           # what can run on it
```
For each board this writes:
- `boards/<name>/<board>/board.xml`, `part0_pins.xml`, `pins.xdc` (all board pins with their I/O standards);
- `boards/<name>/board.xdc` (the board's own constraints, with `xdc:`);
- `targets/<name>.yml` (generated: edit `boards.yml`, not this file).

`boards.lock` records the commit of each repository that was fetched. A new FPGA part gets its Interchange device
description (and, for xc7, the nextpnr chip database) automatically on its first run, in `install/share/interchange/`.

### Generated board file
Keys derived from `part`, for reference:

| Part | Keys |
|------|------|
| `xc7*` | `family: xc7`, `yosys_family: xc7`, `legalize: nextpnr_if`, `package` (from the part), `db_root` (prjxray-db series) |
| `xczu*`, `xck*` | `family: xczu`, `yosys_family: xcup`, `has_ps: true`, `carry: none`, `legalize: dreamplace` |
| `xcvu*`, `xcku*` | `family: xcvu`/`xcku`, `yosys_family: xcup`, `carry: none`, `legalize: dreamplace` |

## Programming permissions (Linux)
The JTAG cable must be accessible to your user. Install the cable rules once, then replug the board (or reload udev):
```sh
sudo /eda/Xilinx/Vivado/2024.1/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers
sudo udevadm control --reload-rules && sudo udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=0403   # the Xilinx rule only fires on "add"
```
With several boards connected, set `jtag_serial` in the board file so both openFPGALoader and Vivado pick the right one.
