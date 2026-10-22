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
## @param FROM First stage (sources|synth|netlist|place|route|bitgen)
FROM ?= sources
## @param TO Last stage
TO ?= bitgen
.PHONY: example outdated update uninstall install-dreamplace check-deps help install conda-env fetch install-xc7 doctor flow synth clean
## @section Help
## Show this guide
help:
	@FILE_FOR_HELP="$(firstword $(MAKEFILE_LIST))" bash "$(MAKEFILE_DIR)utils/MakeHelp"
## @section Install
## Everything: conda env (python deps + RapidWright), pinned tool clones (tools.lock)
install: conda-env fetch check-deps
## Download miniconda (if needed) and create the conda env
conda-env:
	@ENV_NAME=$(ENV_NAME) bash utils/MakeConda
## List tools whose upstream HEAD is newer than the commit pinned in tools.lock
outdated:
	@bash utils/tool_version.sh outdated
## Re-pin one tool in tools.lock to upstream HEAD (or REF)
update:
	@bash utils/tool_version.sh update $(TOOL) $(REF)
## Check build dependencies (git, cmake, g++, boost, eigen, python deps); runs before every build
check-deps:
	@$(CONDA_RUN) bash utils/check_deps.sh || true
## Clone every tool in tools.lock at its pinned commit into third_party/
fetch:
	@bash utils/fetch_tools.sh
## Build nextpnr-xilinx + prjxray (open xc7 bitstream path; long build, needs cmake/boost/eigen)
install-xc7: fetch
	@$(CONDA_RUN) bash utils/check_deps.sh && bash utils/build_xc7.sh
## Build DREAMPlaceFPGA (CPU or CUDA, per available torch) for the open UltraScale+ placer
install-dreamplace: fetch
	@$(CONDA_RUN) bash utils/check_deps.sh && bash utils/build_dreamplace.sh
## @param TOOL Tool name in tools.lock (for `update`)
TOOL ?=
## @param REF Branch/tag/commit to pin (for `update`, default upstream HEAD)
REF ?=
## @param EXAMPLE Design for `make example` (blinky_xc7|lfsr_bank|counter|alu|uart_tx|vhdl_blink|example)
EXAMPLE ?= blinky_xc7
## @param EXAMPLE_TARGET Board for `make example`
EXAMPLE_TARGET ?= xc7z020
## @param EXAMPLE_TO Last stage for `make example` (default: bitgen on xc7z020, route otherwise)
EXAMPLE_TO ?=
## @section Flow
## Show which backend of each stage can run for TARGET
doctor:
	@$(CONDA_RUN) python flow.py doctor -d $(DESIGN) -t $(TARGET) $(if $(PROFILE),-p $(PROFILE))
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
