# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Bitstream upload backends.
# Module   : upload.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import os, pathlib, re, shutil, subprocess, sys
from .. import term as _term
from ..core import Backend, backend, find_vivado

PERM = ("USB permission denied on the JTAG cable. One-time setup (needs root):\n"
        "  sudo /eda/Xilinx/Vivado/2024.1/data/xicom/cable_drivers/lin64/install_script/install_drivers/install_drivers\n"
        "If the rules are already installed they only apply to newly plugged devices: replug the board or run\n"
        "  sudo udevadm control --reload-rules && sudo udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=0403")

def _go(ctx, cmd, log, **kw):
    """Run the programmer; on failure name the usual causes instead of only pointing at the log."""
    try:
        ctx.sh(cmd, log, **kw)
    except SystemExit as e:
        txt = (ctx.work / f"{log}.log").read_text(errors="replace")
        if re.search(r"Access denied|insufficient permissions|usb_open\(\) failed", txt): raise SystemExit(f"{e}\n{PERM}")
        if re.search(r"no current hw_target|no JTAG target has a device|No matching targets found", txt):
            raise SystemExit(f"{e}\nVivado sees no JTAG cable: board powered and USB-JTAG connected? If it is, it is usually permissions:\n{PERM}")
        raise

def _model(part):
    """FPGA model as JTAG reports it: xczu7ev-ffvc1156-2-e -> xczu7ev, xc7z020clg400-1 -> xc7z020, xck26-... -> xck26."""
    return re.match(r"(xc(?:zu\d+(?:eg|ev|cg|dr)?|k\d+|7[azks]\d+t?|vu\d+p?|ku\d+p?))", part).group(1)

CABLE = {"6010": "ft2232", "6011": "ft4232", "6014": "ft232h"}  # FTDI product id -> openFPGALoader cable type

def _scan():
    """Every FTDI JTAG chip on USB, probed with openFPGALoader --detect: serial, USB bus:dev, product, FPGA models."""
    out = []
    for d in sorted(pathlib.Path("/sys/bus/usb/devices").glob("*")):
        try:
            if (d / "idVendor").read_text().strip() != "0403": continue
            rd = lambda f: (d / f).read_text().strip() if (d / f).exists() else ""
            pid, bd = rd("idProduct"), f"{int(rd('busnum'))}:{int(rd('devnum'))}"
            r = subprocess.run(["openFPGALoader", "-c", CABLE.get(pid, "ft2232"), "--busdev-num", bd, "--detect"],
                               capture_output=True, text=True, timeout=30)
            txt = r.stdout + r.stderr
            err = "" if re.search(r"model\s", txt) else (txt.strip().splitlines() or ["no answer"])[-1]
            out.append(dict(serial=rd("serial") or "-", busdev=bd, cable=CABLE.get(pid, "ft2232"),
                            product=f"{rd('manufacturer')} {rd('product')}".strip(), models=re.findall(r"model\s+(\S+)", txt), err=err))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return out

def choose(ctx, verb="programming"):
    """Pick the JTAG cable to program. One compatible board: use it. Several devices on a terminal: show them (like
    jtag-reboot) and ask. Otherwise JTAG=<serial> (or `jtag_serial` in the board file) selects it."""
    t = ctx.target
    want = re.sub(r"(ev|eg|cg|dr)$", "", _model(t["part"]))
    devs = _scan()
    forced = os.environ.get("JTAG") or t.get("jtag_serial")
    if forced:
        devs = [d for d in devs if d["serial"].startswith(str(forced).rstrip("A"))]
        if not devs: raise SystemExit(f"no JTAG cable with serial {forced}")
    ok = [d for d in devs if any(m.startswith(want) for m in d["models"])]
    table = [f"  {_term.bold('#'):>3}  {'SERIAL':<14} {'USB':<6} {'CABLE':<28} FPGA"]
    for i, d in enumerate(devs, 1):
        fpga = ", ".join(d["models"]) or _term.dim(d["err"][:50])
        mark = _term.OK if d in ok else " "
        table.append(f"  {i:>3}  {d['serial']:<14} {d['busdev']:<6} {d['product'][:28]:<28} {fpga} {mark}")
    if not ok and not (len(devs) > 1 and sys.stdin.isatty()):
        hint = f"\n{PERM}\n(or another program, e.g. a running Vivado hw_server, holds the cable)" if any(re.search(r"denied|usb_open|unable to open|claim", d["err"]) for d in devs) else ""
        raise SystemExit(f"no connected JTAG cable has a {want}:\n" + "\n".join(table) + hint)
    if len(devs) > 1 and sys.stdin.isatty() and not forced:
        print(f"    JTAG devices ({_term.OK} = has the {want} of this board):\n" + "\n".join(table), flush=True)
        default = devs.index(ok[0]) + 1 if ok else 1
        ans = input(f"    board to program [{default}]: ").strip() or str(default)
        if not ans.isdigit() or not 1 <= int(ans) <= len(devs): raise SystemExit("no board selected")
        d = devs[int(ans) - 1]
        if d not in ok: print("    " + _term.note(f"{d['serial']} does not report a {want}: programming may fail"), flush=True)
    elif len(ok) > 1:
        raise SystemExit("several boards with a " + want + " are connected: choose one with JTAG=<serial>\n" + "\n".join(table))
    else:
        d = ok[0]
    (ctx.work / "upload_detect.log").write_text(_term.plain("\n".join(table)) + "\n")
    print(f"    {_term.OK} {verb} {_term.bold(d['serial'])} {_term.dim(d['product'] + ' (USB ' + d['busdev'] + ')')}", flush=True)
    return d

@backend
class OpenFpgaLoader(Backend):
    """openFPGALoader on the JTAG cable chosen by `choose()` (scan by FPGA ID code, ask when several are connected)."""
    stage, name, tools = "upload", "openfpgaloader", ["openFPGALoader"]
    def run(self, ctx):
        d = choose(ctx)
        _go(ctx, ["openFPGALoader", "-c", d["cable"], "--busdev-num", d["busdev"], ctx.art["bit"]], "upload_openfpgaloader")

@backend
class VivadoHw(Backend):
    """Vivado hardware manager. Opens every JTAG target in turn and programs the first device matching this board's FPGA
    (`hw_device` pattern, default from the part), so the right board is found by its ID code."""
    stage, name, vendor = "upload", "vivado", "vivado"
    def supports(self, target):
        return None if find_vivado() else "Vivado not found (PATH, $VIVADO, or /eda/Xilinx/Vivado/<version>/bin/vivado)"
    def run(self, ctx):
        t = ctx.target
        pat = t.get("hw_device") or re.sub(r"(ev|eg|cg|dr)$", "", _model(t["part"])) + "*"  # Vivado names: xczu7_0, xc7z020_1
        serial = None
        if shutil.which("openFPGALoader"):  # same scan / choice as openFPGALoader, then let Vivado open that cable only
            serial = choose(ctx)["serial"]
        serial = serial or os.environ.get("JTAG") or t.get("jtag_serial")
        targets = f"[get_hw_targets *{str(serial).rstrip('A')}*]" if serial else "[get_hw_targets]"
        tcl = ctx.work / "upload.tcl"
        tcl.write_text(f"""open_hw_manager
connect_hw_server
set done 0
set seen {{}}
foreach tg {targets} {{
  if {{[catch {{open_hw_target $tg}}]}} continue
  set devs [get_hw_devices -quiet {{{pat}}}]
  if {{[llength $devs]}} {{
    set dev [lindex $devs 0]
    puts "FREISA: programming $dev on $tg"
    current_hw_device $dev
    set_property PROGRAM.FILE {{{ctx.art['bit']}}} $dev
    program_hw_devices $dev
    set done 1
    break
  }}
  lappend seen "$tg: [get_hw_devices -quiet]"
  close_hw_target $tg
}}
if {{!$done}} {{ puts "FREISA: no JTAG target has a device matching {pat}"; foreach x $seen {{ puts "FREISA:   $x" }}; close_hw_manager; exit 1 }}
close_hw_manager
""")
        _go(ctx, [find_vivado(), "-mode", "batch", "-nojournal", "-log", "upload_vivado.vivado.log", "-source", tcl.name], "upload_vivado", cwd=ctx.work)
