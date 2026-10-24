#!/usr/bin/env bash
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Compares and updates the pinned tool versions.
# Module   : tool_version.sh
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set -euo pipefail

cd "$(dirname "$0")/.."

case "${1:-}" in
  outdated)
    grep -vE '^#|^[[:space:]]*$' tools.lock | while read -r name url sha; do
      head=$(git ls-remote "$url" HEAD | cut -c1-40)
      if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then echo "latest    $name follows $sha (upstream ${head:0:10}; make fetch updates it)"
      elif [[ $head == "$sha" ]]; then echo "ok        $name ${sha:0:10}"
      else echo "pinned    $name ${sha:0:10}, upstream ${head:0:10}"; fi
    done ;;

  update)
    name=${2:?usage: update <name> [ref]}; line=$(grep -E "^$name[[:space:]]" tools.lock) || { echo "unknown tool $name"; exit 1; }
    url=$(awk '{print $2}' <<<"$line"); old=$(awk '{print $3}' <<<"$line")
    new=$(git ls-remote "$url" "${3:-HEAD}" | cut -c1-40 | head -1); [[ -n $new ]] || { echo "ref not found"; exit 1; }
    sed -i "s#^\($name[[:space:]]\+[^[:space:]]\+[[:space:]]\+\)$old#\1$new#" tools.lock
    echo "$name: ${old:0:10} -> ${new:0:10}  (run: make fetch, rebuild the tool if it has an install-* target, then re-run the smoke tests in docs/adding-blocks.md)" ;;
  *) echo "usage: $0 outdated | update <name> [ref]"; exit 1 ;;
esac
