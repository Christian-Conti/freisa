# Supported platforms

`make doctor TARGET=<board>` is the source of truth for what runs on a board. Board files live in `targets/`.

| Board file | Part | Family | Synth (Yosys) | Place | Route | Bitstream |
|------------|------|--------|---------------|-------|-------|-----------|
| `zcu106` | xczu7ev-ffvc1156-2-e | Zynq UltraScale+ | open | open (DREAMPlaceFPGA) | open (RWRoute) | Vivado `write_bitstream` only; `PROFILE=vivado_ps` gives `.bit` + `.hwh` + `.xsa` |
| `zcu104` | xczu7ev-ffvc1156-2-e | Zynq UltraScale+ | open | open | open | Vivado only |
| `kv260`  | xck26-sfvc784-2LV-c | Zynq UltraScale+ | open | open | open | Vivado only |
| `xc7z020` | xc7z020clg400-1 (PYNQ-Z1 pins in `examples/blinky`) | Zynq-7000 PL | open | open (nextpnr-xilinx) | open (nextpnr-xilinx) | **open** (prjxray) |

Notes
- UltraScale+ boards: the open path implements the PL logic **out of context** (no I/O buffers, no PS). A final bitstream needs
  the board's block design (PS8, DDR, AXI) and Vivado for `write_bitstream`; no open UltraScale+ bitstream writer exists
  (`prjuray` is registered but reports why it cannot be used yet).
- Synthesis restrictions for the DREAMPlaceFPGA path (applied automatically by `legalize: dreamplace`): no carry chains
  (`carry: none`), no wide LUT muxes, no LUTRAM/SRL, sync-reset flip-flops only (FDRE), RAMB36E2/DSP48E2 as hard blocks.
- Other UltraScale+ and UltraScale parts work by adding a board file; DREAMPlaceFPGA's Interchange support targets most of them.
- Other xc7 parts (Artix-7, Kintex-7, Spartan-7, other Zynq-7000) need the matching chip database for nextpnr-xilinx
  (`utils/build_xc7.sh` builds `xc7z020` as the example) and a board file.
- Not supported: Versal, Lattice, Gowin, Intel (other Yosys/nextpnr families can be added as new boards + blocks).

## Add a board
```yaml
# targets/<name>.yml
part: <vivado part name>
family: xczu | xcvu | xcku | xc7          # selects the open P&R/bitstream blocks that `supports()` accepts
yosys_family: xcup | xcu | xc7             # synth_xilinx -family
carry: none                                # UltraScale+ with DREAMPlaceFPGA
legalize: dreamplace                       # UltraScale+ with DREAMPlaceFPGA
chipdb: install/share/<part>.bin           # xc7 only
db_root: third_party/prjxray-db/<series>   # xc7 only
flow: {netlist: none, place: in_route, route: nextpnr_xilinx, bitgen: prjxray}   # xc7 only
```
Copy the closest existing board file, run `make doctor TARGET=<name>`, then the smoke test from [adding-blocks](adding-blocks.md).
