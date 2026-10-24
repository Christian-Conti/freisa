#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Clones the pinned third-party tools.
# Module   : fetch_tools.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set -euo pipefail

info() {
  echo -e "\033[1;34m[INFO]\033[0m $*"
}

cd "$(dirname "$0")/.."
mkdir -p third_party

want=" $* "
grep -vE '^#|^[[:space:]]*$' tools.lock | while read -r name url ref; do
  [[ $# -eq 0 || $want == *" $name "* ]] || continue
  d=third_party/$name
  pinned=0; [[ $ref =~ ^[0-9a-f]{40}$ ]] && pinned=1
  if [[ $pinned == 1 && -d $d/.git && $(git -C "$d" rev-parse HEAD) == "$ref" ]]; then info "$name @ ${ref:0:10} (present, pinned)"; continue; fi
  [[ -d $d/.git ]] || git clone --quiet "$url" "$d"
  git -C "$d" fetch --quiet origin "$ref" 2>/dev/null || git -C "$d" fetch --quiet origin
  git -C "$d" checkout --quiet FETCH_HEAD 2>/dev/null || git -C "$d" checkout --quiet "$ref"
  git -C "$d" submodule update --init --recursive --quiet
  info "$name @ $(git -C "$d" rev-parse --short=10 HEAD) ($([[ $pinned == 1 ]] && echo pinned || echo "latest of the default branch"))"
done
