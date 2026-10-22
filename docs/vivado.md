# Optional Vivado steps

The open flow cannot map everything (URAM, LUTRAM/SRL, wide muxes, carry chains, I/O buffers, PS) and cannot write
UltraScale+ bitstreams. If Vivado is installed (`$VIVADO`, `PATH`, or `/eda/Xilinx/Vivado/<version>/bin/vivado`, preferring 2024.1), every step has a Vivado backend, and steps exchange
checkpoints, so you can run all of them or mix them with open ones. `make doctor` shows what is available.

| stage | backend | what it runs |
|-------|---------|--------------|
| synth | `vivado` | `synth_design` on the RTL (URAM/BRAM/LUTRAM/SRL/DSP/carry mapped natively); writes `synth.dcp`, `synth.edf`, utilization and timing reports |
| netlist | `vivado_link` | `link_design` of a Yosys EDIF + constraints (for `synth: yosys` with Vivado implementation) |
| place | `vivado` | `opt_design` + `place_design` (+ `phys_opt_design` with `phys_opt: true`); `opt_directive`, `place_directive` |
| route | `vivado` | `route_design` (+ post-route `phys_opt_design` with `post_route_phys_opt: <directive>`); `route_directive`; timing/utilization/route-status reports |
| bitgen | `vivado` | `write_bitstream` from the routed checkpoint (PL only) |
| bitgen | `vivado_ps` | boards with a Zynq PS: project + block design -> synthesis, implementation, bitstream; produces `out.bit`, **`out.hwh`** and `out.xsa` |

## Presets
`make flow PROFILE=<name>` (profiles live in `defaults.yml`; they override design and board stage choices):

| profile | steps |
|---------|-------|
| `open` (default) | Yosys, RapidWright, DREAMPlaceFPGA, RWRoute, Vivado bitgen only |
| `vivado` | Vivado for every step |
| `vivado_ps` | Vivado for every step, block design with PS, `.bit` + `.hwh` + `.xsa` |
| `yosys_vivado` | Yosys synthesis, Vivado link/place/route/bitgen |

Single steps can also be chosen per stage in a design (`stages: {synth: vivado, place: dreamplacefpga}`) or compared with
`explore:` (`explore: {place: [{backend: vivado, place_directive: Explore}, {backend: dreamplacefpga}]}`). For Vivado steps
the explore score is minus the worst negative slack from the step's timing report.

## PS boards and the hardware handoff (`.hwh`)
Boards with a PS (`needs_ps: true`: zcu104, zcu106, kv260) need a block design. Add to the design file:
```yaml
bd_tcl: fpga/scripts/Xilinx/amaretto_bd.tcl   # relative to `repo`; creates the BD (PS8, clocks, AXI) and instantiates the RTL top
bd_name: design_1
vivado_jobs: 8
```
`vivado_ps` copies the BD's `hw_handoff/<bd_name>.hwh` and exports an `.xsa` (`write_hw_platform -fixed -include_bit`) next to
`out.bit`. The PL bitstream alone (`bitgen: vivado`) is refused on PS boards, because without the PS configuration it cannot
run on the board. A checkpoint produced by the open placer/router cannot be put inside a block design (module references
need RTL), so PS builds use the Vivado profiles.

Tested here with Vivado 2024.1: `synth`, `place` and the sign-off reports on open-flow checkpoints. `vivado_ps` (block design) is not yet
exercised; check the generated `*.tcl` files in the stage directories first.
