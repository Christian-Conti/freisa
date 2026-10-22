# FREISA - FPGA Reusable and Extensible Infrastructure for Synthesis Automation: open-source RTL -> bitstream flow. Modular: designs/*.yml (any RTL), targets/*.yml (any board), freisa/stages/*.py (any tool).
SHELL := /bin/bash
MAKEFILE_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ENV_NAME ?= freisa
# conda is activated per recipe so no `conda activate` is needed in the user's shell
CONDA_RUN = source $$(conda info --base 2>/dev/null || echo $$HOME/miniconda3)/etc/profile.d/conda.sh && conda activate $(ENV_NAME) &&
export PATH := $(MAKEFILE_DIR)install/bin:$(PATH)
## @section Config
## @param DESIGN Design file name in designs/ (or a .yml path)
DESIGN ?= amaretto
## @param TARGET Board file name in targets/
TARGET ?= zcu106
## @param PROFILE Stage preset: open (default) | vivado | vivado_ps (PS boards: also .hwh/.xsa) | yosys_vivado
PROFILE ?=
## @param EXPLORE `all` = try every supported backend per stage, keep the best (scores compared per metric)
EXPLORE ?=
## @param FROM First stage (sources|synth|netlist|place|route|bitgen)
FROM ?= sources
## @param TO Last stage
TO ?= bitgen
.PHONY: upload example outdated update uninstall install-dreamplace check-deps help install conda-env fetch install-xc7 doctor flow synth clean
## @section Help
## Show this guide
help:
	@FILE_FOR_HELP="$(firstword $(MAKEFILE_LIST))" bash "$(MAKEFILE_DIR)utils/MakeHelp"
## @section Install
## Everything: conda env (python deps + RapidWright), pinned tool clones (tools.lock)
install: conda-env check-deps
## Download miniconda (if needed) and create the conda env
conda-env:
	@ENV_NAME=$(ENV_NAME) bash utils/MakeConda
## List tools whose upstream HEAD is newer than the commit pinned in tools.lock
outdated:
	@bash utils/tool_version.sh outdated
## Re-pin one tool in tools.lock to upstream HEAD (or REF)
update:
	@bash utils/tool_version.sh update $(NAME) $(REF)
## Check build dependencies (git, cmake, g++, boost, eigen, python deps); runs before every build
check-deps:
	@$(CONDA_RUN) bash utils/check_deps.sh || true
## Clone the tools in tools.lock at their pinned commit into third_party/ (TOOLS="a b" for a subset; present ones are skipped)
fetch:
	@bash utils/fetch_tools.sh $(TOOLS)
## Build nextpnr-xilinx + prjxray (open xc7 bitstream path; long build, needs cmake/boost/eigen)
install-xc7:
	@bash utils/fetch_tools.sh nextpnr-xilinx prjxray prjxray-db
	@$(CONDA_RUN) bash utils/check_deps.sh && bash utils/build_xc7.sh
## Build DREAMPlaceFPGA (CPU or CUDA, per available torch) for the open UltraScale+ placer
install-dreamplace:
	@bash utils/fetch_tools.sh dreamplacefpga
	@$(CONDA_RUN) bash utils/check_deps.sh && bash utils/build_dreamplace.sh
## @param TOOL Upload tool for `make upload`: openfpgaloader | vivado
TOOL ?=
## @param BIT Bitstream file for `make upload` (default build/<DESIGN>/<TARGET>/out.bit)
BIT ?=
## @param NAME Tool name in tools.lock (for `update`)
NAME ?=
## @param TOOLS Subset of tools.lock names (for `fetch`)
TOOLS ?=
## @param REF Branch/tag/commit to pin (for `update`, default upstream HEAD)
REF ?=
## @param EXAMPLE Design for `make example` (blinky_xc7|lfsr_bank|counter|alu|uart_tx|vhdl_blink|example)
EXAMPLE ?= blinky_xc7
## @param EXAMPLE_TARGET Board for `make example`
EXAMPLE_TARGET ?= xc7z020
## @param EXAMPLE_TO Last stage for `make example` (default: bitgen on xc7z020, route otherwise)
EXAMPLE_TO ?=
## @section Flow
## Program the bitstream on the connected board: TOOL=openfpgaloader (open, default) | vivado; BIT=<file> to override
upload:
	@$(CONDA_RUN) python flow.py upload -d $(DESIGN) -t $(TARGET) --tool $(or $(TOOL),openfpgaloader) $(if $(BIT),--bit $(BIT))
## Show which backend of each stage can run for TARGET
doctor:
	@$(CONDA_RUN) python flow.py doctor -d $(DESIGN) -t $(TARGET) $(if $(PROFILE),-p $(PROFILE)) $(if $(EXPLORE),--explore $(EXPLORE))
## Run the flow for DESIGN on TARGET (FROM..TO stages)
flow:
	@$(CONDA_RUN) python flow.py run -d $(DESIGN) -t $(TARGET) --from $(FROM) --to $(TO) $(if $(PROFILE),-p $(PROFILE))
## Run the flow on a small bundled example (default: blinky on xc7z020, fully open RTL -> .bit). Other: EXAMPLE=lfsr_bank EXAMPLE_TARGET=zcu106 TO=route
example:
	@$(MAKE) --no-print-directory flow DESIGN=$(EXAMPLE) TARGET=$(EXAMPLE_TARGET) FROM=sources TO=$(or $(EXAMPLE_TO),$(if $(filter xc7z020,$(EXAMPLE_TARGET)),bitgen,route))
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
