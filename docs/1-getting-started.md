<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : Install, first run, where the results are.
  Module   : 1-getting-started.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 1. Getting started

## Requirements
- Linux x86-64, git, a C++ toolchain, cmake (checked by `make check-deps`, which prints the `apt` line for anything missing).
- [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) on `PATH`: Yosys with the `slang` and `ghdl` plugins, openFPGALoader.
- Java 11 or newer (RapidWright).
- Optional: Vivado. FREISA finds it through `$VIVADO`, then `PATH`, then `/path/to/Xilinx/Vivado/<version>/bin/vivado`. 

## Install
```sh
make install
```
This creates the `freisa` conda environment, downloads the board files of the supported boards, and builds the open tools
that are not packaged (nextpnr-fpga_interchange, python-fpga-interchange in its own env `freisa-if`, prjxray, Project U-Ray,
DREAMPlaceFPGA) into `install/` and `third_party/`. The first run on a new chip also builds its Interchange device
description (a few minutes, once).
Tools already built are skipped; `FORCE=1` rebuilds them. `make uninstall` removes everything `make install` created.

## First run
```sh
make flow                     # default: DESIGN=blinky TARGET=pynq-z2 (PYNQ-Z1/Z2)
```
What you see:
```
▶ check    blinky → pynq-z2        every step's tool, ✔ available / ✘ not (with what to change)
FREISA  blinky → xc7z020clg400-1   header with the steps of the run
▶ synth    yosys                   a step starts
  ✔ synth done in 00:00:06  cpu 80%  mem 0.1G  score 27
    │ last lines of the tool log
results                            every generated file and the report folder
✔ finished in 00:00:14
```
While a step runs, the bottom of the terminal shows a progress bar (step n of N, step and total time, CPU and memory of
the running tools) and the last line of the tool log. Colors are used only on a terminal; set `NO_COLOR=1` to turn them
off. The same text, without colors, is saved in `build/<design>/<board>/flow.log`.

The result is `build/blinky/pynq-z2/out.bit`, produced only by open tools. To program a connected board:
```sh
make upload                   # openFPGALoader; TOOL=vivado to use the Vivado hardware manager
                              # several boards connected: it lists them and asks which one (or JTAG=<serial>)
```

## Other boards
```sh
make flow TARGET=zcu104       # ZCU104 / ZCU106
make flow TARGET=kv260 TO=route
```
On ZCU104 and ZCU106 everything is done by open tools, I/O buffers and clock buffer included (`bitgen: open_io`, see [open_io](8-open-io.md));
Vivado only runs `write_bitstream` on the finished checkpoint, because no open bitstream writer exists for UltraScale+.
The KV260 has no PL clock oscillator (its PL clock comes from the PS), so blinky stops at the routed checkpoint there.
Supported boards: `pynq-z2`, `zcu104`, `zcu106`, `kv260` (see [Boards](4-boards.md)).

## Second example: UART loopback
`designs/examples/uart_loopback.yml`: the FPGA sends back on its UART whatever it receives, at any baud rate.
On ZCU104 and ZCU106 the USB cable used for JTAG also carries the FPGA's UART (another channel of the same FTDI chip),
so one cable is enough:
```sh
make flow   DESIGN=uart_loopback TARGET=zcu104
make upload DESIGN=uart_loopback TARGET=zcu104
make uart-test TARGET=zcu104          # finds the serial port of that cable, sends random bytes, checks the echo
```
`make uart-test` finds the port on its own (`uart_channel` in the board file); `PORT=/dev/ttyUSBx` and `BAUD=` override.
On the PYNQ-Z1/Z2 and the KV260 the USB serial port is wired only to the processor (PS), not to FPGA pins: there a
loopback needs software on the processor or an external USB-serial adapter on PMOD pins.

## Where the results are
```
build/<design>/<board>/
  out.bit, design.netlist, routed.phys, ...   generated files (.netlist/.phys: FPGA Interchange)
  report/summary.md                    one table: block, time, CPU, memory, score of every step
  report/reports/                      area.rpt and timing.rpt (open tools), tool reports of each step
  report/artifacts/                    links to every generated file
  report/logs/                         logs of every tool
```

## When something is missing
Every `make flow` and `make upload` first runs a check. If a selected tool is not available for the board,
it stops and prints what to install or which variable to change. You can run it alone:
```sh
make check TARGET=zcu104
python freisa.py                              # interactive interface: browse everything, run every command from a menu
make status                                  # dashboard: tools, boards, projects, builds
make doctor                                   # every tool of every step, yes/no, for every board (TARGET=<b> for one)
```
