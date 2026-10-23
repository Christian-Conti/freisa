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



## @param FROM First stage (sources|synth|netlist|place|route|bitgen)
FROM ?= sources

## @param TO Last stage
TO ?= bitgen

## @param TOOL Upload tool for `make upload`: openfpgaloader | vivado
TOOL ?=

## @param BIT Bitstream file for `make upload` (default build/<DESIGN>/<TARGET>/out.bit)
BIT ?=

## @param FORCE `1` = rebuild tools that are already built (install-xc7, install-dreamplace)
FORCE ?=

## @param PIN `1` = keep boards.lock / do not move pins (for `install-boards`)
PIN ?=

## @param JTAG USB serial of the JTAG cable to program (`make upload`), when several boards are connected
JTAG ?=
## @param PORT Serial port for `make uart-test` (default: found from the board's JTAG cable)
PORT ?=
## @param BAUD Baud rate for `make uart-test` (default 115200)
BAUD ?=
## @param NAME Tool name in tools.lock (for `update`)
NAME ?=

## @param TOOLS Subset of tools.lock names (for `fetch`)
TOOLS ?=

## @param REF Branch/tag/commit to pin (for `update`, default upstream HEAD)
REF ?=

.PHONY: install-prjuray install-interchange uart-test check install-boards upload outdated update uninstall install-dreamplace check-deps help install conda-env fetch install-xc7 doctor flow synth clean

## @section Help
## Show this guide
help:
	@FILE_FOR_HELP="$(firstword $(MAKEFILE_LIST))" bash "$(MAKEFILE_DIR)utils/MakeHelp"

## @section Install
## Everything: conda env (python deps + RapidWright), board files, pinned tools built from source (xc7 tools, DREAMPlaceFPGA); skips what is already built
install: conda-env check-deps install-boards install-xc7 install-dreamplace install-interchange install-prjuray

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

## Build the prjxray bitstream tools (open xc7 bitstream)
install-xc7:
	@if [ -x install/bin/xc7frames2bit ] && [ -z "$(FORCE)" ]; then echo "[INFO] xc7 tools present (FORCE=1 to rebuild)"; else \
	bash utils/fetch_tools.sh prjxray prjxray-db && $(CONDA_RUN) bash utils/check_deps.sh && $(CONDA_RUN) bash utils/build_xc7.sh; fi

## Build the FPGA Interchange tools: nextpnr-fpga_interchange and python-fpga-interchange (conda env freisa-if)
install-interchange:
	@if [ -x install/bin/nextpnr-fpga_interchange ] && [ -z "$(FORCE)" ]; then echo "[INFO] Interchange tools present (FORCE=1 to rebuild)"; else \
	bash utils/fetch_tools.sh nextpnr-fpga-interchange python-fpga-interchange fpga-interchange-schema && $(CONDA_RUN) bash utils/check_deps.sh && $(CONDA_RUN) bash utils/build_interchange.sh; fi
## Build Project U-Ray's bitstream tools (xcframes2bit, prjuray-fasm2bit) and fetch its database prjuray-db
install-prjuray:
	@if [ -x install/bin/xcframes2bit ] && [ -z "$(FORCE)" ]; then echo "[INFO] prjuray tools present (FORCE=1 to rebuild)"; else \
	bash utils/fetch_tools.sh prjuray prjuray-db && $(CONDA_RUN) bash utils/check_deps.sh && $(CONDA_RUN) bash utils/build_prjuray.sh; fi
## Build DREAMPlaceFPGA (CPU or CUDA, per available torch) for the open UltraScale+ placer
install-dreamplace:
	@if [ -d third_party/dreamplacefpga/install/dreamplacefpga ] && [ -z "$(FORCE)" ]; then echo "[INFO] DREAMPlaceFPGA present (FORCE=1 to rebuild)"; else \
	bash utils/fetch_tools.sh dreamplacefpga && $(CONDA_RUN) bash utils/check_deps.sh && $(CONDA_RUN) bash utils/build_dreamplace.sh; fi

## @section Flow
## Program the bitstream on the connected board: TOOL=openfpgaloader (open, default) | vivado; BIT=<file> to override
upload:
	@$(CONDA_RUN) python utils/check_flow.py -d $(DESIGN) -t $(TARGET) --upload $(if $(TOOL),--tool $(TOOL))
	@$(CONDA_RUN) JTAG=$(JTAG) python flow.py upload -d $(DESIGN) -t $(TARGET) $(if $(TOOL),--tool $(TOOL)) $(if $(BIT),--bit $(BIT))

## Check that the tools chosen in the project file for TARGET are available; stops and suggests how to change the command if not
check:
	@$(CONDA_RUN) python utils/check_flow.py -d $(DESIGN) -t $(TARGET) --from $(FROM) --to $(TO)
## UART loopback test: send data on the board's PL UART and check the echo (PORT=/dev/ttyUSBx, BAUD=115200 to override)
uart-test:
	@$(CONDA_RUN) JTAG=$(JTAG) python utils/uart_test.py $(if $(filter command line environment,$(origin TARGET)),-t $(TARGET)) $(if $(PORT),--port $(PORT)) $(if $(BAUD),--baud $(BAUD))
## Show every tool of every step and whether it can run: all boards, or only TARGET when given
doctor:
	@$(CONDA_RUN) python flow.py doctor -d $(DESIGN) $(if $(filter command line environment,$(origin TARGET)),-t $(TARGET),--all-boards)

## Run the flow for DESIGN on TARGET (FROM..TO stages)
flow:
	@$(CONDA_RUN) python utils/check_flow.py -d $(DESIGN) -t $(TARGET) --from $(FROM) --to $(TO)
	@$(CONDA_RUN) python flow.py run -d $(DESIGN_DIR)$(DESIGN) -t $(TARGET) --from $(FROM) --to $(TO)

## Open synthesis only (yosys)
synth:
	@$(MAKE) flow TO=synth

## Remove everything install created: third_party/, install/, build/ and the conda env (Miniconda itself is kept)
uninstall:
	rm -rf third_party install build
	-@source $$(conda info --base 2>/dev/null || echo $$HOME/miniconda3)/etc/profile.d/conda.sh && conda env remove -y -n $(ENV_NAME); conda env remove -y -n freisa-if

## Remove build outputs
clean:
	rm -rf build
