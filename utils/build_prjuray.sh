#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Builds Project U-Ray's bitstream tools: xcframes2bit (prjuray-tools, C++) and the prjuray Python package,
#            and installs a `prjuray-fasm2bit` wrapper (FASM -> UltraScale+ bitstream with the prjuray-db database).
# Module   : build_prjuray.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; PREFIX="$ROOT/install"; TP="$ROOT/third_party"; J="${JOBS:-$(nproc)}"
U="$TP/prjuray"; T="$U/third_party/prjuray-tools"
mkdir -p "$PREFIX/bin"
cmake -S "$T" -B "$TP/_build/prjuray-tools" -DCMAKE_CXX_FLAGS="-include cstdint -fpermissive -Wno-error" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 >/dev/null
make -C "$TP/_build/prjuray-tools" -j"$J" xcframes2bit
install "$(find "$TP/_build/prjuray-tools" -name xcframes2bit -type f -perm -u+x | head -1)" "$PREFIX/bin/"
pip install -q intervaltree pyjson5 parse progressbar2 numpy
pip install -q --no-deps -e "$T" -e "$U/third_party/fasm"
printf '#!/bin/sh\n# FASM -> bitstream with Project U-Ray (database: prjuray-db)\ncd "%s" && PYTHONPATH="%s:$PYTHONPATH" exec python3 utils/fasm2bit.py --xcframes2bit "%s/bin/xcframes2bit" "$@"\n' \
  "$U" "$U" "$PREFIX" > "$PREFIX/bin/prjuray-fasm2bit"
chmod +x "$PREFIX/bin/prjuray-fasm2bit"
echo "[INFO] prjuray tools in $PREFIX/bin (xcframes2bit, prjuray-fasm2bit)"
