# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Top-level build, install and run targets for the FREISA flow.
# Module   : Makefile
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

SHELL := /bin/bash
MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ENV_NAME ?= freisa
# conda is activated per recipe so no `conda activate` is needed in the user's shell
CONDA_RUN = source $$(conda info --base 2>/dev/null || echo $$HOME/miniconda3)/etc/profile.d/conda.sh && conda activate $(ENV_NAME) &&
export PATH := $(MAKEFILE_DIR)install/bin:$(PATH)

DESIGN_DIR = "designs/"
## @section Config
## @param DESIGN Design file name in designs/ (or a .yml path)
DESIGN ?= blinky
## @param TARGET Board file name in targets/
TARGET ?= xc7z020
## @param PROFILE Stage preset: open (default) | vivado | vivado_ps (PS boards: also .hwh/.xsa) | yosys_vivado
PROFILE ?=
## @param EXPLORE `all` = try every supported backend per stage, keep the best (scores compared per metric)
EXPLORE ?=
## @param FROM First stage (sources|synth|netlist|place|route|bitgen)
FROM ?= sources
## @param TO Last stage
TO ?= bitgen
.PHONY: install-boards upload example outdated update uninstall install-dreamplace check-deps help install conda-env fetch install-xc7 doctor flow synth clean
## @section Help
## Show this guide
help:
	@FILE_FOR_HELP="$(firstword $(MAKEFILE_LIST))" bash "$(MAKEFILE_DIR)utils/MakeHelp"
## @section Install
## Everything: conda env (python deps + RapidWright), board files, pinned tools built from source (xc7 tools, DREAMPlaceFPGA); skips what is already built
install: conda-env check-deps install-boards install-xc7 install-dreamplace
## Download miniconda (if needed) and create the conda env
conda-env:
	@ENV_NAME=$(ENV_NAME) bash utils/MakeConda
## List tools whose upstream HEAD is newer than the commit pinned in tools.lock
outdated:
	@bash utils/tool_version.sh outdated
## Re-pin one tool in tools.lock to upstream HEAD (or REF)
update:
	@bash utils/tool_version.sh update $(NAME) $(REF)
## Pull board files (+ generated pins.xdc) for the boards in targets/*.yml from XilinxBoardStore and refresh boards.lock; PIN=1 keeps the lock as is
install-boards:
	@$(CONDA_RUN) python utils/boards.py install $(if $(PIN),--pin)
## Check build dependencies (git, cmake, g++, boost, eigen, python deps); runs before every build
check-deps:
	@$(CONDA_RUN) bash utils/check_deps.sh || true
## Clone the tools in tools.lock at their pinned commit into third_party/ (TOOLS="a b" for a subset; present ones are skipped)
fetch:
	@bash utils/fetch_tools.sh $(TOOLS)
## Build nextpnr-xilinx + prjxray (open xc7 bitstream path; long build, needs cmake/boost/eigen)
install-xc7:
	@if [ -x install/bin/nextpnr-xilinx ] && [ -z "$(FORCE)" ]; then echo "[INFO] xc7 tools present (FORCE=1 to rebuild)"; else \
	bash utils/fetch_tools.sh nextpnr-xilinx prjxray prjxray-db && $(CONDA_RUN) bash utils/check_deps.sh && $(CONDA_RUN) bash utils/build_xc7.sh; fi
## Build DREAMPlaceFPGA (CPU or CUDA, per available torch) for the open UltraScale+ placer
install-dreamplace:
	@if [ -d third_party/dreamplacefpga/install/dreamplacefpga ] && [ -z "$(FORCE)" ]; then echo "[INFO] DREAMPlaceFPGA present (FORCE=1 to rebuild)"; else \
	bash utils/fetch_tools.sh dreamplacefpga && $(CONDA_RUN) bash utils/check_deps.sh && $(CONDA_RUN) bash utils/build_dreamplace.sh; fi
## @param TOOL Upload tool for `make upload`: openfpgaloader | vivado
TOOL ?=
## @param BIT Bitstream file for `make upload` (default build/<DESIGN>/<TARGET>/out.bit)
BIT ?=
## @param FORCE `1` = rebuild tools that are already built (install-xc7, install-dreamplace)
FORCE ?=
## @param PIN `1` = keep boards.lock / do not move pins (for `install-boards`)
PIN ?=
## @param NAME Tool name in tools.lock (for `update`)
NAME ?=
## @param TOOLS Subset of tools.lock names (for `fetch`)
TOOLS ?=
## @param REF Branch/tag/commit to pin (for `update`, default upstream HEAD)
REF ?=
## @section Flow
## Program the bitstream on the connected board: TOOL=openfpgaloader (open, default) | vivado; BIT=<file> to override
upload:
	@$(CONDA_RUN) python flow.py upload -d $(DESIGN) -t $(TARGET) --tool $(or $(TOOL),openfpgaloader) $(if $(BIT),--bit $(BIT))
## Show which backend of each stage can run for TARGET
doctor:
	@$(CONDA_RUN) python flow.py doctor -d $(DESIGN) -t $(TARGET) $(if $(PROFILE),-p $(PROFILE)) $(if $(EXPLORE),--explore $(EXPLORE))
## Run the flow for DESIGN on TARGET (FROM..TO stages)
flow:
	@$(CONDA_RUN) python flow.py run -d $(DESIGN_DIR)$(DESIGN) -t $(TARGET) --from $(FROM) --to $(TO) $(if $(PROFILE),-p $(PROFILE)) $(if $(EXPLORE),--explore $(EXPLORE))
## Run the bundled blinky example on any supported board: make example TARGET=zcu104 (xc7z020: RTL -> .bit fully open; UltraScale+ boards: up to the routed checkpoint, no Vivado needed)
example:
	@$(MAKE) --no-print-directory flow DESIGN=$(DESIGN) TARGET=$(TARGET) FROM=sources TO=$(or $(TO),$(if $(filter xc7z020,$(TARGET)),bitgen,route))
## Open synthesis only (yosys)
synth:
	@$(MAKE) flow TO=synth
## Remove everything install created: third_party/, install/, build/ and the conda env (Miniconda itself is kept)
uninstall:
	rm -rf third_party install build
	-@source $$(conda info --base 2>/dev/null || echo $$HOME/miniconda3)/etc/profile.d/conda.sh && conda env remove -y -n $(ENV_NAME)
## Remove build outputs
clean:
	rm -rf build
