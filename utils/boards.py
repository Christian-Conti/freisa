#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Installs the boards listed in boards.yml: fetches their board files (XilinxBoardStore or any git repository,
#            default branch, i.e. their latest version), generates boards/<name>/.../pins.xdc and writes targets/<name>.yml with the settings derived
#            from the FPGA part. boards.lock records the commits that were fetched.
# Module   : boards.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
"""Usage: boards.py install [--only name ...]"""
import argparse, hashlib, pathlib, re, shutil, subprocess, sys, xml.etree.ElementTree as ET
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "third_party" / "boards"
STORE = "https://github.com/Xilinx/XilinxBoardStore.git"
HEADER = ("# Copyright 2026 FREISA contributors\n# Apache License, Version 2.0, see LICENSE.md for details.\n"
          "# SPDX-License-Identifier: Apache-2.0\n#\n")

def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

def fetch(url, paths, ref="HEAD"):
    """Shallow fetch of `ref` (default: the repository's default branch, its latest version) of `url` into the cache, extracting only `paths`; returns (dir, commit).
    No sparse-checkout: `git checkout <commit> -- <paths>` also works with old git versions."""
    d = CACHE / hashlib.sha1(url.encode()).hexdigest()[:12]
    if not (d / ".git").exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", url, str(d))
    git("fetch", "-q", "--depth", "1", "origin", ref, cwd=d)
    sha = git("rev-parse", "FETCH_HEAD", cwd=d)
    git("checkout", "-q", sha, "--", *paths, cwd=d)
    return d, sha

def vkey(v): return [int(x) if x.isdigit() else x for x in re.split(r"[.\-]", v)]

def latest(d):
    """Board-store layout <board>/<version>/board.xml: newest version; plain layout: the folder itself."""
    if (d / "board.xml").exists(): return d
    vs = sorted((x for x in d.iterdir() if x.is_dir() and (x / "board.xml").exists()), key=lambda x: vkey(x.name))
    if not vs: sys.exit(f"no board.xml under {d}")
    return vs[-1]

def pins_xdc(pins_xml, out):
    root = ET.parse(pins_xml).getroot()
    lines = [f"# generated from {pins_xml.name}: {root.get('part_name')}"]
    for p in root.iter("pin"):
        name, loc, std = p.get("name").strip(), p.get("loc"), p.get("iostandard")
        if not loc: continue
        body = f"set_property PACKAGE_PIN {loc} [get_ports {{{name}}}]" + (f"; set_property IOSTANDARD {std} [get_ports {{{name}}}]" if std else "")
        lines.append(f"if {{[llength [get_ports -quiet {{{name}}}]]}} {{ {body} }}")
    out.write_text("\n".join(lines) + "\n")

SERIES7 = {"xc7z": "zynq7", "xc7a": "artix7", "xc7k": "kintex7", "xc7s": "spartan7"}

def derived(part):
    """Settings every FREISA board file needs, derived from the FPGA part."""
    p = part.lower()
    if p.startswith("xc7"):
        pkg = re.search(r"(clg|clga|cpg|csg|cpga|fbg|ffg|fgg|ftg|sbg|rbg|fbv|ffv)\d+", p)
        return {"family": "xc7", "yosys_family": "xc7", "legalize": "nextpnr_if", "package": pkg.group(0) if pkg else None,
                "db_root": f"third_party/prjxray-db/{SERIES7.get(p[:4], 'zynq7')}"}
    if p.startswith(("xczu", "xck")):
        return {"family": "xczu", "yosys_family": "xcup", "has_ps": True, "carry": "none", "legalize": "dreamplace"}
    if p.startswith(("xcvu", "xcku")):
        return {"family": p[:4], "yosys_family": "xcup", "carry": "none", "legalize": "dreamplace"}
    sys.exit(f"part {part}: family not supported by FREISA (xc7, xczu, xck, xcvu, xcku)")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["install"]); ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "boards.yml")) or {}
    boards = cfg.get("boards") or {}
    if a.only: boards = {k: v for k, v in boards.items() if k in a.only}
    lock = []
    for name, b in boards.items():
        if "part" not in b or "source" not in b: sys.exit(f"boards.yml: {name} needs `part` and `source`")
        src = b["source"]; dst = ROOT / "boards" / name
        shutil.rmtree(dst, ignore_errors=True); dst.mkdir(parents=True)
        stores = src.get("store") or []
        stores = [stores] if isinstance(stores, str) else stores
        if stores:
            repo, sha = fetch(STORE, [f"boards/{p}" for p in stores], src.get("ref", "HEAD"))
            dirs = [(p.split("/")[-1], latest(repo / "boards" / p)) for p in stores]
            lock.append(f"{name:<14} {STORE} {sha}")
        elif "git" in src:
            want = [src["path"]] + ([src["xdc"]] if src.get("xdc") else [])
            repo, sha = fetch(src["git"], want, src.get("ref", "HEAD"))
            dirs = [(pathlib.Path(src["path"]).name, latest(repo / src["path"]))]
            if src.get("xdc"): shutil.copy(repo / src["xdc"], dst / "board.xdc")
            lock.append(f"{name:<14} {src['git']} {sha}")
        else:
            sys.exit(f"boards.yml: {name}: source needs `store:` or `git:`")
        for sub, d in dirs:
            out = dst / sub; out.mkdir(exist_ok=True)
            for f in ("board.xml", "part0_pins.xml", "preset.xml", "LICENSE"):
                if (d / f).exists(): shutil.copy(d / f, out / f)
            if (out / "part0_pins.xml").exists(): pins_xdc(out / "part0_pins.xml", out / "pins.xdc")
        t = {"part": b["part"], **{k: v for k, v in derived(b["part"]).items() if v is not None},
             **{k: v for k, v in b.items() if k not in ("source", "part", "description")}}
        (ROOT / "targets" / f"{name}.yml").write_text(
            HEADER + f"# Info     : Board {name}{(': ' + b['description']) if b.get('description') else ''}.\n"
            "#            Generated by `make install-boards` from boards.yml: edit boards.yml, not this file.\n"
            f"# Module   : {name}.yml\n\n" + yaml.safe_dump(t, sort_keys=False))
        print(f"[INFO] {name}: {b['part']}  board files -> boards/{name}/, settings -> targets/{name}.yml")
    if not a.only:
        (ROOT / "boards.lock").write_text(HEADER + "# Info     : Commits fetched by the last `make install-boards` (default branch of each repository).\n"
                                          "# Module   : boards.lock\n\n" + "\n".join(lock) + "\n")

main()
