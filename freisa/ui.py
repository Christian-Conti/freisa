"""Live monitor, On a TTY it refreshes the progress bar every second; otherwise it prints a plain line every 30 s
(make > file, CI).
"""
import os
import sys
import threading
import time

from tqdm import tqdm

try:
    import psutil
except ImportError:  # resources are then simply not shown
    psutil = None


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

        self.stop = threading.Event()
        self.thread = None
        self.finished = False
        self.out = open(logfile, "a")

        self.proc = psutil.Process() if psutil else None
        if self.proc:
            self.proc.cpu_percent(None)

        self.pbar = tqdm(
            total=len(self.stages),
            desc="Stages",
            unit="stage",
            dynamic_ncols=True,
            file=sys.stdout,
            disable=not self.tty,
            leave=True,
            ascii="▖▘▝▗▚▞█",   #░▖▘▝▗▚▞█
            colour="magenta"
        )

    def say(self, msg):
        """Permanent line (preserves the progress bar), also appended to flow.log."""
        for base in (str(self.root) + os.sep, os.getcwd() + os.sep):
            msg = msg.replace(base, "")

        if self.tty and not self.finished:
            self.pbar.write(msg)
        else:
            print(msg, flush=True)

        self.out.write(msg + "\n")
        self.out.flush()

    def _res(self):
        if not self.proc:
            return 0.0, 0

        try:
            cache = self.__dict__.setdefault("_cache", {})
            procs = [
                cache.setdefault(p.pid, p)
                for p in [self.proc] + self.proc.children(recursive=True)
            ]

            cpu = sum(p.cpu_percent(None) for p in procs if p.is_running())
            rss = sum(p.memory_info().rss for p in procs if p.is_running())

        except psutil.Error:
            return 0.0, 0

        self.peak_rss = max(self.peak_rss, rss)
        self.cpu_sum += cpu
        self.cpu_n += 1

        return cpu, rss

    def _last_line(self):
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

    def _render(self):
        cpu, rss = self._res()

        elapsed = _fmt(time.time() - self.t0)
        stage_elapsed = _fmt(time.time() - self.t_stage)
        tail = self._last_line()

        postfix = (
            f"step {stage_elapsed} | total {elapsed} | "
            f"CPU {cpu:.0f}% | MEM {_gb(rss)}"
        )

        if tail:
            postfix += f" | {tail[-100:]}"

        if self.tty:
            self.pbar.set_description_str(self.cur or "Waiting", refresh=False)
            self.pbar.set_postfix_str(postfix, refresh=False)
            self.pbar.refresh()

        else:
            n = len(self.stages)
            self.say(
                f"{self.done}/{n} {self.cur or '-'} "
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
                self._res()  # keep sampling for the step summary

    def start(self):
        self.say(
            f"== {self.ctx.target.get('part')}  "
            f"stages: {' > '.join(self.stages)}"
        )

        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def begin(self, stage, backend):
        self.cur = stage
        self.t_stage = time.time()
        self.peak_rss = 0
        self.cpu_sum = 0.0
        self.cpu_n = 0

        self.backend = backend
        self.ctx.cur_log = None

        self.pbar.set_description_str(stage, refresh=False)
        self.pbar.set_postfix_str("", refresh=False)
        if self.tty:
            self.pbar.refresh()

        self.say(f">> {stage}: {backend}")

    def end(self, stage, extra="", rep=None):
        dt = time.time() - self.t_stage
        self.done += 1

        avg = self.cpu_sum / self.cpu_n if self.cpu_n else 0

        self.cur = None
        self.pbar.set_description_str(
            "Complete" if self.done == len(self.stages) else "Waiting",
            refresh=False,
        )
        self.pbar.set_postfix_str("", refresh=False)
        self.pbar.update(1)

        self.say(
            f"   {stage} done in {_fmt(dt)} | "
            f"avg cpu {avg:.0f}% | peak mem {_gb(self.peak_rss)}"
            + (f" | {extra}" if extra else "")
        )

        log = getattr(self.ctx, "cur_log", None)
        if log and os.path.exists(log):
            try:
                with open(log, errors="replace") as f:
                    lines = [
                        line.strip()
                        for line in f
                        if line.strip()
                    ]

                for line in lines[-3:]:
                    self.say(f"   | {line[:150]}")

            except OSError:
                pass

        if rep:
            rep.stage(
                stage,
                self.backend,
                dt,
                avg,
                self.peak_rss / 2**30,
                extra.replace("score ", "") or None,
            )

    def finish(self, ok=True):
        self.stop.set()

        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()

        self.pbar.close()
        self.finished = True

        self.say(
            f"== {'finished' if ok else 'FAILED'} "
            f"in {_fmt(time.time() - self.t0)}"
        )

        self.out.close()