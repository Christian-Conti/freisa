<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : FREISA overview, quick start and documentation index.
  Module   : README.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# FREISA — FPGA Reusable and Extensible Infrastructure for Synthesis Automation

FREISA takes an RTL design (Verilog, SystemVerilog, VHDL) to an FPGA bitstream using open-source tools.
Each step of the flow is a replaceable block, and designs and boards are short YAML files.
Vivado is optional: it is used only when you ask for it.

Everything can be done from the terminal (`make`) or from an interactive interface (`python freisa.py`).

## Quick start
```sh
make install                       # one time: conda env, board files, open tools
make flow                          # default: blinky on PYNQ-Z2, RTL -> out.bit, open tools only
make flow TARGET=zcu104            # blinky on ZCU104: open tools, Vivado only writes the bitstream
make flow DESIGN=uart_loopback TARGET=zcu104 && make upload DESIGN=uart_loopback TARGET=zcu104 && make uart-test TARGET=zcu104
make help                          # every command and variable
```

## Interactive interface
```sh
python freisa.py                   # switches to the FREISA conda env by itself; works from 60x20
```
One tab per activity, switched with `1`-`6`, `Tab` or the mouse; the bottom lines list the keys of the tab, `?` all of them:

| Tab | What it does |
|-----|--------------|
| 1 Home | tools, boards, projects, JTAG cables at a glance; every build: open its reports, program, run again, delete |
| 2 Flow | choose design, board, FROM/TO and the tool of each step (each tool shows whether it can run there); run with live progress and logs |
| 3 Builds | each build's summary, flow log, area and timing reports |
| 4 Boards | `boards.yml`: install boards, see their files and settings |
| 5 Hardware | JTAG cables and serial ports: program, reset, UART monitor as a conversation, loopback test |
| 6 Tools | source tools: install, update, environment, doctor |

The tab bar shows CPU and memory of the PC; each running command shows its time, CPU, memory and memory peak.
Details: [Using the flow](docs/2-usage.md#interactive-interface).

## Documentation
Read in this order:

1. [Getting started](docs/1-getting-started.md): install, first run, where the results are.
2. [Using the flow](docs/2-usage.md): commands, variables, explore, upload, reports, the interactive interface.
3. [Project files](docs/3-projects.md): one file per design with sources, tools per step and board settings.
4. [Boards](docs/4-boards.md): supported boards (PYNQ-Z2, ZCU104, ZCU106, KV260, AUP-ZU3 8 GB), tools per step, adding a board in `boards.yml`.
5. [Tools per step](docs/5-tools.md): what each block does and its limits (including Vivado and the PS / `.hwh`).
6. [Developer guide](docs/6-developer.md): how the engine works, adding or updating a block.
7. [Examples](docs/7-examples.md): blinky and uart_loopback on every board: build, program, test.
8. [open_io](docs/8-open-io.md): how UltraScale+ bitstreams are made with open tools for everything except `write_bitstream`.
9. [Real designs](docs/9-real-designs.md): any repository untouched (generators, FuseSoC cores) and which flow to use.

## Repository layout
| Path | Content |
|------|---------|
| `Makefile`, `flow.py` | entry points of the terminal commands |
| `freisa.py` | entry point of the interactive interface |
| `designs/` | project files, one per design (examples: `designs/examples/blinky.yml`, `uart_loopback.yml`) |
| `examples/` | RTL and pin files of the bundled examples |
| `targets/` | board files (generated from `boards.yml`) |
| `freisa/` | flow engine (`core`, `resolve`, `monitor`, `report`), the tools of each step (`freisa/stages/`), the interactive interface (`freisa/tui/`), RapidWright scripts (`freisa/rw/`); map in the [Developer guide](docs/6-developer.md#code-map) |
| `utils/` | install, check and helper scripts |
| `defaults.yml` | default tool options |
| `boards.yml` | the boards to install (you edit it; `make install-boards`) |
| `tools.lock`, `boards.lock` | source tools (latest version or pinned commit) / commits of the fetched board files |
| `build/<design>/<board>/` | outputs (created by the flow) |
