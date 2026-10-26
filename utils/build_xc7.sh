#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Builds the prjxray bitstream tools (fasm2frames, xc7frames2bit) and nextpnr-xilinx (prjxray-db chip database)
#            for the open xc7 path. The other xc7 place and route,
#            nextpnr-fpga_interchange, comes from python freisa.py install interchange.
# Module   : build_xc7.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set -euo pipefail

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

export XRAY_DIR="${XRAY_DIR:-$(cd "$(dirname "$0")/.." && pwd)/third_party/prjxray}" DB_DIR="${DB_DIR:-$(cd "$(dirname "$0")/.." && pwd)/third_party/prjxray-db}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PREFIX="$ROOT/install"; mkdir -p "$PREFIX/bin"

J="${JOBS:-$(nproc)}"

# prjxray: xc7frames2bit (C++) + python fasm2frames
cmake -S "$ROOT/third_party/prjxray" -B "$ROOT/third_party/_build/prjxray" -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_CXX_FLAGS="-include cstdint -fpermissive -Wno-error" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
make -C "$ROOT/third_party/_build/prjxray" -j"$J" xc7frames2bit
install "$ROOT/third_party/_build/prjxray/tools/xc7frames2bit" "$PREFIX/bin/"

(cd "$ROOT/third_party/prjxray" && pip install -r requirements.txt >/dev/null)
printf '#!/bin/sh
PYTHONPATH="%s:%s:$PYTHONPATH" exec python3 %s/utils/fasm2frames.py "$@"
' "$ROOT/third_party/prjxray" "$ROOT/third_party/prjxray/third_party/fasm" "$ROOT/third_party/prjxray" > "$PREFIX/bin/fasm2frames"; chmod +x "$PREFIX/bin/fasm2frames"

info "prjxray tools in $PREFIX/bin"

# nextpnr-xilinx: xc7 place and route whose chip database comes from prjxray-db (open). One database per xc7 board part.
cmake -S "$ROOT/third_party/nextpnr-xilinx" -B "$ROOT/third_party/_build/nextpnr-xilinx" -DBOOST_ROOT="${CONDA_PREFIX:-/usr}" -DBoost_NO_SYSTEM_PATHS=ON -DARCH=xilinx -DBUILD_GUI=OFF -DBUILD_PYTHON=OFF -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_CXX_FLAGS="-include cstdint -fpermissive -Wno-error" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
make -C "$ROOT/third_party/_build/nextpnr-xilinx" -j"$J" nextpnr-xilinx bbasm
install "$ROOT/third_party/_build/nextpnr-xilinx/nextpnr-xilinx" "$PREFIX/bin/"
install "$ROOT/third_party/_build/nextpnr-xilinx/bba/bbasm" "$PREFIX/bin/bbasm-xilinx"   # its own bbasm: not the Interchange one
mkdir -p "$PREFIX/share/nextpnr-xilinx"
export PYTHONPATH="$ROOT/third_party/nextpnr-xilinx/xilinx/python:$ROOT/third_party/prjxray:$ROOT/third_party/prjxray/third_party/fasm:${PYTHONPATH:-}"
for part in $(grep -l "family: xc7" "$ROOT"/targets/*.yml | xargs -n1 awk '/^part:/{print $2}'); do
  [ -f "$PREFIX/share/nextpnr-xilinx/$part.bin" ] && continue
  python3 "$ROOT/third_party/nextpnr-xilinx/xilinx/python/bbaexport.py" --device "$part" --bba "$PREFIX/share/nextpnr-xilinx/$part.bba"
  "$PREFIX/bin/bbasm-xilinx" --l "$PREFIX/share/nextpnr-xilinx/$part.bba" "$PREFIX/share/nextpnr-xilinx/$part.bin"
  rm -f "$PREFIX/share/nextpnr-xilinx/$part.bba"
done
info "nextpnr-xilinx and its chip databases in $PREFIX/share/nextpnr-xilinx"
