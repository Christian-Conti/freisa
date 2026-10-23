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
grep -vE '^#|^[[:space:]]*$' tools.lock | while read -r name url sha; do
  [[ $# -eq 0 || $want == *" $name "* ]] || continue
  d=third_party/$name
  if [[ -d $d/.git && $(git -C "$d" rev-parse HEAD) == "$sha" ]]; then info "$name @ ${sha:0:10} (present)"; continue; fi
  [[ -d $d/.git ]] || git clone --quiet "$url" "$d"
  git -C "$d" fetch --quiet origin "$sha" 2>/dev/null || true
  git -C "$d" checkout --quiet "$sha"
  git -C "$d" submodule update --init --recursive --quiet
  info "$name @ ${sha:0:10}"
done
