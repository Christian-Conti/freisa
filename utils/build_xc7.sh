#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Builds nextpnr-xilinx and the prjxray tools.
# Module   : build_xc7.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set -euo pipefail
export XRAY_DIR="${XRAY_DIR:-$(cd "$(dirname "$0")/.." && pwd)/third_party/prjxray}" DB_DIR="${DB_DIR:-$(cd "$(dirname "$0")/.." && pwd)/third_party/prjxray-db}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PREFIX="$ROOT/install"; mkdir -p "$PREFIX/bin"
J="${JOBS:-$(nproc)}"
# prjxray: xc7frames2bit (C++) + python fasm2frames
cmake -S "$ROOT/third_party/prjxray" -B "$ROOT/build/prjxray" -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_CXX_FLAGS="-include cstdint -fpermissive -Wno-error" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
make -C "$ROOT/build/prjxray" -j"$J" xc7frames2bit
install "$ROOT/build/prjxray/tools/xc7frames2bit" "$PREFIX/bin/"
(cd "$ROOT/third_party/prjxray" && pip install -r requirements.txt >/dev/null)
printf '#!/bin/sh
PYTHONPATH="%s:%s:$PYTHONPATH" exec python3 %s/utils/fasm2frames.py "$@"
' "$ROOT/third_party/prjxray" "$ROOT/third_party/prjxray/third_party/fasm" "$ROOT/third_party/prjxray" > "$PREFIX/bin/fasm2frames"; chmod +x "$PREFIX/bin/fasm2frames"
# nextpnr-xilinx + chipdb for the xc7z020 (Zynq-7000 PL)
cmake -S "$ROOT/third_party/nextpnr-xilinx" -B "$ROOT/build/nextpnr-xilinx" -DBOOST_ROOT="${CONDA_PREFIX:-/usr}" -DBoost_NO_SYSTEM_PATHS=ON -DARCH=xilinx -DBUILD_GUI=OFF -DBUILD_PYTHON=OFF -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_CXX_FLAGS="-include cstdint -fpermissive -Wno-error" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
make -C "$ROOT/build/nextpnr-xilinx" -j"$J" nextpnr-xilinx bbasm
install "$ROOT/build/nextpnr-xilinx/nextpnr-xilinx" "$ROOT/build/nextpnr-xilinx/bba/bbasm" "$PREFIX/bin/"
mkdir -p "$PREFIX/share"
DB="$ROOT/third_party/prjxray-db/zynq7"
# chipdb needs prjxray python + database on the path
export PYTHONPATH="$ROOT/third_party/nextpnr-xilinx/xilinx/python:$ROOT/third_party/prjxray:$ROOT/third_party/prjxray/third_party/fasm:${PYTHONPATH:-}"
python3 "$ROOT/third_party/nextpnr-xilinx/xilinx/python/bbaexport.py" --device xc7z020clg400-1 --bba "$PREFIX/share/xc7z020.bba"
"$PREFIX/bin/bbasm" --l "$PREFIX/share/xc7z020.bba" "$PREFIX/share/xc7z020.bin"
echo "[INFO] xc7 tools in $PREFIX/bin (add to PATH, set db_root=$DB in targets/xc7z020.yml)"
