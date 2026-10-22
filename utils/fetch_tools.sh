#!/usr/bin/env bash
# Clone the tools.lock entries named in $@ (default: all) at their pinned commit into third_party/.
# Tools already at the pinned commit are left alone (no network).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p third_party
want=" $* "
grep -v '^#' tools.lock | while read -r name url sha; do
  [[ $# -eq 0 || $want == *" $name "* ]] || continue
  d=third_party/$name
  if [[ -d $d/.git && $(git -C "$d" rev-parse HEAD) == "$sha" ]]; then echo "[INFO] $name @ ${sha:0:10} (present)"; continue; fi
  [[ -d $d/.git ]] || git clone --quiet "$url" "$d"
  git -C "$d" fetch --quiet origin "$sha" 2>/dev/null || true
  git -C "$d" checkout --quiet "$sha"
  git -C "$d" submodule update --init --recursive --quiet
  echo "[INFO] $name @ ${sha:0:10}"
done
