# Supported platforms

`make doctor TARGET=<board>` is the source of truth on your machine; this table lists what each chip supports.
Board files live in `targets/` (one per chip/board family); board-store files are pulled by `make install-boards`.

| Chip | FPGA boards using it | Synthesis | Netlist | Placement | Routing | Bitstream | Upload |
|------|----------------------|-----------|---------|-----------|---------|-----------|--------|
| xczu7ev (Zynq UltraScale+ MPSoC) | ZCU104 (`zcu104`), ZCU106 (`zcu106`) | Yosys (slang, ghdl), Vivado | RapidWright (EDIF → DCP), Vivado link | DREAMPlaceFPGA, Vivado | RWRoute, Vivado | Vivado (`vivado`; `vivado_ps` = PS block design, also `.hwh` + `.xsa`) | openFPGALoader, Vivado HW manager |
| xck26 (Kria K26 SOM, Zynq UltraScale+) | Kria KV260 starter kit (`kv260`) | Yosys (slang, ghdl), Vivado | RapidWright, Vivado link | DREAMPlaceFPGA, Vivado | RWRoute, Vivado | Vivado (`vivado`, `vivado_ps`) | openFPGALoader, Vivado HW manager |
| xc7z020 (Zynq-7000) | PYNQ-Z2 and PYNQ-Z1 (`xc7z020`) | Yosys (slang, ghdl), Vivado | — (nextpnr reads the Yosys JSON), Vivado link | nextpnr-xilinx, Vivado | nextpnr-xilinx, Vivado | prjxray (open), Vivado | openFPGALoader, Vivado HW manager |

Reading the table
- Tools listed in one cell are interchangeable blocks of that step; pick with `stages:`/`flow:`/`PROFILE=`, compare with
  `explore:` or `EXPLORE=all`. The first tool of each cell is the default of the `open` profile.
- A fully open RTL → bitstream path exists only for the Zynq-7000 (xc7) row. For the UltraScale+ rows the open tools implement
  the PL logic out of context (no I/O buffers, no PS); the bitstream (and the PS design, `.hwh`) comes from Vivado.
- `prjuray` (Project U-Ray) is registered as an open UltraScale+ bitstream candidate but reports why it cannot be used yet.
- f4pga: its flow targets 7-series parts with architecture definitions (Artix-7 35T/100T, Zynq xc7z010) and it programs
  boards through openFPGALoader, which FREISA already uses for `make upload`; it is not integrated as a flow because the
  xc7z020 and UltraScale+ parts are outside its device list.
- DREAMPlaceFPGA restrictions (applied automatically by `legalize: dreamplace`): no carry chains, no wide LUT muxes, no
  LUTRAM/SRL, FDRE flip-flops, RAMB36E2 and DSP48E2 as hard blocks. Use the Vivado steps when the design needs URAM or others.
- Evaluated but not integrated: OpenPARF and AMF-Placer (contest architectures only / need Vivado Tcl), the FPL'26 contest agent (Vivado-driven).
- Not supported: Versal, Lattice, Gowin, Intel (add a board file and blocks to extend).

## Add a board
```yaml
# targets/<name>.yml
part: <vivado part name>
family: xczu | xcvu | xcku | xc7           # selects the blocks whose supports() accept it
yosys_family: xcup | xcu | xc7             # synth_xilinx -family
board_store: Xilinx/zcu106                 # XilinxBoardStore path(s); `make install-boards` pulls them (and adds them to boards.lock)
ofl_board: zcu106                          # openFPGALoader board name (`openFPGALoader --list-boards`) for `make upload`
hw_device: "xczu7*"                        # Vivado hardware-manager device pattern (default derived from the part)
needs_ps: true                             # Zynq PS present: PL-only Vivado bitgen is refused, use vivado_ps
carry: none                                # UltraScale+ with DREAMPlaceFPGA
legalize: dreamplace                       # UltraScale+ with DREAMPlaceFPGA
chipdb: install/share/<part>.bin           # xc7 only
db_root: third_party/prjxray-db/<series>   # xc7 only
flow: {netlist: none, place: in_route, route: nextpnr_xilinx, bitgen: prjxray}   # xc7 only
```
Copy the closest existing board file, run `make doctor TARGET=<name>`, then `make install-boards` and a smoke test from [adding-blocks](adding-blocks.md).

## Board files
`boards.lock` pins the XilinxBoardStore commit and one version per supported board; the boards are exactly those named by
`board_store:` in `targets/*.yml`. `make install-boards` moves the lock to the newest store state and fetches only those
boards into `boards/<target>/` (with a generated `pins.xdc` from `part0_pins.xml`); `make install-boards PIN=1` reproduces
the committed lock.
