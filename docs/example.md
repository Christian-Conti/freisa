# Example: configuration and complete flow

## 1. Describe the design (`designs/lfsr_bank.yml`)
```yaml
repo: ../examples/lfsr_bank       # RTL directory, relative to this file
top: lfsr_bank
rtl: ["*.sv"]                     # globs; .v/.sv/.vhd picked by extension (or `core: x.core` for FuseSoC)
xdc: []                           # constraints (e.g. boards/zcu106/zcu106/pins.xdc)
clocks: {clk: 4.0}                # optional: clock periods (ns) used by the sign-off timing report
params: {N: 64}                   # optional top-level parameters
explore:                          # optional: several runs per stage, keep the best
  place:
    - {dreamplace: {random_seed: 1000}}
    - {dreamplace: {random_seed: 7}}
```
The board is `targets/<board>.yml` ([platforms](platforms.md)).

### The bundled example on every board
`designs/example/blinky.yml` is one design for all boards. `xdc_per_target: true` makes the flow use `examples/blinky/<TARGET>.xdc`
when it exists (here only `xc7z020.xdc`, the PYNQ pins); without one the design is implemented out of context (no pins).
What `make example TARGET=<board>` produces:

| board | result |
|-------|--------|
| `xc7z020` | `out.bit` (fully open) |
| `zcu104`, `zcu106`, `kv260` | `routed.dcp` plus reports; the bitstream needs Vivado and, with the PS, the block design (`PROFILE=vivado_ps`) |

To run it with a different design, board or profile: `make flow DESIGN=<name> TARGET=<board> [PROFILE=...] [TO=<stage>]`.

## 2. Install once
```
make install            # conda env "freisa", board files, xc7 tools, DREAMPlaceFPGA (skips what is built)
make doctor TARGET=zcu106
```

## 3. Run
```
make example                                           # blinky on the default board (xc7z020): RTL -> .bit, fully open
make example TARGET=zcu104                             # same design on any supported board: zcu104 | zcu106 | kv260 | xc7z020
make flow DESIGN=blinky TARGET=zcu106 TO=route              # UltraScale+: Yosys -> RapidWright -> DREAMPlaceFPGA -> RWRoute
make flow DESIGN=blinky TARGET=zcu106 PROFILE=vivado        # same design, every step in Vivado
make flow DESIGN=blinky TARGET=zcu106 EXPLORE=all           # every supported backend per stage, keep the best
make flow DESIGN=blinky TARGET=zcu106 PROFILE=vivado_ps     # PS board: .bit + .hwh + .xsa

make upload DESIGN=blinky TARGET=xc7z020 TOOL=openfpgaloader   # or TOOL=vivado
```
While it runs the monitor shows one status line (progress bar over the stages, step and total time, CPU and memory of the
running tools, last log line); after each step it prints the step time, average CPU, peak memory, the step's score and the
last lines of its log.

## 4. What you get (`build/<design>/<board>/`)
```
report/
  summary.md  summary.json     stage table (backend, time, cpu, memory, score), artifact and report index
  reports/                     area (Yosys stats, utilization), timing, routing status, DRC, power ...
                               signoff_*.rpt = Vivado reports of the final checkpoint when Vivado is present,
                               otherwise a RapidWright utilization report
  artifacts/                   links to every generated file: out.edif, linked/placed/routed.dcp, out.fasm, out.bit, out.hwh, out.xsa
  logs/                        every tool log
<stage>_v<i>/                  per-variant work dirs when a stage is explored; <stage>_best.json lists all scores
```
Paths printed by the flow are relative to the directory it is started from.

## 5. A complete configuration in one place
```yaml
# designs/my_design.yml
repo: ../../my_rtl
top: top
rtl: ["src/**/*.sv", "src/*.vhd"]
xdc: [../boards/zcu106/zcu106/pins.xdc, constraints.xdc]
clocks: {clk_pl: 5.0}
defines: {USE_FIFO: 1}
stages: {synth: yosys, place: dreamplacefpga, route: rwroute}   # the default open profile
explore:
  synth: [{synth_args: -flatten}, {synth_args: -flatten -abc9}]
  route: all                                                   # every backend that supports the board
bd_tcl: bd/top_bd.tcl                                          # PS boards with vivado_ps
bd_name: design_1
```
