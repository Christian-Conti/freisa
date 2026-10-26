#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Checks system packages needed to build the open tools.
# Module   : check_deps.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

err() {
  echo -e "\033[1;31m[ERROR]\033[0m $*" >&2
}

miss=()

for t in git cmake make g++ python3 pkg-config; do command -v $t >/dev/null || miss+=("$t"); done
[[ -f /usr/include/boost/version.hpp || -f ${CONDA_PREFIX:-/nonexistent}/include/boost/version.hpp ]] || miss+=("libboost-all-dev")
[[ -d /usr/include/eigen3 || -d ${CONDA_PREFIX:-/nonexistent}/include/eigen3 ]] || miss+=("libeigen3-dev")

python3 -c 'import yaml' 2>/dev/null || miss+=("pyyaml (python freisa.py install conda)")


if ((${#miss[@]})); then err "missing: ${miss[*]}"; echo "  apt: sudo apt install build-essential cmake pkg-config libboost-all-dev libeigen3-dev python3-dev"; exit 1; fi
info "build dependencies ok"
