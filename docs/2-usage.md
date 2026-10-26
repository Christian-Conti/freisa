<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : Commands, variables, tools per step, explore, upload, reports.
  Module   : 2-usage.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 2. Using the flow

## Steps
```
sources -> synth -> netlist -> place -> route -> bitgen        (upload is a separate command)
```
Each step has one or more tools. The project file chooses the tool of every step (see [Choosing the tools](#choosing-the-tools)).

## Commands
| Command | What it does |
|---------|--------------|
| `make flow DESIGN=<d> TARGET=<b>` | run the flow; `STEPS="place=dreamplacefpga route=rwroute"` changes the tool of some steps for this run only |
| `make check` | check that the selected tools are available; suggest fixes if not |
| `python freisa.py` | interactive interface, see below |
| `make status` | dashboard: environment, tools (commit, pinned or latest), installed boards, projects and latest builds; `PART=env\|tools\|boards\|projects\|builds` for one panel |
| `make show DESIGN=<d> TARGET=<b>` | one build: time/cpu/memory of each step, area, timing and output files |
| `make doctor` | every tool of every step and whether it can run: for all boards, or only `TARGET=<b>` |
| `make uart-test` | send data on the board's PL UART and check the echo (uart_loopback example; `PORT=`, `BAUD=`) |
| `make upload` | program `build/<d>/<b>/out.bit` on the board |
| `make install`, `make uninstall` | install / remove everything |
| `make install-boards [BOARD=<name>]` | install the boards of `boards.yml` (board files, pin file, `targets/<name>.yml`) |
| `make install-xc7`, `make install-interchange`, `make install-prjuray`, `make install-dreamplace` | build one open tool (`FORCE=1` to rebuild) |
| `make outdated`, `make update NAME=<tool> [REF=<commit>]` | show which tools follow their latest version and which are pinned / pin one |
| `make clean` | delete `build/` |
| `make help` | this list with every variable |

## Variables
| Variable | Default | Meaning |
|----------|---------|---------|
| `DESIGN` | `blinky` | project name (`designs/**/<name>.yml`) or path; `make flow` alone builds blinky for pynq-z2 |
| `TARGET` | `pynq-z2` | board file name in `targets/` |
| `FROM`, `TO` | `sources`, `bitgen` | first and last step; `FROM` reuses the outputs of a previous run |
| `TOOL`, `BIT` | `openfpgaloader`, `out.bit` | for `make upload` |

## Choosing the tools
Every project file has a `steps:` section (tool of each step, all boards) and a `boards:` section (changes for one board):
```yaml
steps:   {synth: yosys, netlist: auto, place: auto, route: auto, bitgen: auto, upload: openfpgaloader}
boards:
  zcu104: {bitgen: open_io}
```
`auto` picks the first open tool that works on the board; `all` runs every tool that works and keeps the best;
`all_open` does the same with open tools only (no tool marked `(vivado)`); a step not
listed is `auto`. All values and tools: [Project files](3-projects.md#values-of-steps--boards).

`make check` validates the choice for the board: for every step whose tool cannot run it prints why, how to install it,
and which tools work there instead, as the line to put in the project file. The same check runs before every
`make flow` and `make upload`. `make doctor` lists every tool of every step and whether it can run, for every board (`TARGET=<board>` for one).

## Several runs per step (explore)
A step can run several variants in parallel and keep the best one; the next step continues from it.
```yaml
# in the project file
explore:
  synth: [{synth_args: -flatten}, {synth_args: -flatten -abc9}]   # same tool, different options
  route: all                                                        # every block available on the board
```
To explore every tool that works for a step, set that step to `all` (or `all_open`, without Vivado) in the project file
(`steps:` or `boards:`). Results are compared only between tools that measure the same thing: the tool `auto` would
pick is run first and sets the metric, so with `all` a Vivado variant is run and reported but kept only if it is
comparable (for example, on xc7 nextpnr places during routing, so Vivado's placement is reported and not kept):
```yaml
steps: {place: all}
```
Each variant runs in `build/<d>/<b>/<step>_v<i>/`; `<step>_best.json` lists the scores.
Scores are compared only between blocks that measure the same thing (area for synthesis, wirelength or HPWL for the open
placer and router, worst slack for Vivado steps).

## Programming the board
```sh
make upload TARGET=zcu104                       # openFPGALoader
make upload TARGET=zcu104 TOOL=vivado           # Vivado hardware manager
make upload JTAG=38138                          # a specific JTAG cable (USB serial)
make upload BIT=path/to/file.bit
```
`make upload` scans every FTDI JTAG cable on USB and reads the FPGA on each. With one board matching `TARGET` it
programs it directly; with several devices on a terminal it shows them and asks which one:
```
    #  SERIAL         USB    CABLE                        FPGA
    1  XFL1SGME2JVO   1:7    Xilinx ML Carrier Card       -
    2  38138          1:8    Xilinx JTAG+3Serial          xczu7cg/eg/ev ✔
    board to program [2]:
```
Both tools use the chosen cable. Without a terminal, several matching boards require `JTAG=<serial>`.

## Monitor and reports
While running, a progress bar shows the step, step and total time, CPU and memory of the tools, and the last log line.
After each step: time, average CPU, peak memory, score and the last log lines. Colors only on a terminal (`NO_COLOR=1`
disables them); `flow.log` in the build folder has the same text without colors. At the end the flow writes
`report/` (see [Getting started](1-getting-started.md#where-the-results-are)), including
area and timing reports of the result, made by open tools (below). Vivado reports are added only with
`signoff: vivado` in the project file (`report/reports/signoff_*.rpt`).

### Area and timing reports
Every run writes `report/reports/area.rpt` and `report/reports/timing.rpt`; their main values also appear in
`report/summary.md` (sections "Area" and "Timing").

| Tools of the run | `area.rpt` | `timing.rpt` |
|------------------|-----------|-------------|
| any (after synthesis) | cells by type (Yosys) | — |
| xc7, `nextpnr_xilinx` | used resources (nextpnr) | maximum frequency per clock, critical path (nextpnr) |
| xc7, `nextpnr_interchange` | used resources (nextpnr) | not available: nextpnr-fpga_interchange has no timing model (use `route: nextpnr_xilinx` for timing) |
| UltraScale+ (`rwroute`, `open_io`) | cells by type, sites used, routed nets (RapidWright) | requirement, critical path, slack, path details, wirelength (RapidWright timing model) |

The clock requirement comes from `clocks:` in the project file (written into the design by `open_io`); without it only
the critical path is reported.

## Interactive interface

`python freisa.py` opens a terminal interface (it switches to the FREISA conda env by itself). It works from 60x20:
below 110 columns the panes are stacked instead of side by side. Tabs are switched with `1`-`6`, `Tab` or a mouse click;
the wheel scrolls logs. The two bottom lines list the keys of the current tab, `?` shows them all.
The tab bar shows the PC resources on every tab (CPU, memory; red above 90%). Every command run from the interface shows
in its log title the elapsed time, the CPU and memory of all its processes (Vivado, Java, ...) and the memory peak.

| Tab | What it does |
|---|---|
| 1 Home | overview: tools built, boards installed, projects, builds, Vivado; the open flow `auto` picks for each board family; every build: `Enter` opens its reports, `u` programs it, `r` runs it again, `D` deletes it |
| 2 Flow | choose design, board, FROM/TO and the tool of every step (Enter on a step: every tool with whether it can run on that board); `r` run, `s` synthesis only, `c` check, `u` upload, `e` edit the project file. Progress per step and two live logs: the flow and the tool running now |
| 3 Builds | every build: steps, area, timing, flow log, summary (`←→`); `u` programs its bitstream, `r` runs it again, `D` deletes it |
| 4 Boards | boards.yml: installed or not, part, source, generated settings and board files; `i` installs one board, `a` all, `e` edits boards.yml |
| 5 Hardware | JTAG cables found on USB with their FPGA and boards, and their serial ports (the PL UART is marked); `p` programs a bitstream, `R` resets the FPGA (openFPGALoader; on Zynq UltraScale+, which it cannot reset, it reloads the last bitstream programmed from this tab), `Y` resets the whole board (PS and PL, Vivado xsdb); `o` opens a UART monitor as a conversation, sent messages on the left and received on the right (`b` baud, `i` type and send, `h` raw hex view, `C` clear), `t` loopback test |
| 6 Tools | tools.lock: commit, pinned or latest, built or not; `i` installs one, `u` moves it to the latest commit, `o` lists the outdated ones; environment |

Commands run in the background: you can change tab while a flow runs; `x` stops the command of the tab, `q` quits
(asking first if something still runs). Tools chosen in the Flow tab apply to that run only (`STEPS=`); to keep them,
write them in the project file (`e`).
