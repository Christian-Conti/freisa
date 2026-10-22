#!/usr/bin/env bash
# Verify system packages needed to build the open xc7 tools before spending an hour compiling.
miss=()
for t in git cmake make g++ python3 pkg-config; do command -v $t >/dev/null || miss+=("$t"); done
[[ -f /usr/include/boost/version.hpp || -f ${CONDA_PREFIX:-/nonexistent}/include/boost/version.hpp ]] || miss+=("libboost-all-dev")
[[ -d /usr/include/eigen3 || -d ${CONDA_PREFIX:-/nonexistent}/include/eigen3 ]] || miss+=("libeigen3-dev")
python3 -c 'import yaml' 2>/dev/null || miss+=("pyyaml (make conda-env)")
if ((${#miss[@]})); then echo "[ERROR] missing: ${miss[*]}"; echo "  apt: sudo apt install build-essential cmake pkg-config libboost-all-dev libeigen3-dev python3-dev"; exit 1; fi
echo "[INFO] build dependencies ok"
