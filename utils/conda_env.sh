#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Installs Miniconda if missing and creates or updates the FREISA conda env (python freisa.py install conda).
# Module   : conda_env.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set -euo pipefail

ENV_NAME="${ENV_NAME:-freisa}"
MINICONDA_DIR="${HOME}/miniconda3"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-${SCRIPT_DIR}/python-requirements.txt}"

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

warn() {
  echo -e "\033[1;33m[WARN]\033[0m $*" >&2
}

err() {
  echo -e "\033[1;31m[ERROR]\033[0m $*" >&2
}

download_file() {
  local url="$1"
  local out="$2"

  if command -v wget >/dev/null 2>&1; then
    wget -q "$url" -O "$out"
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  else
    err "Neither wget nor curl is available..."
    return 1
  fi
}

glibc_version() {
  # Returns glibc version as a comparable integer: major*1000+minor (e.g. 2.17 → 2017)
  local ver
  ver="$(ldd --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+$')"
  local major minor
  major="${ver%%.*}"
  minor="${ver##*.}"
  echo $(( major * 1000 + minor ))
}

ensure_conda() {
  if command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    return 0
  fi

  if [[ ! -x "${MINICONDA_DIR}/bin/conda" ]]; then
    local installer="/tmp/miniconda_installer.sh"
    local arch
    arch="$(uname -m)"

    # Latest Miniconda requires GLIBC >= 2.28.
    # For older systems (e.g. CentOS 7 with GLIBC 2.17) use the last compatible release.
    local glibc_ver
    glibc_ver="$(glibc_version)"
    local suffix
    if (( glibc_ver >= 2028 )); then
      suffix="latest"
    else
      info "GLIBC < 2.28 detected ($(ldd --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+$')), using Miniconda3 py39_4.12.0 (last GLIBC-2.17-compatible release)."
      suffix="py39_4.12.0"
    fi

    local url=""
    case "$arch" in
      x86_64)  url="https://repo.anaconda.com/miniconda/Miniconda3-${suffix}-Linux-x86_64.sh" ;;
      aarch64) url="https://repo.anaconda.com/miniconda/Miniconda3-${suffix}-Linux-aarch64.sh" ;;
      *)
        err "Unsupported architecture: $arch"
        return 1
        ;;
    esac

    download_file "$url" "$installer"
    bash "$installer" -b -p "$MINICONDA_DIR"
    rm -f "$installer"
    info "Miniconda installed to $MINICONDA_DIR..."
  fi

  export PATH="${MINICONDA_DIR}/bin:${PATH}"
  eval "$("${MINICONDA_DIR}/bin/conda" shell.bash hook)"
}

configure_conda_channels() {
  local channels
  channels="$(conda config --show channels 2>/dev/null || true)"

  if grep -qF -- "- defaults" <<<"$channels"; then
    conda config --remove channels defaults || true
    info "Removed 'defaults' channel to avoid non-interactive ToS prompts."
  fi

  if ! grep -qF -- "- conda-forge" <<<"$channels"; then
    conda config --add channels conda-forge
  fi

  conda config --set channel_priority strict
}

accept_conda_tos_if_supported() {
  if conda tos --help >/dev/null 2>&1; then
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true
  fi
}

init_conda_shell() {
  local user_shell
  user_shell="$(basename "${SHELL:-bash}")"

  if conda init "${user_shell}" >/dev/null 2>&1; then
    info "Conda initialized for ${user_shell}. Please restart your shell or run: source ~/.${user_shell}rc"
  else
    warn "Could not run 'conda init ${user_shell}'. You may need to add conda to your shell manually."
  fi
}

install_requirements() {
  python -m pip install --upgrade pip
  python -m pip install -r "$REQUIREMENTS_FILE"
}

ensure_env() {
  configure_conda_channels
  accept_conda_tos_if_supported

  if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
    conda activate "${ENV_NAME}"
    install_requirements
  else
    conda create -y -n "${ENV_NAME}" --override-channels -c conda-forge python=3.11
    conda activate "${ENV_NAME}"
    install_requirements
  fi
}

main() {
  ensure_conda
  init_conda_shell
  accept_conda_tos_if_supported
  ensure_env
  
  info "Environment '${ENV_NAME}' is ready..."
  info "Activate with: conda activate ${ENV_NAME}"
}

main "$@"
