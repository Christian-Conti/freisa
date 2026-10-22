# Architecture

`flow.py` loads `defaults.yml`, merges the design file (`designs/<name>.yml`), loads the board (`targets/<board>.yml`),
and runs the selected stages in order. Stages exchange data through `ctx.art`, a dict of artifacts:

| artifact | produced by | consumed by |
|----------|-------------|-------------|
| `rtl`    | sources     | synth       |
| `edif`, `json` | synth | netlist/place/route (RapidWright reads edif, nextpnr-xilinx reads json) |
| `dcp`    | netlist, place, route (each replaces it) | next stage (bitgen: Vivado) |
| `fasm`   | route (nextpnr-xilinx) | bitgen (prjxray) |
| `bit`    | bitgen      | you         |

Stages: `sources → synth → netlist → place → route → bitgen`. Backend choice precedence: board `flow:` > design `stages:` > `defaults.yml`.
Outputs and logs: `build/<design>/<board>/` (one `<step>.log` per tool call, `synth.ys` is the generated Yosys script).

## Backends shipped
| stage | backend | notes |
|-------|---------|-------|
| sources | `core` | FuseSoC `.core`, no FuseSoC install needed |
| sources | `files` | `rtl:` globs in the design file |
| synth | `yosys` | yosys-slang (SV/Verilog) + ghdl plugin (VHDL) → `synth_xilinx` |
| netlist | `rapidwright_edif` | EDIF → DCP in RapidWright, no Vivado |
| place | `dreamplacefpga` | DcpToInterchange → Bookshelf → DREAMPlaceFPGA → DCP; needs `make install-dreamplace` |
| route | `rwroute` | RapidWright RWRoute (timing-driven, multithreaded) |
| bitgen | `vivado` | `write_bitstream` only: the single closed step, for UltraScale+ |
| route | `nextpnr_xilinx` | xc7 only |
| bitgen | `prjxray` | xc7 only |

`make doctor TARGET=<board>` prints every backend with `ok` or the reason it cannot run.

Vivado backends for every step (optional): see [vivado.md](vivado.md).
