# Extending

## Add a design (any RTL)
Create `designs/<name>.yml`:
```yaml
repo: ../path/to/rtl      # relative to this file
top: my_top
rtl: ["src/*.sv", "src/*.v", "src/*.vhd"]   # or `core: my.core` (+ `core_target:`) for FuseSoC
xdc: [constraints.xdc]    # optional
defines: {FOO: 1}         # optional, read_slang -D
params: {WIDTH: 16}       # optional, read_slang -G (top-level parameters)
vhdl_top: some_entity     # when VHDL is mixed into SV (default: top)
slang_args: --compat vcs  # optional extra slang flags
yosys_pre: [attrmap -remove ram_style]   # optional raw Yosys commands before synth_xilinx
patches:                  # optional tool-compat fixes applied to copies
  - {file: x.sv, from: "old", to: "new"}
```
Run: `make flow DESIGN=<name> TARGET=<board>`. Examples: `designs/{example,counter,alu,uart_tx,vhdl_blink}.yml`.

## Add a board
Create `targets/<board>.yml`:
```yaml
part: xc7a35tcsg324-1
family: xc7              # xc7 enables the open nextpnr-xilinx/prjxray path
yosys_family: xc7        # synth_xilinx -family value
chipdb: ...              # xc7 only: nextpnr-xilinx chip database
db_root: ...             # xc7 only: prjxray-db directory
flow: {netlist: none, place: in_route, route: nextpnr_xilinx, bitgen: prjxray}   # optional overrides
needs_ps: true           # set when the PL needs a Zynq PS (blocks OOC bitgen)
```
Then `make doctor TARGET=<board>` shows what can run. A new family with an open toolchain needs only its backends (below).

## Add a tool / backend
Drop `freisa/stages/<tool>.py`:
```python
from ..core import Backend, backend

@backend
class MyPlacer(Backend):
    stage, name, tools = "place", "myplacer", ["my-placer"]   # tools: executables checked by supports()
    def supports(self, target):                               # None = usable, else a reason string
        return super().supports(target) or (None if target["family"] == "xc7" else "xc7 only")
    def run(self, ctx):                                       # read ctx.art / ctx.cfg / ctx.target, write ctx.art
        ctx.sh(["my-placer", ctx.art["dcp"]], "myplacer", cwd=ctx.work)
```
Select it with `stages: {place: myplacer}` in a design or `flow:` in a board. Add its repo and commit to `tools.lock`.

## Explore: several runs, keep the best per stage
In a design file, `explore:` lists variants per stage. Each variant is a config overlay and may name another tool with `backend:`.
Variants run in parallel (`-j N`), each in `build/<design>/<board>/<stage>_v<i>/`; the lowest `Backend.score()` wins and its
artifacts feed the next stage; `<stage>_best.json` records every score. Unavailable backends are skipped.
```yaml
explore:
  synth: [{synth_args: -flatten}, {synth_args: -flatten -abc9}]
  place: [{backend: dreamplacefpga, dreamplace: {random_seed: 1}}, {backend: dreamplacefpga, dreamplace: {random_seed: 2}}]
  route: [{backend: rwroute}]
```
Scores are only comparable within a stage's metric (synth: LUT+FF+weighted hard blocks; place: HPWL; route: wirelength),
so mix tools in one stage only when they report the same metric. Override `score()` in a backend to change it.

## Bitstream
`bitgen: prjxray` (xc7) is fully open. For UltraScale+ the only registered open candidate is `prjuray`; it reports unavailable
(no routed-DCP → FASM exporter, device coverage unverified), so `vivado` (`write_bitstream` only) is the default. When an open
writer matures, implement `Prjuray.run` and set `bitgen: prjuray` in the board file.
