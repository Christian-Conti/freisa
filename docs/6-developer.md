<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : How the flow engine works; adding and updating tools.
  Module   : 6-developer.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 6. Developer guide

The point of FREISA is that every step is a black box with a fixed contract: it reads files from the previous step and
writes files for the next one. A new tool is one class in one file; nothing else changes.

## Code map
| Path | What it is |
|------|------------|
| `freisa.py` | the entry point: interactive interface, or one command; it calls the scripts in `utils/` |
| `freisa/core.py` | the block registry (`Backend`, `@backend`, `AUTO`), the run context (`Ctx`, `ctx.sh`), `prepare:` commands, explore |
| `freisa/resolve.py` | project file + board file -> one tool per step; the rules between steps (`problems()`) |
| `freisa/stages/` | the blocks, one file per tool family: `sources.py`, `synth_yosys.py`, `rapidwright.py`, `open_pnr.py`, `vivado.py`, `upload.py` |
| `freisa/ifx.py` | FPGA Interchange conversions (RapidWright, python-fpga-interchange) |
| `freisa/vivado.py` | Vivado helpers shared by the Vivado blocks (run a script, constraints, reports) |
| `freisa/monitor.py`, `freisa/report.py` | the run monitor; reports collected after each step |
| `freisa/cli.py`, `freisa/term.py` | `python freisa.py status` / `python freisa.py show`; terminal colors |
| `freisa/tui/` | the interactive interface (see below) |
| `freisa/rw/`, `freisa/yosys/` | RapidWright scripts; Yosys techmap for the open placer |
| `utils/` | `flow.py` (`run`, `doctor`, `upload`), install scripts, `check_flow.py` (`python freisa.py check`), `boards.py` (`python freisa.py install boards`), `uart_test.py` |

## How a run works
1. `freisa/resolve.py` loads `defaults.yml`, the project file and the board file, picks one tool per step
   (resolving `auto`) and applies the design's `per_target` overrides.
2. `utils/check_flow.py` (run by `freisa.py run`) verifies that every selected block can run; if not it stops with suggestions.
3. `utils/flow.py` runs the steps in order. Steps pass files to each other through `ctx.art`:

| Key | Written by | Read by |
|-----|-----------|---------|
| `rtl`, `incdirs`, `defines` | sources | synth |
| `json`, `edif` | synth | netlist |
| `netlist` (`.netlist`, FPGA Interchange logical netlist) | netlist (or Vivado synth) | every later step |
| `phys` (`.phys`, FPGA Interchange physical netlist) | place, route | route, bitgen |
| `dcp`, `fasm` | written only inside a step that needs them (conversion at its edges) | that step |
| `bit`, `hwh`, `xsa` | bitgen | upload, you |

4. `freisa/monitor.py` draws the run monitor; `freisa/report.py` collects reports into `report/` after each step.

## Adding a block
Create `freisa/stages/<name>.py`:
```python
from ..core import Backend, backend

@backend
class MyPlacer(Backend):
    stage, name, tools = "place", "myplacer", ["my-placer"]   # tools: executables that must be on PATH
    metric = "hpwl"                                             # what score() measures (explore compares only equal metrics)

    def supports(self, target):                                 # None = can run; otherwise the reason (shown by check/doctor)
        return super().supports(target) or (None if target["family"] == "xczu" else "UltraScale+ only")

    def run(self, ctx):                                         # in: ctx.art["netlist"] (+ "phys"); out: ctx.art["phys"]
        ctx.sh(["my-placer", ctx.art["netlist"], "-o", ctx.work / "placed.phys"], "myplacer")   # log: <work>/myplacer.log
        ctx.art["phys"] = ctx.work / "placed.phys"

    def score(self, ctx):                                       # lower is better
        return 0.0
```
A tool that does not speak FPGA Interchange converts at its edges with `freisa/ifx.py`: `ifx.to_dcp(ctx, name)` and
`ifx.from_dcp(ctx, dcp, name)` (RapidWright), `ifx.pyif(...)` (python-fpga-interchange). Set `vendor = "vivado"` on a
block that uses Vivado, so that it is shown as `name (vivado)`.

Then select it in a project file (`steps: {place: myplacer}`), add it to `AUTO` in `freisa/core.py` if `auto` should pick it, and
compare it with the current block: `explore: {place: [{backend: dreamplacefpga}, {backend: myplacer}]}`.
`ctx.sh(cmd, log, watch=regex)` stops a tool as soon as `regex` appears in its log.
If the check script should suggest how to install it, add a line to `HINTS` in `utils/check_flow.py`.

## Source tools: tools.lock
Tools built from source are listed in `tools.lock` (`name url ref`). `ref: HEAD` follows the repository's default branch
(latest version, updated by `python freisa.py fetch`); a commit pins the tool. Only two are pinned, because their latest version
does not work in this flow:
- DREAMPlaceFPGA: the commit named in the RapidWright tutorial (its master imports an operator that is never built);
- nextpnr-fpga-interchange: the last nextpnr commit with the `fpga_interchange` architecture (removed from master in 2024).

```sh
python freisa.py outdated                    # which tools follow their latest version, which are pinned
python freisa.py fetch                       # update the ones that follow HEAD (pinned ones are left alone)
python freisa.py update <tool> <commit>      # pin a tool (HEAD to follow its latest version again)
python freisa.py install dreamplace --force  # rebuild after an update (interchange, xc7, prjuray likewise)
python freisa.py run -t zcu104               # smoke test (`python freisa.py run` alone for the xc7 tools)
```
RapidWright comes from pip (`utils/python-requirements.txt`). `utils/build_dreamplace.sh` and
`freisa/stages/rapidwright.py` contain workarounds for DREAMPlaceFPGA, each with a comment.

## Exchange formats between steps
Between steps only FPGA Interchange files travel: `.netlist` (logical netlist) and `.phys` (physical netlist, partial or
complete). See [Tools per step](5-tools.md#the-exchange-format-fpga-interchange) for what every tool reads and writes.

| File | Content | Written / read by |
|------|---------|-------------------|
| `.netlist` | logical netlist (cells, ports, nets) | python-fpga-interchange (from Yosys JSON), RapidWright (from EDIF or DCP); read by every placer and router |
| `.phys` | placement and routing | DREAMPlaceFPGA, nextpnr-fpga_interchange, RWRoute and Vivado (through RapidWright) |
| `.device` | device description (sites, BELs, wires, PIPs) | generated once per part by RapidWright in `install/share/interchange/` (xc7: patched for nextpnr) |

The helpers are in `freisa/ifx.py`. Constraints (pins, clocks) are not part of the Interchange files: steps that need them
read `xdc:` from the project file.

## Adding to the interactive interface

`python freisa.py` runs the package `freisa/tui/`:

| File | What it is |
|------|------------|
| `data.py` | what is read from the repository: projects, boards, builds, serial ports, PC resources |
| `draw.py` | colors, `put`, `box`, `textpane`, `ListView`, popups (`modal_pick`, `modal_text`, `confirm`) |
| `jobs.py` | `Job` (a command in the background, its log, CPU and memory) and `Uart` (serial port monitor) |
| `tabs/` | one file per tab; `tabs/__init__.py` lists them in `TABS` |
| `app.py` | the application: header, tab bar, footer, keys, mouse, help |

Each tab is a class derived from `Tab` (`tabs/base.py`):

- `keys()` returns `(key, hint, function)` entries: a new command is one line there, and the footer shows its hint.
- `draw(w, y, x, h, wd)` draws the tab in its area with the helpers `box`, `put`, `textpane` and `ListView`.
- `self.run(cmd, title)` starts a command in the background (usually `[*FREISA, "<command>", ...]`, i.e. `python freisa.py <command>`); `self.log(...)` shows its output.
- Popups: `modal_pick` (list), `modal_text` (one line), `confirm`.

A new tab: a file in `tabs/` with a `Tab` subclass (`title`, `icon`, `keys()`, `draw()`), added to `TABS`.
Data shown by more than one interface (environment, tools, builds) comes from `freisa/cli.py`, which also prints
`python freisa.py status`.
