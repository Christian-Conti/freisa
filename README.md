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

## Quick start
```sh
make install                       # one time: conda env, board files, open tools
make flow                          # default: blinky on PYNQ-Z1/Z2 (xc7z020), RTL -> out.bit, open tools only
make flow TARGET=zcu104            # blinky on ZCU104: open tools, Vivado only writes the bitstream
make flow DESIGN=uart_loopback TARGET=zcu104 && make upload DESIGN=uart_loopback TARGET=zcu104 && make uart-test TARGET=zcu104
make help                          # every command and variable
```

## Documentation
Read in this order:

1. [Getting started](docs/1-getting-started.md): install, first run, where the results are.
2. [Using the flow](docs/2-usage.md): commands, variables, explore, upload, reports.
3. [Project files](docs/3-projects.md): one file per design with sources, tools per step and board settings.
4. [Boards](docs/4-boards.md): supported boards (PYNQ-Z1/Z2, ZCU104, ZCU106, KV260, AUP-ZU3 8 GB), tools per step, adding a board in `boards.yml`.
5. [Tools per step](docs/5-tools.md): what each block does and its limits (including Vivado and the PS / `.hwh`).
6. [Developer guide](docs/6-developer.md): how the engine works, adding or updating a block.
7. [Examples](docs/7-examples.md): blinky and uart_loopback on every board: build, program, test.
8. [open_io](docs/8-open-io.md): how UltraScale+ bitstreams are made with open tools for everything except `write_bitstream`.

## Repository layout
| Path | Content |
|------|---------|
| `Makefile`, `flow.py` | entry points |
| `designs/` | project files, one per design (examples: `designs/examples/blinky.yml`, `uart_loopback.yml`) |
| `examples/` | RTL and pin files of the bundled examples |
| `targets/` | board files (generated from `boards.yml`) |
| `freisa/` | flow engine (`core`, `resolve`, `ui`, `report`, `term`), tools of each step (`freisa/stages/`), RapidWright scripts (`freisa/rw/`) |
| `utils/` | install, check and helper scripts |
| `defaults.yml` | default tool options |
| `boards.yml` | the boards to install (you edit it; `make install-boards`) |
| `tools.lock`, `boards.lock` | source tools (latest version or pinned commit) / commits of the fetched board files |
| `build/<design>/<board>/` | outputs (created by the flow) |
