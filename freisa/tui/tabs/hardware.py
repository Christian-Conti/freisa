# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Tab 5: JTAG cables and serial ports; program, reset, UART monitor as a conversation, loopback test.
# Module   : hardware.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, textwrap, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from ... import cli, core, resolve, term as T
from ...stages import upload
from ..data import *
from ..draw import *
from ..jobs import *
from .base import Tab

class Hardware(Tab):
    """JTAG cables (scan, program, reset) and the UART monitor of their serial ports."""
    title, icon = "Hardware", "⚡"
    def __init__(self, app):
        super().__init__(app)
        self.lv, self.cables, self.scanning, self.uart, self.baud, self.hex, self.line = ListView(), [], False, None, 115200, False, ""
        self.last = {}  # cable serial -> last bitstream programmed from here (PL reset on ZynqMP reloads it)
        self.scan()
    def scan(self):
        if self.scanning: return
        self.scanning = True
        def go():
            try: self.cables = upload._scan()
            finally: self.scanning = False
        threading.Thread(target=go, daemon=True).start()
    def items(self):
        """Cables and, under each, its serial ports: [(kind, cable, port)]."""
        out, ps = [], ports()
        for c in self.cables:
            out.append(("cable", c, None))
            out += [("port", c, p) for p in ps if p[1] == c["serial"]]
        known = {c["serial"] for c in self.cables}
        out += [("port", None, p) for p in ps if p[1] not in known]
        return out
    def sel(self):
        it = self.items(); return it[self.lv.i] if it and self.lv.i < len(it) else (None, None, None)
    def boards_of(self, c):
        """Installed boards whose FPGA this cable reports."""
        out = []
        for b in installed():
            try:
                if any(m.startswith(fpga_want(target(b)["part"])) for m in c["models"]): out.append(b)
            except Exception: pass
        return out
    def uart_name(self, c, p):
        for b in self.boards_of(c) if c else []:
            if str(target(b).get("uart_channel", "")) == str(p[2]): return f"PL UART of {b}"
        return ""
    def program(self):
        k, c, _ = self.sel()
        if not c: self.app.flash("select a JTAG cable", C["warn"]); return
        bs = self.boards_of(c)
        opts = []
        for d in builds():
            bit = cli.build_info(d)[1]
            if bit and (d.name in bs or not bs): opts.append((f"{d.parent.name}/{d.name}", str(bit), rel(bit), 0))
        opts.append(("other file…", "", "type a path", C["dim"]))
        v = modal_pick(self.app, f"bitstream for {c['serial']} ({', '.join(c['models']) or '?'})", opts)
        if v == "": v = modal_text(self.app, "bitstream file")
        if v:
            self.last[c["serial"]] = v
            self.run(["openFPGALoader", "-c", c["cable"], "--busdev-num", c["busdev"], v], f"program {c['serial']}")
    def reset_pl(self):
        k, c, _ = self.sel()
        if c and any(m.startswith("xczu") for m in c["models"]):  # openFPGALoader --reset does not support ZynqMP: reload the bitstream
            v = self.last.get(c["serial"])
            if not v: self.app.flash("ZynqMP: reset reloads the bitstream, pick it once", C["warn"]); self.program(); return
            if confirm(self.app, f"reset the PL on {c['serial']}: reload {rel(v)}?"):
                self.run(["openFPGALoader", "-c", c["cable"], "--busdev-num", c["busdev"], v], f"reset PL {c['serial']} (reload)")
        elif c and confirm(self.app, f"reset the FPGA on {c['serial']}? (clears the loaded bitstream)"):
            self.run(["openFPGALoader", "-c", c["cable"], "--busdev-num", c["busdev"], "--reset"], f"reset PL {c['serial']}")
    def reset_sys(self):
        k, c, _ = self.sel()
        viv = core.find_vivado()
        xsdb = shutil.which("xsdb") or (str(pathlib.Path(shutil.which(viv) or viv).parent / "xsdb") if viv else None)
        if not c or not xsdb or not os.path.exists(xsdb): self.app.flash("system reset needs a cable and Vivado's xsdb", C["bad"]); return
        if not confirm(self.app, f"reset the whole board (PS and PL) on {c['serial']}? (xsdb, vivado)"): return
        tcl = pathlib.Path(tempfile.mkdtemp()) / "reset.tcl"
        tcl.write_text("connect\n"
                       f"targets -set -nocase -filter {{jtag_cable_serial =~ \"*{c['serial'].rstrip('A')}*\" && (name =~ \"PSU\" || name =~ \"APU\")}}\n"
                       "rst -system\nafter 500\ndisconnect\n")
        self.run([xsdb, tcl], f"reset system {c['serial']} (vivado)")
    def toggle_uart(self):
        if self.uart: self.uart.close(); self.uart = None; return
        k, c, p = self.sel()
        if k != "port": self.app.flash("select a serial port (under its cable)", C["warn"]); return
        try: self.uart = Uart(p[0], self.baud)
        except Exception as e: self.app.flash(f"cannot open {p[0]}: {e}", C["bad"])
    def set_baud(self):
        v = modal_pick(self.app, "baud rate", [(str(b), b, "", 0) for b in BAUDS], self.baud)
        if v:
            self.baud = v
            if self.uart: p = self.uart.port; self.uart.close(); self.uart = Uart(p, v)
    def loopback(self):
        k, c, p = self.sel()
        if self.uart: self.uart.close(); self.uart = None  # the test opens the port itself
        self.run([*FREISA, "uart-test", *(["--port", p[0]] if p else []), "--baud", str(self.baud)], "uart loopback test")
    def keys(self):
        return [("s", "scan", self.scan), ("p", "program", self.program), ("R", "reset PL", self.reset_pl), ("Y", "reset system (vivado)", self.reset_sys),
                ("o", "open/close UART", self.toggle_uart), ("b", "baud", self.set_baud), ("i", "type", self.typing),
                ("h", "hex", lambda: setattr(self, "hex", not self.hex)), ("t", "loopback test", self.loopback),
                ("C", "clear", lambda: self.uart and self.uart.clear()), ("x", "stop", self.stop)]
    def chat(self, w, y, x, h, wd, title):
        """Conversation view: sent messages on the left, received on the right, newest at the bottom."""
        box(w, y, x, h, wd, title + "  ◀ sent · received ▶", True)
        bw = max(10, (wd - 4) * 2 // 3)  # bubble width
        rows = []
        for d, b, t in self.uart.chat:
            body = textwrap.wrap(bubble_text(b), bw - 4, break_on_hyphens=False) or [""]
            n = max(map(len, body)); stamp = time.strftime("%H:%M:%S", time.localtime(t))
            left = d == "tx"; cx = x + 2 if left else x + wd - n - 6
            attr = C["accent"] if left else C["ok"]
            rows.append((cx, f"{'you' if left else 'board'} · {stamp}", C["dim"]))
            rows.append((cx, "╭" + "─" * (n + 2) + "╮", attr))
            rows += [(cx, "│ " + l.ljust(n) + " │", attr) for l in body]
            rows.append((cx, "╰" + "─" * (n + 2) + "╯", attr))
        inner = h - 2
        top = max(0, len(rows) - inner - self.scroll)
        for i, (cx, text, attr) in enumerate(rows[top:top + inner]): put(w, y + 1 + i, cx, text, attr, x + wd - 1 - cx)
        if not rows: put(w, y + 1, x + 2, "nothing yet: i to type a message", C["dim"], wd - 4)
    def typing(self):
        if not self.uart: self.app.flash("open a UART first (o)", C["warn"]); return
        self.capture, self.line = True, ""
    def key(self, k):
        if self.capture:
            if k == 27: self.capture = False
            elif k in KEYNAMES["Enter"]: self.uart.send((self.line + "\n").encode()); self.line = ""
            elif k in (curses.KEY_BACKSPACE, 127, 8): self.line = self.line[:-1]
            elif 32 <= k < 127: self.line += chr(k)
            return True
        if self.lv.move(k, len(self.items())): return True
        return super().key(k)
    def draw(self, w, y, x, h, wd):
        its = self.items()
        rows = []
        for kind, c, p in its:
            if kind == "cable":
                ok = bool(c["models"])
                rows.append([(" ◆ ", C["accent"] if ok else C["bad"]), (c["serial"].ljust(14), curses.A_BOLD), (", ".join(c["models"]) or ("no access: permissions?" if re.search(r"denied|usb_open|claim", c["err"]) else "no FPGA answered"), C["ok"] if ok else C["bad"])])
                bs = self.boards_of(c)
                rows.append([("     ", 0), (f"{c['product'][:22]} · USB {c['busdev']}" + (f" · {', '.join(bs)}" if bs else ""), C["dim"])])
            else:
                u = self.uart_name(c, p) if c else ""
                rows.append([("   └ ", C["dim"]), (p[0].ljust(14), C["info"]), (f"if {p[2]}  {u}", C["ok"] if u else C["dim"])])
        (ly, lx, lh, lw), (ry, rx, rh, rw) = split(y, x, h, wd, min(60, wd // 2 - 4), min(len(rows) + 2, h // 2))
        box(w, ly, lx, lh, lw, ("JTAG " + SPIN[int(time.time() * 8) % 10] + " scanning") if self.scanning else f"JTAG CABLES ({len(self.cables)})  ↑↓", True)
        # the list moves on items; cable rows take two lines: map the selection to the drawn rows
        sel_row, r = 0, 0
        for i, (kind, _, _) in enumerate(its):
            if i == self.lv.i: sel_row = r
            r += 2 if kind == "cable" else 1
        lv = ListView(); lv.i = sel_row
        lv.draw(w, ly + 1, lx + 1, lh - 2, lw - 2, rows or [[(" no FTDI JTAG cable found (s rescans)" if not self.scanning else " scanning USB…", C["dim"])]])
        # UART monitor above, JTAG command log below
        jh = 10 if wd >= WIDE else max(5, min(8, rh // 3)); uh = rh - jh
        if self.uart:
            data = bytes(self.uart.data)
            if self.hex: lines = [" ".join(f"{b:02x}" for b in data[i:i + 16]) + "  " + "".join(chr(b) if 32 <= b < 127 else "." for b in data[i:i + 16]) for i in range(max(0, len(data) - 16 * 400), len(data), 16)]
            title = f"UART {self.uart.port} · {self.baud} · rx {len(data)} B · tx {self.uart.sent} B" + (" · HEX" if self.hex else "") + (f"  ✘ {self.uart.err}" if self.uart.err else "")
            if self.hex: textpane(w, ry, rx, uh - 3, rw, lines, title, True, self.scroll, colorize=False)
            else: self.chat(w, ry, rx, uh - 3, rw, title)
            box(w, ry + uh - 3, rx, 3, rw, "send: i to type" if not self.capture else "typing: Enter sends · Esc stops", self.capture)
            put(w, ry + uh - 2, rx + 2, ("› " + self.line + ("█" if self.capture else "")), C["accent"] if self.capture else C["dim"], rw - 4)
        else:
            textpane(w, ry, rx, uh, rw, ["UART closed: select a port under its cable and press o", f"baud {self.baud} (b changes it)",
                                         "'PL UART of <board>' ports are wired to the FPGA"], "UART", False, colorize=False)
        self.log(w, ry + uh, rx, jh, rw, "jtag")

def bubble_text(b):
    """Message bytes as text: printable as is, line ends shown as ↵, other bytes as \\xNN."""
    return "".join("↵" if c == 10 else "" if c == 13 else chr(c) if 32 <= c < 127 else f"\\x{c:02x}" for c in b)
