"""Live monitor: progress bar over stages, elapsed time, CPU/RSS of the tools being run, last log line, per-step summary.
On a TTY it redraws one status line every second; otherwise it prints a plain line every 30 s (make > file, CI)."""
import os, sys, threading, time

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
        self.stages, self.ctx, self.tty = stages, ctx, sys.stdout.isatty()
        self.root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.t0 = time.time(); self.done = 0; self.cur = None; self.t_stage = self.t0
        self.peak_rss = 0; self.cpu_sum = 0.0; self.cpu_n = 0
        self.stop = threading.Event(); self.out = open(logfile, "a")
        self.proc = psutil.Process() if psutil else None
        if self.proc: self.proc.cpu_percent(None)

    def say(self, msg):
        """Permanent line (clears the status line first), also appended to flow.log."""
        for base in (str(self.root) + os.sep, os.getcwd() + os.sep):  # print paths relative to the flow dir / cwd
            msg = msg.replace(base, "")
        if self.tty: sys.stdout.write("\r\033[K")
        print(msg, flush=True); self.out.write(msg + "\n"); self.out.flush()

    def _res(self):
        if not self.proc: return 0.0, 0
        try:
            cache = self.__dict__.setdefault("_cache", {})  # cpu_percent needs the same object across ticks
            procs = [cache.setdefault(p.pid, p) for p in [self.proc] + self.proc.children(recursive=True)]
            cpu = sum(p.cpu_percent(None) for p in procs if p.is_running())
            rss = sum(p.memory_info().rss for p in procs if p.is_running())
        except psutil.Error:
            return 0.0, 0
        self.peak_rss = max(self.peak_rss, rss); self.cpu_sum += cpu; self.cpu_n += 1
        return cpu, rss

    def _last_line(self):
        log = getattr(self.ctx, "cur_log", None)
        try:
            with open(log, "rb") as f:
                f.seek(0, 2); f.seek(max(0, f.tell() - 400))
                lines = [l for l in f.read().decode(errors="replace").splitlines() if l.strip()]
            return lines[-1].strip() if lines else ""
        except (OSError, TypeError):
            return ""

    def _render(self):
        cpu, rss = self._res()
        n = len(self.stages); w = 20; fill = int(w * (self.done + 0.5) / n) if self.cur else int(w * self.done / n)
        bar = "█" * fill + "░" * (w - fill)
        line = (f"[{bar}] {self.done}/{n} {self.cur or '-':8} step {_fmt(time.time() - self.t_stage)} total {_fmt(time.time() - self.t0)}"
                f" | cpu {cpu:5.0f}% mem {_gb(rss)}")
        if self.tty:
            cols = os.get_terminal_size().columns if sys.stdout.isatty() else 120
            tail = self._last_line()
            sys.stdout.write("\r\033[K" + (line + " | " + tail)[:cols - 1]); sys.stdout.flush()
        else:
            self.say(line + " | " + self._last_line()[:100])

    def _loop(self):
        tick = 0
        while not self.stop.wait(1):
            tick += 1
            if not self.cur: continue
            if self.tty or tick % 30 == 0: self._render()
            else: self._res()  # keep sampling for the step summary

    def start(self):
        self.say(f"== {self.ctx.target.get('part')}  stages: {' > '.join(self.stages)}")
        threading.Thread(target=self._loop, daemon=True).start()

    def begin(self, stage, backend):
        self.cur, self.t_stage, self.peak_rss, self.cpu_sum, self.cpu_n = stage, time.time(), 0, 0.0, 0
        self.ctx.cur_log = None; self.say(f">> {stage}: {backend}")

    def end(self, stage, extra=""):
        dt = time.time() - self.t_stage; self.done += 1
        avg = self.cpu_sum / self.cpu_n if self.cpu_n else 0
        self.say(f"   {stage} done in {_fmt(dt)} | avg cpu {avg:.0f}% | peak mem {_gb(self.peak_rss)}" + (f" | {extra}" if extra else ""))
        log = getattr(self.ctx, "cur_log", None)
        if log and os.path.exists(log):
            for l in [l for l in open(log, errors="replace").read().splitlines() if l.strip()][-3:]:
                self.say(f"   | {l.strip()[:150]}")
        self.cur = None

    def finish(self, ok=True):
        self.stop.set()
        self.say(f"== {'finished' if ok else 'FAILED'} in {_fmt(time.time() - self.t0)}")
