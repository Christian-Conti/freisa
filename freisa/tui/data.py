# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive interface: what it reads from the repository (projects, boards, builds, serial ports),
#            constants and small formatting helpers.
# Module   : data.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, textwrap, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from .. import cli, core, term as T
from ..stages import upload

ROOT = cli.ROOT
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
BAUDS = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
CHIP = ["  ┌┴┴┴┴┴┴┴┴┴┐ ",
        " ─┤ ▓▓▓▓▓▓▓ ├─",
        " ─┤ ▓ LUT ▓ ├─",
        " ─┤ ▓▓▓▓▓▓▓ ├─",
        "  └┬┬┬┬┬┬┬┬┬┘ "]

# ------------------------------------------------------------------ data
def designs():  return {f.stem: f for f in sorted((ROOT / "designs").rglob("*.yml"))}
def boards_cfg(): return (yaml.safe_load(open(ROOT / "boards.yml")) or {}).get("boards") or {}
def installed(): return sorted(p.stem for p in (ROOT / "targets").glob("*.yml"))
def target(name): return core.load_yaml(ROOT / "targets" / f"{name}.yml")
def rel(p): return os.path.relpath(p, ROOT)

def pc_status():
    """CPU, memory, disk of the build folder, load: (long line, short line for narrow screens, highest % of cpu/mem)."""
    try:
        import psutil
        c, m, dk = psutil.cpu_percent(), psutil.virtual_memory(), psutil.disk_usage(str(ROOT))
        return (f"cpu {c:>3.0f}% ×{psutil.cpu_count()}  ·  mem {m.used / 2**30:.1f}/{m.total / 2**30:.0f}G  ·  "
                f"disk {dk.free / 2**30:.0f}G free  ·  load {os.getloadavg()[0]:.1f}"), \
               f"cpu {c:.0f}% mem {m.used / 2**30:.0f}/{m.total / 2**30:.0f}G", max(c, m.percent)
    except Exception: return "", "", 0

def builds():
    """Build directories build/<design>/<board>, newest first."""
    ds = [p for p in (ROOT / "build").glob("*/*") if (p / "flow.log").exists()]
    return sorted(ds, key=lambda p: (p / "flow.log").stat().st_mtime, reverse=True)

def fpga_want(part):
    """Prefix of the FPGA model JTAG reports for this part (same rule as `make upload`)."""
    return re.sub(r"(ev|eg|cg|dr)$", "", upload._model(part))

def ports():
    """[(tty, usb serial, interface number)] of every USB serial port."""
    out = []
    for t in sorted(pathlib.Path("/sys/class/tty").glob("ttyUSB*"), key=lambda p: int(p.name[6:])):
        try:
            intf = (t / "device").resolve().parent
            out.append((f"/dev/{t.name}", (intf.parent / "serial").read_text().strip(), int((intf / "bInterfaceNumber").read_text(), 16)))
        except (OSError, ValueError):
            pass
    return out

def tail(path, n=400):
    """Last lines of a text file (reads only its end)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); f.seek(max(0, f.tell() - 64 * 1024))
            return [T.plain(l) for l in f.read().decode(errors="replace").splitlines()[-n:]]
    except OSError:
        return []

def fmt(s):
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"
