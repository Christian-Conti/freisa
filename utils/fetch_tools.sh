#!/usr/bin/env bash
# Clone every tools.lock entry at its pinned commit (with submodules) into third_party/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p third_party
grep -v '^#' tools.lock | while read -r name url sha; do
  d=third_party/$name
  [[ -d $d/.git ]] || git clone --quiet "$url" "$d"
  git -C "$d" fetch --quiet origin "$sha" 2>/dev/null || true
  git -C "$d" checkout --quiet "$sha"
  git -C "$d" submodule update --init --recursive --quiet
  echo "[INFO] $name @ ${sha:0:10}"
done
