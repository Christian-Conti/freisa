#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Builds the FPGA Interchange tools: nextpnr-fpga_interchange (+ bbasm), python-fpga-interchange, and the
#            chip databases (.device from RapidWright, patched; nextpnr .bin) of the xc7 boards in targets/.
# Module   : build_interchange.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set -euo pipefail

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PREFIX="$ROOT/install"; TP="$ROOT/third_party"; J="${JOBS:-$(nproc)}"

mkdir -p "$PREFIX/bin" "$PREFIX/share/interchange"

export PKG_CONFIG_PATH="${CONDA_PREFIX:-/usr}/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

SCHEMA="$TP/fpga-interchange-schema/interchange"; PYIF="$TP/python-fpga-interchange"

# python-fpga-interchange (device patches, nextpnr database emitter, Yosys JSON -> .netlist, FASM generator) needs
# pycapnp 1.1.0 (the main env has 2.x for DREAMPlaceFPGA): it lives in its own conda env "freisa-if"
IFENV="${FREISA_IF_ENV:-freisa-if}"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda env list | awk '{print $1}' | grep -qx "$IFENV" || conda create -y -q -n "$IFENV" -c conda-forge python=3.9 swig >/dev/null
conda activate "$IFENV"

pip install -q "cython<3" wheel setuptools pyyaml python-sat psutil
pip install -q --no-build-isolation pycapnp==1.1.0
pip install -q "git+https://github.com/litghost/rapidyaml.git@fixup_python_packaging#egg=rapidyaml"
pip install -q --no-deps -e "$PYIF"

# the schemas import /capnp/java.capnp (capnproto-java): pycapnp resolves imports along sys.path
cp "$TP/fpga-interchange-schema/../dreamplacefpga/IFsupport/capnp/java.capnp" "$(python -c 'import capnp, os; print(os.path.dirname(capnp.__file__))')/java.capnp" 2>/dev/null \
  || curl -fsSL https://raw.githubusercontent.com/capnproto/capnproto-java/master/compiler/src/main/schema/capnp/java.capnp \
     -o "$(python -c 'import capnp, os; print(os.path.dirname(capnp.__file__))')/java.capnp"

conda deactivate

# nextpnr with the fpga_interchange architecture (pinned to the last upstream commit that has it)
cmake -S "$TP/nextpnr-fpga-interchange" -B "$TP/_build/nextpnr-fpga-interchange" -DARCH=fpga_interchange -DBUILD_GUI=OFF \
      -DBUILD_PYTHON=OFF -DINTERCHANGE_SCHEMA_PATH="$SCHEMA" -DPYTHON_INTERCHANGE_PATH="$PYIF" -DRAPIDWRIGHT_PATH="$TP/rapidwright-unused" \
      -DBOOST_ROOT="${CONDA_PREFIX:-/usr}" -DBoost_NO_SYSTEM_PATHS=ON -DCMAKE_CXX_FLAGS="-include cstdint -fpermissive -Wno-error" \
      -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null

make -C "$TP/_build/nextpnr-fpga-interchange" -j"$J" nextpnr-fpga_interchange bbasm
install "$TP/_build/nextpnr-fpga-interchange/nextpnr-fpga_interchange" "$TP/_build/nextpnr-fpga-interchange/bba/bbasm" "$PREFIX/bin/"
      
info "nextpnr-fpga_interchange in $PREFIX/bin; device databases are built on first use in install/share/interchange"
