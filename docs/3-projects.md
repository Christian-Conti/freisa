<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : Project files: every key, and the blinky project explained entry by entry.
  Module   : 3-projects.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 3. Project files

A project is one YAML file under `designs/` (any subfolder; the bundled example is `designs/examples/blinky.yml`).
`make flow DESIGN=<name>` finds `designs/**/<name>.yml`; a path to any `.yml` works too.
The project file says everything about a design: where its sources are, which tool runs each step, and what changes
from board to board. There is no other configuration file.

## How a project file is read
1. The keys at the top level apply to every board.
2. `steps:` gives the tool of each step; `boards.<TARGET>:` overrides some of them for one board.
3. `per_target.<TARGET>:` overrides design keys (pins, top, ...) for one board; `per_target.<TARGET>@<tool>:` only when that
   tool runs in some step on that board.
`make check TARGET=<board>` shows the result: which tool each step will use and whether it can run.

## All keys
| Key | Meaning |
|-----|---------|
| `repo` | folder with the RTL, relative to the project file (or absolute); other paths are relative to it |
| `top` | top-level module or entity |
| `rtl` | source files as glob patterns; language from the extension (`.v`, `.sv`, `.vhd`, `.vhdl`) |
| `core`, `core_target` | instead of `rtl`: a FuseSoC `.core` file and its target; FREISA runs `fusesoc run --setup` of that target (dependencies, generators, defines) and reads the resulting file list as with `edam` |
| `fusesoc` | `{conda, env, flags}`: conda env where `fusesoc` runs, extra variables, extra `fusesoc run` options |
| `filelist` | instead of `rtl`: a `.f`/`.vc` file list (files, `+incdir+`, `+define+`) |
| `edam` | instead of `rtl`: the `.eda.yml` that `fusesoc run --setup` writes for a target (glob allowed: the newest file is used); gives RTL, include dirs and defines |
| `prepare` | commands run before the sources are read, in the repo: a string, or `{run, cwd, conda, env}` (`conda`: run inside that conda env, e.g. the project's own generators) |
| `steps` | tool of each step for every board (`auto`, `all`, `all_open` or a tool name, see below) |
| `boards` | `{<board>: {<step>: <tool>}}`: tools for one board, merged over `steps` |
| `per_target` | `{<board>: {...}}` or `{<board>@<tool>: {...}}`: design keys for one board (or board + tool) |
| `xdc` | constraint files; for a bitstream every port needs `PACKAGE_PIN` and `IOSTANDARD` |
| `clocks` | `{port: period_ns}`: clock constraints (`open_io`, timing report) |
| `signoff` | `vivado`: also run Vivado's reports (utilization, timing, DRC, power) on the final design; default: open reports only |
| `pins` | `auto`: free pins picked automatically for `open_io`; only to check that a bitstream can be built, never load it |
| `synth_args` | extra Yosys `synth_xilinx` options |
| `defines`, `params` | Verilog defines and top-level parameters |
| `vhdl_top` | VHDL entity to elaborate when VHDL is mixed with SystemVerilog |
| `slang_args`, `yosys_pre` | extra SystemVerilog frontend options / raw Yosys commands before synthesis |
| `patches` | `[{file, from, to}]`: text fixes applied to copies of the RTL |
| `explore` | several variants of a step, best one kept ([Using the flow](2-usage.md#several-runs-per-step-explore)) |
| `wrap` | `{top, rtl, cell}`: hand-written I/O wrapper for `bitgen: vivado_wrap` |
| `bd_tcl`, `bd_name` | block design script and name, for `bitgen: vivado_ps` |
| tool options | `dreamplace_iterations`, `dreamplace_retries`, `dreamplace: {...}`, `rwroute_args`, `vivado_synth_args`, `opt_directive`, `place_directive`, `route_directive`, `phys_opt`, `post_route_phys_opt` |

### Values of `steps` / `boards`
| Value | Meaning |
|-------|---------|
| `auto` | first open-source tool that works on the board (default of a step that is not listed) |
| `all` | every tool that works on the board for this step is run, the best result is kept |
| `all_open` | like `all`, with open tools only (no `(vivado)` tools) |
| a name | that tool. `make doctor TARGET=<board>` lists every tool of every step |

| Step | Tools (`auto` picks the first that works) |
|------|------------------------------------------|
| `synth` | `yosys`, `vivado` |
| `netlist` | `rapidwright_if` (UltraScale+), `yosys_json_if` (xc7), `vivado_link`, `none` |
| `place` | `dreamplacefpga` (UltraScale+), `in_route` (xc7), `vivado` |
| `route` | `rwroute` (UltraScale+), `nextpnr_interchange` (xc7), `nextpnr_xilinx` (xc7, open chip database), `vivado` |
| `bitgen` | `prjxray` (xc7), `prjuray` (UltraScale+, see [Tools](5-tools.md#project-u-ray-ultrascale)), `open_io (vivado)`, `vivado_wrap (vivado)`, `vivado`, `vivado_ps (vivado)` |
| `upload` | `openfpgaloader`, `vivado` |

## The blinky project, entry by entry
```yaml
repo: ../../examples/blinky
```
The RTL is in `examples/blinky/` (two folders up from `designs/examples/`). Pin files below are looked up there too.
```yaml
top: blinky
rtl: ["*.v"]
```
The top module is `blinky` (a 26-bit counter whose top bit drives `led`). `*.v` also picks up `blinky_diff.v`, a top for
boards with a differential clock; it is only used where a board setting names it.
```yaml
synth_args: -flatten
```
Yosys merges the hierarchy into one module before mapping.
```yaml
steps:
  synth: yosys
  netlist: auto
  place: auto
  route: auto
  bitgen: auto
  upload: openfpgaloader
```
Open tools everywhere. With `auto`, pynq-z2 gets nextpnr-fpga_interchange and prjxray (a complete open bitstream); UltraScale+
boards get RapidWright, DREAMPlaceFPGA and RWRoute, and no bitstream writer (none exists for UltraScale+).
```yaml
boards:
  zcu104: {bitgen: open_io}
  zcu106: {bitgen: open_io}
```
On ZCU104/ZCU106 the bitstream step is `open_io`: open tools also place the I/O buffers and clock buffer and route them,
and Vivado only runs `write_bitstream`. KV260 is left out: it has no PL clock oscillator (its PL clock comes from the PS),
so blinky stops at the routed checkpoint there (`make flow TARGET=kv260 TO=route`).
```yaml
per_target:
  pynq-z2: {xdc: [pynq-z2.xdc]}
```
On the PYNQ-Z1/Z2, pins come from `examples/blinky/pynq-z2.xdc` (125 MHz single-ended clock, LED 0).
```yaml
  zcu104@open_io: {xdc: [zcu104.xdc], clocks: {clk: 3.333}}
  zcu106@open_io: {xdc: [zcu106.xdc], clocks: {clk: 3.333}}
```
When `open_io` runs on ZCU104/ZCU106: the XDC gives the 300 MHz differential clock as `clk_p`/`clk_n` and the LED pin;
`open_io` connects `clk_p`/`clk_n` to port `clk` through a differential buffer and a global clock buffer. `clocks` gives
the 3.333 ns period.
```yaml
  zcu104@vivado_wrap: {xdc: [zcu104.xdc], wrap: {top: blinky_diff, rtl: [blinky_diff.v], cell: core}}
  zcu104@vivado: {top: blinky_diff, xdc: [zcu104.xdc]}
```
Ready-made alternatives (same for zcu106): with `bitgen: vivado_wrap`, Vivado implements the I/O wrapper `blinky_diff`
around the open-routed design (instance `core`); with every step in Vivado, the top becomes `blinky_diff` directly.
They are inactive until the corresponding tool is chosen in `boards:`.

## Second example: uart_loopback
`designs/examples/uart_loopback.yml` uses the same keys as blinky. Its RTL (`examples/uart_loopback/`) synchronises the
UART input `rx` with two flip-flops and drives `tx` with it; `led` lights for a moment on every received start bit.
The per-board XDC files give the PL UART pins (`uart2_PL_TX`/`uart2_PL_RX` in the board files), the differential
300 MHz clock and the LED. Only boards whose USB serial port reaches FPGA pins are listed (ZCU104, ZCU106).

## Pin constraints for a bitstream
For every port bit of the top: `PACKAGE_PIN` and `IOSTANDARD` in the XDC, with the port name (`led`, `data[3]`).
A differential input is written as two ports `<port>_p` and `<port>_n` (the design keeps one port `<port>`).
Clock inputs (ports that drive flip-flop clocks) get a global clock buffer automatically; give their period in `clocks:`.
Pins of a supported board can be copied from `boards/<board>/<board>/pins.xdc` (created by `make install-boards`).
Not supported yet by `open_io`: `inout` ports and differential outputs.

## A new project
```yaml
repo: ../../my_rtl
top: top
rtl: ["src/*.sv"]
boards:
  zcu104: {bitgen: open_io}
per_target:
  zcu104: {xdc: [zcu104_pins.xdc], clocks: {clk: 5.0}}
```
Save it as `designs/my_project.yml` and run `make flow DESIGN=my_project TARGET=zcu104`.

## A project with its own generators and Vivado scripts
A repository that generates its RTL and its file list itself is used as it is: `prepare` runs its commands, `core` reads
its FuseSoC target (or `edam` an EDAM file already written). More: [Real designs](9-real-designs.md).
```yaml
per_target:
  zcu104:
    prepare:
      - {run: make generate, conda: my-env}
    core: my_soc.core
    core_target: zcu104
    fusesoc: {conda: my-env}
    xdc: [constraints/zcu104.xdc]
```
