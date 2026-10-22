#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Fetches board files from XilinxBoardStore.
# Module   : boards.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import argparse, pathlib, re, shutil, subprocess, sys, xml.etree.ElementTree as ET
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
URL = "https://github.com/Xilinx/XilinxBoardStore.git"
CACHE = ROOT / "third_party" / "XilinxBoardStore"
LOCK = ROOT / "boards.lock"

def git(*a, cwd=CACHE):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

def supported():
    """target -> list of store paths, from targets/*.yml"""
    out = {}
    for f in sorted((ROOT / "targets").glob("*.yml")):
        t = yaml.safe_load(f.read_text()) or {}
        if t.get("board_store"):
            out[f.stem] = t["board_store"] if isinstance(t["board_store"], list) else [t["board_store"]]
    return out

def read_lock():
    sha, vers = None, {}
    if LOCK.exists():
        for l in LOCK.read_text().splitlines():
            t = l.split()
            if not t or t[0] == "#": continue
            if t[0] == "store": sha = t[2]
            else: vers[t[0]] = t[1]
    return sha, vers

def vkey(v): return [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", v)]

def xdc(pins_xml, out):
    root = ET.parse(pins_xml).getroot()
    lines = [f"# generated from {pins_xml.name} (XilinxBoardStore): {root.get('part_name')}"]
    for p in root.iter("pin"):
        name, loc, std = p.get("name").strip(), p.get("loc"), p.get("iostandard")
        if not loc: continue
        body = f"set_property PACKAGE_PIN {loc} [get_ports {{{name}}}]" + (f"; set_property IOSTANDARD {std} [get_ports {{{name}}}]" if std else "")
        lines.append(f"if {{[llength [get_ports -quiet {{{name}}}]]}} {{ {body} }}")
    out.write_text("\n".join(lines) + "\n")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["install"]); ap.add_argument("--pin", action="store_true")
    a = ap.parse_args()
    want = supported()
    paths = sorted({p for v in want.values() for p in v})
    if not paths: sys.exit("no target has board_store: set it in targets/<board>.yml")
    lock_sha, lock_vers = read_lock()
    if not (CACHE / ".git").exists():
        CACHE.parent.mkdir(exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", URL, str(CACHE)], check=True)
    git("sparse-checkout", "init", "--cone")
    git("sparse-checkout", "set", *[f"boards/{p}" for p in paths])
    if a.pin and lock_sha:
        sha = lock_sha; git("fetch", "-q", "--depth", "1", "origin", sha)
    else:
        git("fetch", "-q", "--depth", "1", "origin", "HEAD"); sha = git("rev-parse", "FETCH_HEAD")
    git("checkout", "-q", sha)
    vers = {}
    for p in paths:
        d = CACHE / "boards" / p
        found = sorted([x.name for x in d.iterdir() if x.is_dir()], key=vkey)
        if not found: sys.exit(f"board {p} not in the store at {sha[:10]}")
        vers[p] = lock_vers.get(p) if a.pin and lock_vers.get(p) in found else found[-1]
    LOCK.write_text("# supported boards (from targets/*.yml `board_store:`); `make install-boards` refreshes, `PIN=1` keeps\n"
                    f"store {URL} {sha}\n# store-path  version\n" + "".join(f"{p} {v}\n" for p, v in vers.items()))
    for tgt, ps in want.items():
        for p in ps:
            src, dst = CACHE / "boards" / p / vers[p], ROOT / "boards" / tgt / pathlib.Path(p).name
            shutil.rmtree(dst, ignore_errors=True); dst.mkdir(parents=True)
            for f in ("board.xml", "part0_pins.xml", "preset.xml", "LICENSE"):
                if (src / f).exists(): shutil.copy(src / f, dst / f)
            if (dst / "part0_pins.xml").exists(): xdc(dst / "part0_pins.xml", dst / "pins.xdc")
            print(f"[INFO] {tgt}: {p} {vers[p]} -> {dst.relative_to(ROOT)}")

main()
