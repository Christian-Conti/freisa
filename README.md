# FREISA — FPGA Reusable and Extensible Infrastructure for Synthesis Automation

Modular open-source RTL → bitstream flow (Yosys · RapidWright · DREAMPlaceFPGA · RWRoute · nextpnr-xilinx · prjxray), with optional Vivado steps.

```
make install                 # conda env + pinned clones of every tool (tools.lock)
make doctor TARGET=zcu106    # which backend of each stage can run for this board
make install-dreamplace      # open UltraScale+ placer
make flow DESIGN=amaretto TARGET=zcu106
make flow DESIGN=example TARGET=zcu106 TO=synth
make help
```

Stages: `sources → synth → netlist → place → route → bitgen`. Each stage has interchangeable backends
(`freisa/stages/*.py`, one `@backend` class each); defaults in `defaults.yml`, overridable per design or per board.

| Add…        | By…                                                                                   |
|-------------|----------------------------------------------------------------------------------------|
| a design    | `designs/<name>.yml`: `repo`, `top`, and either `core:` (FuseSoC) or `rtl:` globs      |
| a board     | `targets/<name>.yml`: `part`, `family`, `yosys_family`, optional `flow:` overrides     |
| a tool      | a module in `freisa/stages/` with a `Backend` subclass (`supports()` + `run()`), a line in `tools.lock` |

## What is open, what is not (honest)
- **Synthesis (Yosys: slang for SV, ghdl for VHDL → EDIF/JSON)** works for any xc7/UltraScale+ part.
- **Full open bitstream exists only for xc7** (prjxray + nextpnr-xilinx): `make install-xc7`, target `xc7z020`.
- **UltraScale+ (zcu104/zcu106/kv260): open end to end up to a routed DCP** — Yosys → RapidWright (EDIF→DCP) → DREAMPlaceFPGA →
  RWRoute. No open UltraScale+ bitstream database exists, so `bitgen: vivado` (`write_bitstream` only) is the one closed step.
  `PROFILE=vivado` / `vivado_ps` run the same steps in Vivado (URAM etc.; `.hwh` for PS boards). Each stage can `explore:` several variants/tools and keep the best.
- Boards with a PS (zcu*, kv260) need the block design for a final bitstream; the OOC netlist alone has no I/O or PS.
- `patches:` in a design file fixes tool-compat RTL issues on copies without touching the source tree.

Docs: [Vivado steps & PS/.hwh](docs/vivado.md) · [platforms](docs/platforms.md) · [add/update flow blocks](docs/adding-blocks.md) · [architecture](docs/architecture.md) · [extending: designs, boards, tools](docs/extending.md) · [install](docs/install.md)
Examples: `make flow DESIGN=counter TO=synth`, `alu`, `uart_tx`, `vhdl_blink`, `example`.
