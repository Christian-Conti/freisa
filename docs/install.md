# Install

`make install` creates the `freisa` conda env (Miniconda is downloaded if missing; `utils/MakeConda`, python deps in
`utils/python-requirements.txt`, including RapidWright), clones every tool in `tools.lock` at its pinned commit into
`third_party/`, and checks build dependencies (`utils/check_deps.sh`).

`make install-xc7` re-checks dependencies first and stops with the apt line to run if something is missing, then builds
nextpnr-xilinx and the prjxray tools into `install/bin` (the Makefile puts it on PATH). Set `db_root`/`chipdb` in the
xc7 board file afterwards.

Host tools expected: Yosys with the `slang` and `ghdl` plugins (OSS CAD Suite), Java (RapidWright), and Vivado for UltraScale+ boards.
Update a pinned tool by editing its commit in `tools.lock` and running `make fetch`.
