#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : UART loopback test: finds the board's PL UART serial port (same USB cable as JTAG), sends data, checks the echo.
# Module   : uart_test.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

"""Usage: uart_test.py -t <board> [--port /dev/ttyUSBx] [--baud 115200] [--bytes 256]

The board file gives `uart_channel` (FT4232H interface number of the PL UART). The JTAG scan of `freisa.py upload` finds the
cable whose FPGA is this board's; its tty on that interface is the PL UART. Exit 0 when every byte comes back unchanged."""
import argparse, os, pathlib, re, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import serial
from freisa import core, term as T
from freisa.stages import upload

ap = argparse.ArgumentParser()
ap.add_argument("-t", "--target", default=None, help="board; default: the connected board that has a PL UART"); ap.add_argument("--port"); ap.add_argument("--baud", type=int, default=115200)
ap.add_argument("--bytes", type=int, default=256)

a = ap.parse_args()

root = pathlib.Path(__file__).resolve().parents[1]

with_uart = {p.stem: core.load_yaml(p) for p in sorted((root / "targets").glob("*.yml"))}
with_uart = {k: v for k, v in with_uart.items() if "uart_channel" in v}

if a.target and a.target not in with_uart and not a.port:
    sys.exit(T.error(f"{a.target}: its USB serial port is not wired to FPGA pins (no PL UART), the loopback cannot run there.\n"
                     f"Boards with a PL UART: {', '.join(with_uart)} -> python freisa.py uart-test -t <board>"))

if a.target is None:  # pick the connected board that has a PL UART
    found = [(k, d) for k, v in with_uart.items() for d in upload._scan()

             if any(m.startswith(re.sub(r"(ev|eg|cg|dr)$", "", upload._model(v["part"]))) for m in d["models"])]

    if not found: sys.exit(T.error(f"no connected board with a PL UART ({', '.join(with_uart)}); pass TARGET= or PORT="))
    a.target = found[0][0]

    print(f"    {T.OK} board {T.bold(a.target)} found on cable {found[0][1]['serial']}")

target = core.load_yaml(root / "targets" / f"{a.target}.yml")

def tty_of(serial_no, interface):
    for t in sorted(pathlib.Path("/sys/class/tty").glob("ttyUSB*")):
        d = (t / "device").resolve(); intf = d.parent; usb = intf.parent
        try:
            if (usb / "serial").read_text().strip() == serial_no and int((intf / "bInterfaceNumber").read_text(), 16) == interface:
                return f"/dev/{t.name}"
        except OSError:
            pass
    return None

port = a.port

if port is None:
    if "uart_channel" not in target: sys.exit(T.error(f"targets/{a.target}.yml has no uart_channel: pass PORT=/dev/ttyUSBx"))
    class Ctx: pass
    ctx = Ctx(); ctx.target = target; ctx.work = pathlib.Path("/tmp")
    dev = upload.choose(ctx, "board on cable")   # same scan / choice as freisa.py upload
    port = tty_of(dev["serial"], int(target["uart_channel"]))
    if port is None: sys.exit(T.error(f"no ttyUSB on interface {target['uart_channel']} of cable {dev['serial']}"))

print(f"{T.ARROW} {T.bold('uart')}     {T.cyan(port)} {T.dim(f'{a.baud} baud, {a.bytes} bytes')}")

data = os.urandom(a.bytes)

with serial.Serial(port, a.baud, timeout=2) as s:
    s.reset_input_buffer(); time.sleep(0.05)
    s.write(data); s.flush()
    back = s.read(len(data))

ok = back == data

print(f"  {T.OK if ok else T.FAIL} {'echo matches' if ok else 'echo differs'}: sent {len(data)}, received {len(back)}" 
      + ("" if ok else f", first difference at byte {next((i for i, (x, y) in enumerate(zip(data, back)) if x != y), len(back))}"))
if not ok:
    print("    " + T.note(f"is uart_loopback loaded on the board? python freisa.py run -d uart_loopback -t {a.target} && "
                       f"python freisa.py upload -d uart_loopback -t {a.target}"))
    
sys.exit(0 if ok else 1)
