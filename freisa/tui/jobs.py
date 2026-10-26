# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive interface: commands running in the background (logs, CPU and memory) and the serial port monitor.
# Module   : jobs.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import collections, curses, os, textwrap, pathlib, re, shutil, signal, subprocess, tempfile, threading, time
import yaml
from .. import term as T
from .data import *

# ------------------------------------------------------------------ background commands
class Job:
    """A command running in the background; its output is kept for the log panes."""
    def __init__(self, cmd, title):
        self.cmd, self.title, self.t0, self.t1, self.rc = [str(c) for c in cmd], title, time.time(), None, None
        self.lines = collections.deque(["$ " + " ".join(self.cmd)], maxlen=5000)
        self.p = subprocess.Popen(self.cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  env={**os.environ, "NO_COLOR": "1", "COLUMNS": "160"}, start_new_session=True)
        threading.Thread(target=self._read, daemon=True).start()
    def _read(self):
        buf = b""
        for chunk in iter(lambda: self.p.stdout.read1(4096), b""):
            *done, buf = (buf + chunk).split(b"\n")
            for l in done:
                s = T.plain(l.rstrip(b"\r").split(b"\r")[-1].decode(errors="replace")).rstrip()  # \r: progress bars, keep the last
                if s: self.lines.append(s)
        self.rc = self.p.wait(); self.t1 = time.time()
        if self.rc == 0 and any(l.startswith("Error") for l in self.lines): self.rc = 1  # openFPGALoader exits 0 on some errors
        self.lines.append(("✔ done" if self.rc == 0 else f"✘ exit code {self.rc}") + f" in {fmt(self.t1 - self.t0)}")
    @property
    def running(self): return self.rc is None
    def elapsed(self): return (self.t1 or time.time()) - self.t0
    def usage(self):
        """CPU % and memory (GB) of the command and every process it started (Vivado, java, ...); keeps the memory peak."""
        try:
            import psutil
            procs = getattr(self, "_procs", {})
            root = psutil.Process(self.p.pid)
            cpu = mem = 0.0
            for q in [root, *root.children(recursive=True)]:
                q = procs.setdefault(q.pid, q)
                try: cpu += q.cpu_percent(None); mem += q.memory_info().rss / 2**30
                except psutil.Error: pass
            self._procs = procs; self.peak = max(getattr(self, "peak", 0.0), mem)
            return cpu, mem
        except Exception: return None
    def kill(self):
        if self.running:
            try: os.killpg(self.p.pid, signal.SIGTERM)
            except ProcessLookupError: pass

class Uart:
    """Serial port monitor: a thread keeps the last 64 KB received, and the conversation: [dir, bytes, time] with dir
    "tx" (sent) or "rx" (received; bytes arriving within 0.3 s of each other form one message)."""
    def __init__(self, port, baud):
        import serial
        self.port, self.baud, self.err = port, baud, None
        self.s = serial.Serial(port, baud, timeout=0.1)
        self.data, self.sent, self.alive, self.chat = bytearray(), 0, True, []
        threading.Thread(target=self._read, daemon=True).start()
    def _read(self):
        while self.alive:
            try: b = self.s.read(4096)
            except Exception as e: self.err = str(e); return
            if b:
                self.data += b; del self.data[:-65536]
                if self.chat and self.chat[-1][0] == "rx" and time.time() - self.chat[-1][2] < 0.3: self.chat[-1][1] += b; self.chat[-1][2] = time.time()
                else: self.chat.append(["rx", bytearray(b), time.time()])
                del self.chat[:-500]
    def send(self, b): self.s.write(b); self.sent += len(b); self.chat.append(["tx", bytearray(b), time.time()])
    def clear(self): self.data.clear(); self.chat.clear()
    def close(self):
        self.alive = False; time.sleep(0.15); self.s.close()
