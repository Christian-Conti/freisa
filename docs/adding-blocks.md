# Adding and updating flow blocks

A *block* is one backend of one stage (`sources, synth, netlist, place, route, bitgen`). Blocks are independent: they only
read/write `ctx.art` (artifacts), so replacing one never touches the others.

## 1. Add a new block (new tool, new release, new alternative)
1. **Pin the tool**: add a line to `tools.lock` (`name url commit`). `make fetch` clones it at that commit into `third_party/<name>`.
   If it needs building, add `utils/build_<name>.sh` and a `install-<name>` target in the `Makefile` (copy `install-dreamplace`),
   and call `utils/check_deps.sh` first like the others.
2. **Write the backend**: `freisa/stages/<name>.py`
   ```python
   from ..core import Backend, backend
   @backend
   class MyPlacer(Backend):
       stage, name, tools = "place", "myplacer", ["my-placer"]     # tools = executables that must be on PATH
       def supports(self, target):                                  # None = usable; else the reason (shown by `make doctor`)
           return super().supports(target) or (None if target["family"] in ("xczu",) else "xczu only")
       def run(self, ctx):                                          # read ctx.art/ctx.cfg/ctx.target, write ctx.art
           ctx.sh(["my-placer", ctx.art["dcp"], "-o", ctx.work / "out.dcp"], "myplacer")   # logs to <work>/myplacer.log
           ctx.art["dcp"] = ctx.work / "out.dcp"
       def score(self, ctx):                                        # lower = better; used by `explore:`
           return float(...)                                        # e.g. parse HPWL from the log
   ```
   Artifact contract between stages: `rtl` → `edif`/`json` (synth) → `dcp` (netlist/place/route) → `fasm` → `bit`.
   A block that cannot honour the contract should convert at its edges, not change what neighbours expect.
3. **Select it**: `stages: {place: myplacer}` in a design file, or `flow:` in a board file. `make doctor TARGET=<board>` must show it `ok`.
4. **Compare it** against the current block without replacing it: `explore: {place: [{backend: dreamplacefpga}, {backend: myplacer}]}`
   (needs the same score metric). Keep the loser registered; it costs nothing.
5. **Smoke-test**: `make flow DESIGN=lfsr_bank TARGET=<board>` for UltraScale+, `DESIGN=blinky_xc7 TARGET=xc7z020` for the open xc7 path.

## 2. Update a block when a new release comes out
```
make outdated                 # every pin vs upstream HEAD
make update NAME=dreamplacefpga   # re-pin to upstream HEAD   (or REF=<tag/branch/commit>)
make fetch                    # check out the new commit
make install-dreamplace       # rebuild if the tool has an install-* target (install-xc7 for nextpnr-xilinx/prjxray)
make flow DESIGN=lfsr_bank TARGET=zcu106 TO=route    # smoke test; then DESIGN=blinky_xc7 TARGET=xc7z020
```
Rules of thumb:
- Pins are exact commits; nothing changes until you run `make update`. Commit `tools.lock` together with the code that needs it.
- RapidWright is used as the pip package (it bundles the jar): bump `rapidwright==` in `utils/python-requirements.txt` and re-run `make conda-env`.
- A failing smoke test after an update means the block's *adapter* needs a fix (CLI flags, file names); fix it in the
  block's `run()` only. Several blocks here carry workarounds for their upstream (see comments in `freisa/stages/rapidwright.py`,
  `utils/build_dreamplace.sh`); on an update, check whether each is still needed and delete the ones that are not.
- To go back, `make update NAME=<name> REF=<old commit>` and `make fetch`.
- Known pin: DREAMPlaceFPGA is pinned to the commit named in RapidWright's tutorial because current `master` imports an op that is not built.

## 3. Add a new board
See [extending](extending.md#add-a-board) and [platforms](platforms.md).
