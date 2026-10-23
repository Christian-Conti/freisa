#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Builds the prjxray bitstream tools (fasm2frames, xc7frames2bit) for the open xc7 path. Place and route of
#            xc7 is nextpnr-fpga_interchange (make install-interchange).
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
