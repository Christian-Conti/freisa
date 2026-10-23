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

## How a run works
1. `freisa/resolve.py` loads `defaults.yml`, the project file and the board file, picks one tool per step
   (resolving `auto`) and applies the design's `per_target` overrides.
2. `utils/check_flow.py` (run by the Makefile) verifies that every selected block can run; if not it stops with suggestions.
3. `flow.py` runs the steps in order. Steps pass files to each other through `ctx.art`:

| Key | Written by | Read by |
|-----|-----------|---------|
| `rtl` | sources | synth |
| `json`, `edif` | synth | netlist |
| `netlist` (`.netlist`, FPGA Interchange logical netlist) | netlist (or Vivado synth) | every later step |
| `phys` (`.phys`, FPGA Interchange physical netlist) | place, route | route, bitgen |
| `dcp`, `fasm` | written only inside a step that needs them (conversion at its edges) | that step |
| `bit`, `hwh`, `xsa` | bitgen | upload, you |

4. `freisa/ui.py` draws the monitor; `freisa/report.py` collects reports into `report/` after each step.

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

## Pinned tools
Tools built from source are pinned in `tools.lock` (`name url commit`). `make fetch TOOLS=<name>` clones only what is
asked, and skips tools already at the pinned commit. To update one:
```sh
make outdated                         # pinned commit vs upstream
make update NAME=dreamplacefpga       # or REF=<tag/branch/commit>
make install-dreamplace FORCE=1       # rebuild (install-interchange for nextpnr-fpga_interchange, install-xc7 for prjxray)
make flow TARGET=zcu104               # smoke test (`make flow` alone for the xc7 tools)
```
RapidWright comes from pip (`utils/python-requirements.txt`). DREAMPlaceFPGA is pinned to the commit named in the
RapidWright tutorial; `utils/build_dreamplace.sh` and `freisa/stages/rapidwright.py` contain workarounds for it,
each with a comment. Check whether they are still needed after an update.

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
