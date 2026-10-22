# FREISA — FPGA Reusable and Extensible Infrastructure for Synthesis Automation

Modular RTL → bitstream flow built from open-source tools, with optional Vivado steps. Every step is a swappable block;
designs and boards are small YAML files, so any RTL and any supported chip can be added without touching the tools.

## Quick start
```
make install                      # conda env, board files, open tools (built once)
make example                      # blinky: RTL -> .bit on a Zynq-7000, no Vivado
make doctor TARGET=zcu106         # which block of each step can run
make flow DESIGN=<design> TARGET=<board>
make upload TARGET=<board> TOOL=openfpgaloader
make help
```

## The flow
```
 sources -> synth -> netlist -> place -> route -> bitgen -> upload
 (RTL list) Yosys    RapidWright DREAMPlaceFPGA RWRoute   prjxray   openFPGALoader
            Vivado   Vivado     nextpnr-xilinx nextpnr-xilinx Vivado  Vivado HW manager
```
Each arrow is a checkpoint (`edif`/`json`, `dcp`, `fasm`, `bit`), so open and Vivado blocks can be mixed per step.
`PROFILE=open|vivado|vivado_ps|yosys_vivado` picks a preset, `explore:` / `EXPLORE=all` runs several variants or every supported
backend and keeps the best, and a live monitor shows progress, time, CPU and memory. Each run writes `report/` with area,
timing and routing reports plus all generated artifacts.

## Make targets
| Target | What it does |
|--------|--------------|
| `install` / `uninstall` | everything (env, boards, tools) / remove it |
| `install-boards` | pull the supported boards from XilinxBoardStore, refresh `boards.lock` (`PIN=1` keeps it) |
| `install-xc7`, `install-dreamplace` | build the open tools (skipped when present, `FORCE=1`) |
| `doctor` | availability of every block for a board |
| `flow` | run the flow (`DESIGN`, `TARGET`, `PROFILE`, `EXPLORE`, `FROM`, `TO`) |
| `example` | run a bundled example |
| `upload` | program the board (`TOOL=openfpgaloader\|vivado`, `BIT=`) |
| `outdated` / `update` | compare/re-pin the tools in `tools.lock` |

## Supported platforms
Zynq UltraScale+ (ZCU104, ZCU106, Kria KV260) and Zynq-7000 (PYNQ-Z1/Z2). Full table with the tools available per step: [docs/platforms.md](docs/platforms.md).

## Documentation
- [Example: configuration and complete flow](docs/example.md)
- [Supported platforms and adding a board](docs/platforms.md)
- [Architecture](docs/architecture.md) · [Extending](docs/extending.md) · [Adding and updating flow blocks](docs/adding-blocks.md)
- [Vivado steps, PS boards and `.hwh`](docs/vivado.md) · [Install](docs/install.md)

## Layout
```
Makefile  flow.py          entry points            designs/  targets/   one YAML per design / board
freisa/                    flow engine and blocks  tools.lock boards.lock pinned tools / boards
utils/                     install scripts         examples/             small RTL designs
```
