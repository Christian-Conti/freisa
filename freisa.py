#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : FREISA entry point: `python freisa.py` opens the interactive interface, `python freisa.py <command>` runs one
#            command (install, run, check, upload, ...). Re-starts itself in the FREISA conda env when needed.
# Module   : freisa.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = os.environ.get("ENV_NAME", "freisa")
USAGE = """usage: python freisa.py [command] [options]        (no command: interactive interface)

flow
  run       -d <design> -t <board> [--from S] [--to S] [--step STAGE=TOOL]...  check, then run the flow
  check     -d <design> -t <board> [--from S] [--to S] [--step STAGE=TOOL]...  can the chosen tools run?
  upload    -d <design> -t <board> [--tool openfpgaloader|vivado] [--bit F]    program the board (JTAG=<serial> picks the cable)
  uart-test [-t <board>] [--port /dev/ttyUSBx] [--baud N]                       PL UART loopback test
  doctor    [-d <design>] [-t <board>]                                          every tool of every step (all boards without -t)
  status    [env|tools|boards|projects|builds]                                  dashboard
  show      <design> <board>                                                    details of one build
install
  install   [all|conda|deps|boards [<board>...]|xc7|interchange|prjuray|dreamplace] [--force]   (default all; --force rebuilds)
  fetch     [tool...]          clone the tools of tools.lock at their pinned commit
  outdated                     tools whose upstream is newer than tools.lock
  update    <tool> [ref]       re-pin one tool in tools.lock
  uninstall                    remove third_party/, install/, build/ and the conda envs
  clean                        remove build/
stages: sources synth netlist place route bitgen · designs: designs/<name>.yml · boards: targets/<name>.yml"""

BUILD = {  # part: (present once built, tools.lock names to fetch, build script)
    "xc7": ("install/bin/xc7frames2bit", "prjxray prjxray-db nextpnr-xilinx", "build_xc7.sh"),
    "interchange": ("install/bin/nextpnr-fpga_interchange", "nextpnr-fpga-interchange python-fpga-interchange fpga-interchange-schema", "build_interchange.sh"),
    "prjuray": ("install/bin/xcframes2bit", "prjuray prjuray-db", "build_prjuray.sh"),
    "dreamplace": ("third_party/dreamplacefpga/install/dreamplacefpga", "dreamplacefpga", "build_dreamplace.sh"),
}
NO_ENV = ("-h", "--help", "help", "fetch", "outdated", "update", "uninstall", "clean")  # commands that do not need the conda env

def sh(*cmd, ok=False):
    """Run a command in the repository; stop with its exit code on failure unless `ok`."""
    rc = subprocess.run(list(cmd), cwd=ROOT).returncode
    if rc and not ok: sys.exit(rc)

def install(args):
    force = "--force" in args; args = [a for a in args if a != "--force"]
    part = args[0] if args else "all"
    if part not in ("all", "conda", "deps", "boards", *BUILD): sys.exit(USAGE)
    if part in ("all", "deps"): sh("bash", "utils/check_deps.sh", ok=True)
    if part in ("all", "boards"): sh(sys.executable, "utils/boards.py", "install", *(["--only", *args[1:]] if args[1:] else []))
    for name, (done, tools, script) in BUILD.items():
        if part not in ("all", name): continue
        if os.path.exists(os.path.join(ROOT, done)) and not force: print(f"[INFO] {name} present (--force rebuilds)"); continue
        sh("bash", "utils/fetch_tools.sh", *tools.split()); sh("bash", "utils/check_deps.sh"); sh("bash", f"utils/{script}")

def main(cmd, args):
    py = lambda *a: sh(sys.executable, *a)
    if cmd is None:
        from freisa import tui
        tui.main()
    elif cmd in ("-h", "--help", "help"): print(USAGE)
    elif cmd == "install": install(args)
    elif cmd == "run": py("utils/check_flow.py", *args); py("utils/flow.py", "run", *args)
    elif cmd == "check": py("utils/check_flow.py", *args)
    elif cmd == "upload": py("utils/check_flow.py", "--upload", *args); py("utils/flow.py", "upload", *args)
    elif cmd == "doctor": py("utils/flow.py", "doctor", *args, *([] if {"-t", "--target"} & set(args) else ["--all-boards"]))
    elif cmd == "uart-test": py("utils/uart_test.py", *args)
    elif cmd in ("status", "show"): py("-m", "freisa.cli", *(args if cmd == "status" and args else [cmd, *args]))
    elif cmd == "fetch": sh("bash", "utils/fetch_tools.sh", *args)
    elif cmd in ("outdated", "update"): sh("bash", "utils/tool_version.sh", cmd, *args)
    elif cmd in ("uninstall", "clean"):
        shutil.rmtree(os.path.join(ROOT, "build"), ignore_errors=True)
        if cmd == "uninstall":
            for d in ("third_party", "install"): shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)
            for e in (ENV, "freisa-if"): sh("conda", "env", "remove", "-y", "-n", e, ok=True)
    else: sys.exit(f"unknown command {cmd}\n\n{USAGE}")

cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else (None, [])
if cmd == "install" and (args[:1] or ["all"])[0] in ("all", "conda") and not os.environ.get("FREISA_REEXEC"):
    subprocess.run(["bash", os.path.join(ROOT, "utils/conda_env.sh")], env={**os.environ, "ENV_NAME": ENV}, check=True)  # miniconda + env
    if args[:1] == ["conda"]: sys.exit()
if cmd not in NO_ENV and os.environ.get("CONDA_DEFAULT_ENV") != ENV:
    # exec the env's python directly (not `conda run`: it sits in between, catches Ctrl+C and prints its own errors)
    conda = shutil.which("conda") or os.path.expanduser("~/miniconda3/bin/conda")
    base = subprocess.run([conda, "info", "--base"], capture_output=True, text=True).stdout.strip() if os.path.exists(conda) else ""
    prefix = os.path.join(base, "envs", ENV)
    py = os.path.join(prefix, "bin", "python")
    if os.environ.get("FREISA_REEXEC") or not os.path.exists(py):
        sys.exit(f"FREISA conda env '{ENV}' not found: run `python freisa.py install` first")
    os.environ.update(FREISA_REEXEC="1", CONDA_DEFAULT_ENV=ENV, CONDA_PREFIX=prefix,
                      PATH=os.path.join(prefix, "bin") + os.pathsep + os.environ.get("PATH", ""))
    os.execv(py, [py, *sys.argv])

os.environ["PATH"] = os.path.join(ROOT, "install", "bin") + os.pathsep + os.environ.get("PATH", "")  # tools built by install
sys.path.insert(0, ROOT)
main(cmd, args)
