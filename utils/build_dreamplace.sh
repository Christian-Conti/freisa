#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Builds DREAMPlaceFPGA.
# Module   : build_dreamplace.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set -euo pipefail

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

ROOT="$(cd "$(dirname "$0")/.." && pwd)"; D="$ROOT/third_party/dreamplacefpga"

python -c 'import torch; assert torch.__version__.startswith("2.0")' 2>/dev/null || pip install "torch==2.0.1" "numpy<2" --index-url https://download.pytorch.org/whl/cpu
pip install -r "$D/requirements.txt" >/dev/null || true

export PKG_CONFIG_PATH="$CONDA_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

cmake -S "$D" -B "$D/build" -DCMAKE_INSTALL_PREFIX="$D/install" -DCMAKE_CXX_FLAGS="-fpermissive -Wno-template-body -Wno-error" -DCMAKE_C_FLAGS="-Wno-error=incompatible-pointer-types -Wno-incompatible-pointer-types -fpermissive" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DPython_EXECUTABLE="$(command -v python)" >/dev/null
make -C "$D/build" -j"${JOBS:-$(nproc)}" install

info "DREAMPlaceFPGA installed in $D/install"

# upstream CMake skips some pure-python ops (timing, utility, rmst_wl) that BasicPlace imports
for o in "$D"/dreamplacefpga/ops/*/; do n=$(basename "$o"); [[ -d $D/install/dreamplacefpga/ops/$n ]] || cp -r "$o" "$D/install/dreamplacefpga/ops/$n"; done

# torch>=2.0 zero_grad() sets grads to None, which the vendored Nesterov optimizer then skips
sed -i 's/\.zero_grad()/.zero_grad(set_to_none=False)/g' "$D"/install/dreamplacefpga/*.py
ln -sfn ../thirdparty "$D/install/thirdparty"  # placer loads capnp schemas relative to its install dir
