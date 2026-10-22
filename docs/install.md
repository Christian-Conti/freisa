# Install

`make install` does, in order:
1. `conda-env`: creates the `freisa` conda env (Miniconda is downloaded if missing; `utils/MakeConda`; Python deps in
   `utils/python-requirements.txt`, including RapidWright, which bundles its jar).
2. `check-deps`: verifies the build dependencies (git, cmake, g++, boost, eigen, python dev) and prints the apt line if something is missing.
3. `install-boards`: pulls the supported boards from XilinxBoardStore ([platforms](platforms.md#board-files)).
4. `install-xc7`: builds nextpnr-xilinx + prjxray tools and the xc7z020 chip database (open Zynq-7000 bitstream path).
5. `install-dreamplace`: builds DREAMPlaceFPGA (CPU, or CUDA when a CUDA torch is installed) for the open UltraScale+ placer.
Tools are cloned from `tools.lock` at the pinned commit into `third_party/`, only the ones a target needs; steps 4 and 5 are
skipped when already built (`FORCE=1` rebuilds). `make uninstall` removes `third_party/`, `install/`, `build/` and the env.

Host tools: Yosys with the `slang` and `ghdl` plugins (OSS CAD Suite, also provides openFPGALoader), Java (RapidWright).
Vivado is optional and found automatically: `$VIVADO`, then `PATH`, then `/eda/Xilinx/Vivado/<version>/bin/vivado`
(`VIVADO_ROOT` changes the base directory, `VIVADO_VERSION` the version; default 2024.1, else the newest).

Update a pinned tool with `make outdated`, `make update NAME=<tool>`, `make fetch TOOLS=<tool>` and a rebuild with `FORCE=1`.
