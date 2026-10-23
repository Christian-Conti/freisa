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
| xc7z020 (Zynq-7000) | PYNQ-Z1, PYNQ-Z2 (`xc7z020`) | Yosys, Vivado | python-fpga-interchange, Vivado | (in routing), Vivado | nextpnr-fpga_interchange, Vivado | prjxray, Vivado | openFPGALoader, Vivado |
| xczu7ev (Zynq UltraScale+) | ZCU104 (`zcu104`), ZCU106 (`zcu106`) | Yosys, Vivado | RapidWright, Vivado | DREAMPlaceFPGA, Vivado | RWRoute, Vivado | open_io (vivado), Vivado; prjuray: not this part | openFPGALoader, Vivado |
| xck26 (Zynq UltraScale+) | Kria KV260 (`kv260`) | Yosys, Vivado | RapidWright, Vivado | DREAMPlaceFPGA, Vivado | RWRoute, Vivado | open_io (vivado), Vivado; prjuray: not this part | openFPGALoader, Vivado |

What this means in practice:
- **xc7z020**: the whole flow, bitstream included, runs with open tools.
- **UltraScale+**: open tools go up to the routed checkpoint, out of context (no I/O pins), because the open placer cannot
  place I/O and no open bitstream writer exists for these chips yet. `bitgen: vivado_wrap` lets Vivado add only the I/O
  wrapper and write the bitstream, keeping the open placement and routing. `bitgen: open_io` goes further: the I/O is also
  done by open tools and Vivado only writes the file. Alternatively every step can run in Vivado.
- **KV260**: the board has no PL clock oscillator; its PL clock comes from the PS, so a bitstream needs a block design
  with the PS (`bitgen: vivado_ps`).

## Board files
One file per board in `targets/`:
```yaml
part: xczu7ev-ffvc1156-2-e      # Vivado part name
family: xczu                    # xczu | xcvu | xcku | xc7: selects which blocks can run
yosys_family: xcup              # Yosys synth_xilinx family
has_ps: true                    # the chip has a Zynq PS (information only)
board_store: Xilinx/zcu104      # XilinxBoardStore path(s) for `make install-boards`
ofl_board: zcu104               # openFPGALoader board name (`openFPGALoader --list-boards`)
hw_device: "xczu7*"             # optional: Vivado hardware-manager device pattern
uart_channel: 3                 # optional: FTDI interface of the PL UART (make uart-test)
jtag_serial: 38138              # optional: USB serial of the board's JTAG chip when several boards/cables are connected
carry: none                     # UltraScale+: synthesis settings needed by DREAMPlaceFPGA
legalize: dreamplace
# xc7 only:
db_root: third_party/prjxray-db/zynq7
```

## Adding a board
1. Copy the board file closest to yours into `targets/<name>.yml` and change `part`, `board_store`, `ofl_board`.
2. `make install-boards` downloads its files and writes `boards/<name>/.../pins.xdc`.
3. `make doctor TARGET=<name>` shows which blocks can run.
4. `make flow TARGET=<name>`; for a bitstream add pins (and a `wrap:` for UltraScale+) for it in `designs/examples/blinky.yml`.
A new part gets its Interchange device description (and, for xc7, the nextpnr chip database) generated automatically on its first run, in `install/share/interchange/`.

## Board files from XilinxBoardStore
`boards.lock` pins the XilinxBoardStore commit and one version per board. The boards are those named by `board_store:` in
`targets/*.yml`. `make install-boards` updates the lock to the newest store and downloads only those boards;
`make install-boards PIN=1` downloads exactly what the lock says.

## Programming permissions (Linux)
The JTAG cable must be accessible to your user. Install the cable rules once, then replug the board (or reload udev):
```sh
sudo /eda/Xilinx/Vivado/2024.1/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers
sudo udevadm control --reload-rules && sudo udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=0403   # the Xilinx rule only fires on "add"
```
With several boards connected, set `jtag_serial` in the board file so both openFPGALoader and Vivado pick the right one.
