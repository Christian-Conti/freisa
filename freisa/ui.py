#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Live monitor: progress, time, CPU/memory of the running tools, last log line, step summaries.
# Module   : ui.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import os
import re
import shutil
import sys
import textwrap
import threading
import time

from tqdm import tqdm

from . import term

try:
    import psutil
except ImportError:  # resources are then simply not shown
    psutil = None


_ORANGE = "\033[38;2;255;165;0m"
_RESET = "\033[0m"
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _fmt(s):
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"


def _gb(b):
    return f"{b / 2**30:.1f}G"


class Monitor:
    def __init__(self, stages, ctx, logfile):
        self.stages, self.ctx = stages, ctx
        self.tty = sys.stdout.isatty()
        self.root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.t0 = time.time()
        self.done = 0
        self.cur = None
        self.t_stage = self.t0
        self.backend = None

        self.peak_rss = 0
        self.cpu_sum = 0.0
        self.cpu_n = 0
        self.last_cpu = 0.0
        self.last_rss = 0

        self.stop = threading.Event()
        self.thread = None
        self.finished = False
        self._display_lock = threading.RLock()
        self.out = open(logfile, "a")

        self.proc = psutil.Process() if psutil else None
        if self.proc:
            self.proc.cpu_percent(None)

        self.digits = max(2, len(str(len(self.stages))))
        self.layout = self._layout_name(self._terminal_width())

        # Reserve a fixed number of terminal rows for the latest log message.
        terminal_height = shutil.get_terminal_size(
            fallback=(80, 24)
        ).lines
        self.log_line_count = min(3, max(1, terminal_height - 4))

        # Main status line. The stage counter is more important than a graphical bar.
        self.pbar = tqdm(
            total=len(self.stages),
            desc="",
            bar_format=self._bar_format(self.layout),
            position=0,
            dynamic_ncols=True,
            file=sys.stdout,
            disable=not self.tty,
            leave=True,
            colour="#FFA500",
        )

        # Independent display rows underneath the status line.
        self.logbars = [
            tqdm(
                total=0,
                desc="",
                bar_format="{desc}",
                position=i + 1,
                dynamic_ncols=True,
                file=sys.stdout,
                disable=not self.tty,
                leave=False,
            )
            for i in range(self.log_line_count)
        ]

        if self.tty:
            self._refresh_display()

    def _terminal_width(self):
        """Return the usable terminal width, leaving the last column unused."""
        return max(
            1,
            shutil.get_terminal_size(fallback=(80, 24)).columns - 1,
        )

    @staticmethod
    def _layout_name(width):
        """Select a stable status layout for the available terminal width."""
        if width >= 130:
            return "wide"
        if width >= 95:
            return "normal"
        if width >= 76:
            return "compact"
        if width >= 42:
            return "narrow"
        if width >= 24:
            return "tiny"
        return "micro"
    
    @staticmethod
    def _bar_format(layout):
        """Show the progress bar only when enough terminal space is available."""
        if layout in ("wide", "normal", "compact"):
            return "{desc}{percentage:3.0f}%|{bar}| {postfix}"

        return "{desc}{postfix}"
    
    def _description(self):
        """Return the current stage name at a fixed width."""
        widths = {
            "wide": 12,
            "normal": 10,
            "compact": 7,
            "narrow": 5,
            "tiny": 3,
        }

        width = widths.get(self.layout, 0)
        if width == 0:
            return ""

        label = str(self.cur or "Waiting")[:width].ljust(width)
        return label + ": "

    def _counter(self):
        """Return the current stage / total stages without colour codes."""
        total = len(self.stages)
        current = min(total, self.done + (1 if self.cur else 0))

        if self.layout in ("tiny", "micro"):
            return f"{current}/{total}"

        return (
            f"{current:0{self.digits}d}/"
            f"{total:0{self.digits}d}"
        )

    def say(self, msg):
        """Print a permanent line without corrupting the live display."""
        for base in (
            str(self.root) + os.sep,
            os.getcwd() + os.sep,
        ):
            msg = msg.replace(base, "")

        if self.tty and not self.finished:
            with self._display_lock:
                self.pbar.write(msg)
                self._render_log_rows()
        else:
            print(msg, flush=True)

        self.out.write(term.plain(msg) + "\n")
        self.out.flush()

    def _res(self):
        if not self.proc:
            self.last_cpu, self.last_rss = 0.0, 0
            return self.last_cpu, self.last_rss

        try:
            cache = self.__dict__.setdefault("_cache", {})
            procs = [
                cache.setdefault(p.pid, p)
                for p in [self.proc] + self.proc.children(recursive=True)
            ]

            cpu = sum(
                p.cpu_percent(None)
                for p in procs
                if p.is_running()
            )
            rss = sum(
                p.memory_info().rss
                for p in procs
                if p.is_running()
            )

        except psutil.Error:
            return self.last_cpu, self.last_rss

        self.last_cpu, self.last_rss = cpu, rss
        self.peak_rss = max(self.peak_rss, rss)
        self.cpu_sum += cpu
        self.cpu_n += 1

        return cpu, rss

    def _last_line(self):
        """Read the last nonempty line from the current stage log."""
        log = getattr(self.ctx, "cur_log", None)

        try:
            with open(log, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 400))

                lines = [
                    line
                    for line in f.read().decode(errors="replace").splitlines()
                    if line.strip()
                ]

            return lines[-1].strip() if lines else ""

        except (OSError, TypeError):
            return ""

    def _tty_postfix(self, cpu, rss, elapsed, stage_elapsed):
        """Format status fields independently of the progress bar."""
        count = self._counter()
        colored_count = f"{_ORANGE}{count}{_RESET}"
        memory = _gb(rss)
        width = self._terminal_width()

        if self.layout in ("wide", "normal"):
            return (
                f"{colored_count} | step {stage_elapsed} | "
                f"total {elapsed} | CPU {cpu:4.0f}% | MEM {memory:>6}"
            )

        if self.layout == "compact":
            return (
                f"{colored_count} | S{stage_elapsed} | T{elapsed} | "
                f"C{cpu:4.0f}% | M{memory:>5}"
            )

        if self.layout == "narrow":
            return (
                f"{colored_count} | {elapsed} | "
                f"C{cpu:3.0f}% | M{memory:>4}"
            )

        if self.layout == "tiny":
            if width >= 30:
                return f"{colored_count} | {elapsed} | C{cpu:3.0f}%"
            return f"{colored_count} | {elapsed}"

        return colored_count
    
    def _render_log_rows(self):
        """Wrap the latest log line into fixed rows below the status line."""
        if not self.tty:
            return

        with self._display_lock:
            width = self._terminal_width()
            tail = self._last_line()

            # Remove ANSI escape sequences and terminal control characters.
            tail = _ANSI_RE.sub("", tail)
            tail = re.sub(r"[\x00-\x1f\x7f]+", " ", tail)
            tail = " ".join(tail.split())

            lines = []

            if tail:
                prefix = "log: " if width >= 10 else ""
                indent = " " * len(prefix)
                wrap_width = max(1, width - len(prefix))

                chunks = textwrap.wrap(
                    tail,
                    width=wrap_width,
                    break_long_words=True,
                    break_on_hyphens=False,
                )

                if chunks:
                    lines = [prefix + chunks[0]]
                    lines.extend(
                        indent + chunk
                        for chunk in chunks[1:]
                    )

            # If the log is longer than the available display, retain its ending.
            if len(lines) > self.log_line_count:
                lines = lines[-self.log_line_count:]

                if self.log_line_count == 1:
                    lines[0] = (
                        "…" + lines[0][-max(0, width - 1):]
                    )[:width]
                else:
                    lines[0] = (
                        "… " + lines[0].lstrip()
                    )[:width]

            # Clear unused rows when the next message is shorter.
            lines = [line[:width] for line in lines]
            lines.extend([""] * (self.log_line_count - len(lines)))

            for bar, line in zip(self.logbars, lines):
                bar.set_description_str(line or " ", refresh=False)

            for bar in self.logbars:
                bar.refresh()

    def _refresh_display(self):
        """Refresh the status line and the independent log rows."""
        if not self.tty:
            return

        with self._display_lock:
            self.layout = self._layout_name(self._terminal_width())
            self.pbar.bar_format = self._bar_format(self.layout)

            elapsed = _fmt(time.time() - self.t0)
            stage_elapsed = _fmt(time.time() - self.t_stage)

            self.pbar.set_description_str(
                self._description(),
                refresh=False,
            )
            self.pbar.set_postfix_str(
                self._tty_postfix(
                    self.last_cpu,
                    self.last_rss,
                    elapsed,
                    stage_elapsed,
                ),
                refresh=False,
            )
            self.pbar.refresh()

            self._render_log_rows()


    def _render(self):
        cpu, rss = self._res()

        elapsed = _fmt(time.time() - self.t0)
        stage_elapsed = _fmt(time.time() - self.t_stage)

        if self.tty:
            self._refresh_display()
        else:
            n = len(self.stages)
            tail = self._last_line()

            self.say(
                f"{self.done + (1 if self.cur else 0)}/{n} "
                f"{self.cur or '-'} "
                f"step {stage_elapsed} total {elapsed} | "
                f"CPU {cpu:.0f}% MEM {_gb(rss)} | {tail[:100]}"
            )

    def _loop(self):
        tick = 0

        while not self.stop.wait(1):
            tick += 1

            if not self.cur:
                continue

            if self.tty or tick % 30 == 0:
                self._render()
            else:
                self._res()  # Keep sampling for the step summary.

    def start(self):
        self.say(term.banner(
            f"FREISA  {self.ctx.cfg.get('top', '')} → {self.ctx.target.get('part')}",
            "  " + f" {term.DOT} ".join(self.stages),
        ))

        self._refresh_display()

        self.thread = threading.Thread(
            target=self._loop,
            daemon=True,
        )
        self.thread.start()

    def begin(self, stage, backend):
        with self._display_lock:
            self.cur = stage
            self.t_stage = time.time()
            self.peak_rss = 0
            self.cpu_sum = 0.0
            self.cpu_n = 0

            self.backend = backend
            self.ctx.cur_log = None

            self._refresh_display()

        self.say(f"{term.ARROW} {term.bold(stage.ljust(8))} {term.cyan(backend)}")

    def end(self, stage, extra="", rep=None):
        with self._display_lock:
            dt = time.time() - self.t_stage
            avg = self.cpu_sum / self.cpu_n if self.cpu_n else 0
            peak_rss = self.peak_rss

            self.done += 1
            self.cur = None

            # Advance the stage counter immediately.
            self.pbar.update(1)
            self._refresh_display()

        self.say(
            f"  {term.OK} {stage} {term.dim('done in')} {_fmt(dt)}  "
            + term.dim(f"cpu {avg:.0f}%  mem {_gb(peak_rss)}")
            + (f"  {term.orange(extra)}" if extra else "")
        )

        log = getattr(self.ctx, "cur_log", None)

        if log and os.path.exists(log):
            try:
                with open(log, errors="replace") as f:
                    lines = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("$ ")  # skip the logged command line
                    ]

                for line in lines[-3:]:
                    self.say("    " + term.dim("│ " + line[:150]))

            except OSError:
                pass

        if rep:
            rep.stage(
                stage,
                self.backend,
                dt,
                avg,
                peak_rss / 2**30,
                extra.replace("score ", "") or None,
            )

    def finish(self, ok=True):
        self.stop.set()

        if (
            self.thread
            and self.thread is not threading.current_thread()
        ):
            self.thread.join()

        self._refresh_display()

        # Close lower rows first, then finish the main status line.
        for bar in reversed(self.logbars):
            bar.close()

        self.pbar.close()
        self.finished = True

        t = _fmt(time.time() - self.t0)
        self.say(f"{term.OK} {term.green(term.bold('finished'))} in {t}" if ok else f"{term.FAIL} {term.red(term.bold('FAILED'))} after {t}")

        self.out.close()