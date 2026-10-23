#!/usr/bin/env python3
"""Interactive terminal control center for the FREISA FPGA flow."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import signal
import shutil
import sys
from pathlib import Path

from rich.text import Text

try:
    from textual import on
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import (
        Button, Footer, Header, Input, Label, ProgressBar, RichLog, Select, Static,
    )
except ImportError:
    print("FREISA TUI needs Textual. Install it with:\n"
          "  python -m pip install -r freisa_tui/requirements.txt\n", file=sys.stderr)
    raise SystemExit(2)

STAGES = ["sources", "synth", "netlist", "place", "route", "bitgen"]
MAKE_TARGETS = [
    "help", "install", "conda-env", "outdated", "update", "install-boards",
    "check-deps", "fetch", "install-xc7", "install-interchange",
    "install-prjuray", "install-dreamplace", "upload", "check", "uart-test",
    "doctor", "flow", "synth", "uninstall", "clean",
]
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def find_root() -> Path:
    """Find the project root from cwd or this script's location."""
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    for start in starts:
        for candidate in (start, *start.parents):
            if (candidate / "Makefile").is_file() and (candidate / "flow.py").is_file():
                return candidate
    raise FileNotFoundError(
        "Could not find FREISA project root (expected Makefile and flow.py). "
        "Run this command from inside the FREISA checkout."
    )


def choices(folder: Path, suffixes: tuple[str, ...], *, recursive: bool = False) -> list[str]:
    """Return config names relative to their folder, preserving nested paths."""
    if not folder.is_dir():
        return []
    paths = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        p.relative_to(folder).with_suffix("").as_posix()
        for p in paths
        if p.is_file() and p.suffix.lower() in suffixes
    )


class FreisaApp(App):
    TITLE = "FREISA • FPGA Flow Control"
    SUB_TITLE = "Interactive terminal workspace"

    CSS = """
    Screen { background: #10141d; color: #e6edf3; }
    Header { background: #202a3a; color: #ffb454; }
    Footer { background: #202a3a; }
    #banner { height: 5; border: round #ff9f43; padding: 1 2; margin: 1 1 0 1; background: #171e2b; }
    #nav { height: 3; margin: 1 1 0 1; }
    #body { height: 1fr; margin: 0 1 1 1; }
    .panel { border: round #34445c; padding: 1; margin: 0 1 0 0; }
    .heading { color: #ffb454; text-style: bold; margin-bottom: 1; }
    #left { width: 38%; }
    #right { width: 1fr; }
    #status { height: 2; color: #7ee787; padding: 0 1; }
    #stage-heading { height: 1; color: #ffb454; text-style: bold; margin: 0 1; }
    #stage-view { height: 2; padding: 0 1; color: #c9d1d9; }
    #progress { height: 1; margin: 0 1 1 1; }
    #metrics { height: 2; padding: 0 1; color: #9fb7d7; }
    #log { height: 1fr; border: round #34445c; background: #0b0f16; }
    .field { margin-bottom: 1; }
    Select, Input { margin-bottom: 1; }
    Button { margin: 0 1 1 0; }
    Button.primary { background: #d97706; color: #111827; text-style: bold; }
    Button.success { background: #238636; }
    Button.danger { background: #8b2635; }
    #actions { height: auto; }
    #hint { color: #9aa9bd; height: auto; margin-top: 1; }
    .muted { color: #9aa9bd; }
    """
    BINDINGS = [
        ("ctrl+r", "run_flow", "Run flow"),
        ("ctrl+d", "doctor", "Doctor"),
        ("ctrl+l", "clear_log", "Clear log"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.root = find_root()
        self.running = False
        self.current_process: asyncio.subprocess.Process | None = None
        self.stage_queue: list[str] = []
        self.stage_done: set[str] = set()
        self.stage_failed: set[str] = set()
        self.stage_current: str | None = None
        self.stage_backend: str | None = None
        self.stage_metrics: dict[str, dict[str, object]] = {}
        self.current_cpu: float | None = None
        self.current_rss: int | None = None
        self.current_peak_rss: int | None = None
        self.elapsed_s = 0.0
        self.stage_elapsed_s = 0.0
        self.monitor_events_seen = False
        self.event_task: asyncio.Task | None = None
        self.event_stop: asyncio.Event | None = None
        self.log_path = self.root / "build" / "freisa-tui.log"
        self.event_path = self.root / "build" / "freisa-tui-events.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.design_names = choices(self.root / "designs", (".yml", ".yaml"), recursive=True)
        self.target_names = choices(self.root / "targets", (".yml", ".yaml"))
        if not self.design_names:
            self.design_names = ["blinky"]
        if not self.target_names:
            self.target_names = ["xc7z020"]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "[bold #ffb454]╭─ FREISA ─ FPGA FLOW CONTROL ─────────────────────────────────────────╮[/]\n"
            "[bold]│[/]  [#7ee787]●[/] Project detected     [bold]Build • Install • Diagnose • Logs[/]\n"
            f"[bold]│[/]  Root: [#9aa9bd]{self.root}[/]\n"
            "[bold #ffb454]╰──────────────────────────────────────────────────────────────────────╯[/]",
            id="banner",
        )
        with Horizontal(id="nav"):
            yield Button("Dashboard", id="nav-dashboard", variant="primary")
            yield Button("Build Flow", id="nav-build")
            yield Button("Tools / Doctor", id="nav-tools")
            yield Button("Install", id="nav-install")
            yield Button("Logs", id="nav-logs")
        with Horizontal(id="body"):
            with Vertical(id="left", classes="panel"):
                yield Label("BUILD CONFIGURATION", classes="heading")
                yield Label("Design", classes="field")
                default_design = next((d for d in self.design_names if d == "blinky" or d.endswith("/blinky")), self.design_names[0])
                yield Select([(x, x) for x in self.design_names], value=default_design, id="design", allow_blank=False)
                yield Label("FPGA target", classes="field")
                default_target = "xc7z020" if "xc7z020" in self.target_names else self.target_names[0]
                yield Select([(x, x) for x in self.target_names], value=default_target, id="target", allow_blank=False)
                yield Label("From stage")
                yield Select([(x, x) for x in STAGES], value="sources", id="from-stage", allow_blank=False)
                yield Label("To stage")
                yield Select([(x, x) for x in STAGES], value="bitgen", id="to-stage", allow_blank=False)
                yield Label("Extra make variables (optional)")
                yield Input(placeholder="e.g. ENV_NAME=freisa", id="extra-vars")
                with Horizontal(id="actions"):
                    yield Button("▶ Run flow", id="run-flow", classes="primary")
                    yield Button("✓ Check", id="check")
                yield Button("Run synthesis only", id="synth")
                yield Label("GENERAL MAKE TARGET", classes="heading")
                yield Select([(x, x) for x in MAKE_TARGETS], value="doctor", id="make-target", allow_blank=False)
                yield Button("▶ Run selected target", id="run-make-target")
                yield Label("INSTALL / MAINTENANCE", classes="heading")
                with Horizontal():
                    yield Button("Install all", id="install-all")
                    yield Button("Clean build", id="clean", classes="danger")
                yield Button("Stop current command", id="stop", disabled=True)
                yield Static("Keys: Ctrl+R run • Ctrl+D doctor • Ctrl+L clear • Q quit", id="hint")
            with Vertical(id="right"):
                yield Static("● READY  |  Waiting for a command", id="status")
                yield Static("STAGE PROGRESS", id="stage-heading")
                yield Static("No build running. Select a stage range and launch a flow.", id="stage-view")
                yield ProgressBar(total=6, show_eta=False, id="progress")
                yield Static("CPU: —    RAM: —    Stage time: —    Total time: —", id="metrics")
                yield RichLog(id="log", wrap=True, highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "FREISA • FPGA Flow Control"
        log = self.query_one("#log", RichLog)
        log.write("[bold #ffb454]FREISA terminal workspace[/]")
        log.write(f"[dim]Project root: {self.root}[/]")
        log.write("[#7ee787]Ready.[/] Select a design and target, then run a command.")
        self._log_file("FREISA TUI session started")
        self._update_metrics()

    def _log_file(self, message: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(ANSI_RE.sub("", message) + "\n")

    def _log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)
        self._log_file(message)

    def _log_external(self, message: str) -> None:
        """Write tool output as literal text so tool strings cannot become Rich markup."""
        self.query_one("#log", RichLog).write(Text(message))
        self._log_file(message)

    def _set_status(self, message: str, running: bool = False) -> None:
        self.query_one("#status", Static).update(message)
        self.query_one("#stop", Button).disabled = not running
        self.query_one("#run-flow", Button).disabled = running
        self.query_one("#check", Button).disabled = running
        self.query_one("#install-all", Button).disabled = running
        self.query_one("#run-make-target", Button).disabled = running
        self.query_one("#synth", Button).disabled = running
        self.query_one("#clean", Button).disabled = running
        self.running = running

    def _prepare_stages(self, stages: list[str]) -> None:
        self.stage_queue = list(stages)
        self.stage_done = set()
        self.stage_failed = set()
        self.stage_current = None
        self.stage_backend = None
        self.stage_metrics = {}
        self.current_cpu = None
        self.current_rss = None
        self.current_peak_rss = None
        self.elapsed_s = 0.0
        self.stage_elapsed_s = 0.0
        self.monitor_events_seen = False
        total = max(1, len(self.stage_queue))
        self.query_one("#progress", ProgressBar).update(total=total, progress=0)
        self._update_stage_view()
        self._update_metrics()

    def _update_stage_view(self) -> None:
        queue = self.stage_queue
        if not queue:
            self.query_one("#stage-view", Static).update("No stage-specific progress for this command.")
            self.query_one("#progress", ProgressBar).update(total=1, progress=0)
            return
        labels = []
        for stage in queue:
            if stage in self.stage_failed:
                icon, color = "✗", "#ff6b6b"
            elif stage in self.stage_done:
                icon, color = "✓", "#7ee787"
            elif stage == self.stage_current:
                icon, color = "▶", "#ffb454"
            else:
                icon, color = "·", "#7d8590"
            labels.append(f"[{color}]{icon} {stage}[/]")
        self.query_one("#stage-view", Static).update("   ".join(labels))
        self.query_one("#progress", ProgressBar).update(
            total=max(1, len(queue)), progress=len(self.stage_done)
        )

    def _observe_line(self, line: str) -> None:
        """Fallback parser for the existing monitor output when the event hook is absent."""
        stages = "|".join(re.escape(stage) for stage in STAGES)
        if not self.monitor_events_seen:
            begin = re.search(rf"(?:▶|→|->|>>)\s*({stages})\b", line)
            if begin and begin.group(1) in self.stage_queue:
                self.stage_current = begin.group(1)
                self._update_stage_view()
            done = re.search(rf"\b({stages})\s+done in\b", line)
            if done and done.group(1) in self.stage_queue:
                stage = done.group(1)
                self.stage_done.add(stage)
                if self.stage_current == stage:
                    self.stage_current = None
                self._update_stage_view()

        # The existing compact/wide tqdm status line carries live CPU/RAM and elapsed times.
        cpu = re.search(r"\bCPU\s*(\d+(?:\.\d+)?)%", line, re.I)
        memory = re.search(r"\bMEM\s*([0-9]+(?:\.[0-9]+)?)G", line, re.I)
        elapsed = re.search(r"\btotal\s+(\d{2}:\d{2}:\d{2})", line, re.I)
        stage_elapsed = re.search(r"\bstep\s+(\d{2}:\d{2}:\d{2})", line, re.I)
        if cpu and not self.monitor_events_seen:
            self.current_cpu = float(cpu.group(1))
        if memory and not self.monitor_events_seen:
            self.current_rss = int(float(memory.group(1)) * (1024 ** 3))
        if elapsed and not self.monitor_events_seen:
            try:
                h, m, sec = map(int, elapsed.group(1).split(":"))
                self.elapsed_s = h * 3600 + m * 60 + sec
            except ValueError:
                pass
        if stage_elapsed and not self.monitor_events_seen:
            try:
                h, m, sec = map(int, stage_elapsed.group(1).split(":"))
                self.stage_elapsed_s = h * 3600 + m * 60 + sec
            except ValueError:
                pass
        self._update_metrics()

    @staticmethod
    def _duration(seconds: float | int | None) -> str:
        if seconds is None:
            return "—"
        value = max(0, int(seconds))
        return f"{value // 3600:02d}:{value % 3600 // 60:02d}:{value % 60:02d}"

    @staticmethod
    def _memory_gib(nbytes: int | None) -> str:
        if nbytes is None:
            return "—"
        return f"{nbytes / (1024 ** 3):.1f} GiB"

    def _update_metrics(self) -> None:
        cpu = f"{self.current_cpu:.0f}%" if self.current_cpu is not None else "—"
        rss = self._memory_gib(self.current_rss)
        peak = self._memory_gib(self.current_peak_rss)
        text = (
            f"CPU: {cpu}    RAM: {rss}    Peak: {peak}    "
            f"Stage: {self._duration(self.stage_elapsed_s)}    "
            f"Total: {self._duration(self.elapsed_s)}"
        )
        try:
            self.query_one("#metrics", Static).update(text)
        except Exception:
            pass

    def _handle_event(self, event: dict[str, object]) -> None:
        """Handle structured monitor events emitted by freisa.ui.Monitor."""
        kind = str(event.get("event", ""))
        if kind in {"monitor_started", "stage_started", "stage_finished", "sample", "monitor_finished"}:
            self.monitor_events_seen = True

        if kind == "monitor_started":
            stages = event.get("stages")
            if isinstance(stages, list):
                self.stage_queue = [str(s) for s in stages]
                self.stage_done = set()
                self.stage_failed = set()
                self.stage_current = None
                self.stage_backend = None
                self.stage_metrics = {}
                self.query_one("#progress", ProgressBar).update(
                    total=max(1, len(self.stage_queue)), progress=0
                )
                self._update_stage_view()
            design = event.get("design", "")
            target = event.get("target", "")
            self._log(f"[bold #ffb454]Flow monitor connected[/] · {design} · {target}")

        elif kind == "stage_started":
            stage = str(event.get("stage", ""))
            self.stage_current = stage
            self.stage_backend = str(event.get("backend", ""))
            self.stage_elapsed_s = 0.0
            self._update_stage_view()
            self._log(f"[bold #ffb454]▶ {stage}[/]  [dim]{self.stage_backend}[/]")

        elif kind == "stage_finished":
            stage = str(event.get("stage", ""))
            self.stage_done.add(stage)
            self.stage_metrics[stage] = event
            if self.stage_current == stage:
                self.stage_current = None
                self.stage_backend = None
            seconds = float(event.get("seconds", 0) or 0)
            avg_cpu = event.get("avg_cpu_percent")
            peak = event.get("peak_rss_bytes")
            cpu_text = f"{float(avg_cpu):.0f}%" if avg_cpu is not None else "—"
            peak_text = self._memory_gib(int(peak)) if peak is not None else "—"
            self._log(
                f"[bold #7ee787]✓ {stage} complete[/]  "
                f"[dim]{self._duration(seconds)} · avg CPU {cpu_text} · peak RAM {peak_text}[/]"
            )
            self._update_stage_view()

        elif kind == "sample":
            cpu = event.get("cpu_percent")
            rss = event.get("rss_bytes")
            peak = event.get("peak_rss_bytes")
            self.current_cpu = float(cpu) if cpu is not None else None
            self.current_rss = int(rss) if rss is not None else None
            self.current_peak_rss = int(peak) if peak is not None else None
            self.elapsed_s = float(event.get("elapsed_s", self.elapsed_s) or 0)
            self.stage_elapsed_s = float(event.get("stage_elapsed_s", self.stage_elapsed_s) or 0)
            self._update_metrics()

        elif kind == "monitor_finished":
            self.elapsed_s = float(event.get("elapsed_s", self.elapsed_s) or 0)
            if event.get("success") is False and self.stage_current:
                self.stage_failed.add(self.stage_current)
                self.stage_current = None
                self.stage_backend = None
                self._update_stage_view()
            self._update_metrics()

    async def _poll_monitor_events(self, stop_event: asyncio.Event) -> None:
        """Tail the monitor's JSONL side channel without blocking the UI event loop."""
        offset = 0
        while not stop_event.is_set():
            offset = self._read_monitor_events(offset)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.2)
            except asyncio.TimeoutError:
                pass
        self._read_monitor_events(offset)

    def _read_monitor_events(self, offset: int) -> int:
        try:
            with self.event_path.open("rb") as stream:
                stream.seek(offset)
                while True:
                    line_start = stream.tell()
                    line = stream.readline()
                    if not line:
                        break
                    if not line.endswith(b"\n"):
                        # A writer may still be flushing this event. Retry from its start.
                        offset = line_start
                        break
                    offset = stream.tell()
                    try:
                        event = json.loads(line.decode("utf-8", errors="replace"))
                        if isinstance(event, dict):
                            self._handle_event(event)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
        except OSError:
            pass
        return offset

    def _config(self) -> tuple[str, str, str, str, list[str]]:
        design = str(self.query_one("#design", Select).value)
        target = str(self.query_one("#target", Select).value)
        start = str(self.query_one("#from-stage", Select).value)
        end = str(self.query_one("#to-stage", Select).value)
        extra_text = self.query_one("#extra-vars", Input).value.strip()
        extra = shlex.split(extra_text) if extra_text else []
        return design, target, start, end, extra

    async def run_command(self, args: list[str], title: str) -> None:
        if self.running:
            self._log("[yellow]A command is already running.[/]")
            return
        command = ["make", *args]
        self._log("")
        self._log(f"[bold #ffb454]╭─ {title}[/]")
        self._log("[dim]$ " + " ".join(command) + "[/]")
        self._set_status(f"[yellow]● RUNNING[/]  {title}", True)
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        # Optional structured events come from the small monitor hook in freisa/ui.py.
        # The UI still works without that hook by parsing the existing monitor output.
        self.event_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_path.write_text("", encoding="utf-8")
        env["FREISA_TUI_EVENTS"] = str(self.event_path)
        self.event_stop = asyncio.Event()
        self.event_task = asyncio.create_task(self._poll_monitor_events(self.event_stop))
        try:
            # GNU script gives the Makefile/Python monitor a pseudo-TTY, so its
            # existing tqdm interface remains enabled even though Textual captures it.
            script = shutil.which("script")
            if script:
                self.current_process = await asyncio.create_subprocess_exec(
                    script, "-q", "-e", "-f", "-c", shlex.join(command), "/dev/null",
                    cwd=str(self.root), env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )
            else:
                self._log("[yellow]Note: 'script' was not found; running without pseudo-TTY progress.[/]")
                self.current_process = await asyncio.create_subprocess_exec(
                    *command, cwd=str(self.root), env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )
            assert self.current_process.stdout is not None
            pending = ""
            last_progress_log = 0.0
            while True:
                raw = await self.current_process.stdout.read(4096)
                if not raw:
                    break
                pending += raw.decode("utf-8", errors="replace")
                # PTY-based progress often uses CR instead of LF. Split on both,
                # coalescing tqdm refreshes to avoid flooding the log panel.
                while True:
                    matches = [i for i in (pending.find("\n"), pending.find("\r")) if i >= 0]
                    if not matches:
                        break
                    pos = min(matches)
                    raw_line, pending = pending[:pos], pending[pos + 1:]
                    safe = ANSI_RE.sub("", raw_line).replace("\x00", "").strip()
                    if not safe:
                        continue
                    self._observe_line(safe)
                    is_progress = "|" in safe and "%" in safe
                    now = asyncio.get_running_loop().time()
                    if not is_progress or now - last_progress_log >= 1.0:
                        self._log_external(safe)
                        if is_progress:
                            last_progress_log = now
            if pending.strip():
                safe = ANSI_RE.sub("", pending).replace("\x00", "").strip()
                if safe:
                    self._observe_line(safe)
                    self._log_external(safe)
            code = await self.current_process.wait()
            if code == 0:
                self._log(f"[bold #7ee787]✓ {title} completed successfully (exit {code})[/]")
                self._set_status(f"[#7ee787]● SUCCESS[/]  {title}", False)
            else:
                self._log(f"[bold #ff6b6b]✗ {title} failed (exit {code})[/]")
                self._set_status(f"[#ff6b6b]● FAILED[/]  {title} (exit {code})", False)
        except FileNotFoundError:
            self._log("[bold red]Could not execute make. Is GNU Make installed and on PATH?[/]")
            self._set_status("[red]● ERROR[/]  make not found", False)
        except asyncio.CancelledError:
            self._log("[yellow]Command task cancelled.[/]")
            self._set_status("[yellow]● STOPPED[/]", False)
            raise
        finally:
            if self.event_stop is not None:
                self.event_stop.set()
            if self.event_task is not None:
                try:
                    await asyncio.wait_for(self.event_task, timeout=1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self.event_task.cancel()
                self.event_task = None
                self.event_stop = None
            self.current_process = None
            self.running = False
            self.query_one("#stop", Button).disabled = True
            self.query_one("#run-flow", Button).disabled = False
            self.query_one("#check", Button).disabled = False
            self.query_one("#install-all", Button).disabled = False

    def action_run_flow(self) -> None:
        self._start_flow()

    def _start_flow(self) -> None:
        design, target, start, end, extra = self._config()
        if STAGES.index(start) > STAGES.index(end):
            self._log("[bold red]Invalid stage range: FROM must not be after TO.[/]")
            self._set_status("[red]● CONFIGURATION ERROR[/]  Invalid stage range", False)
            return
        self._prepare_stages(STAGES[STAGES.index(start):STAGES.index(end) + 1])
        args = ["flow", f"DESIGN={design}", f"TARGET={target}", f"FROM={start}", f"TO={end}", *extra]
        self.run_worker(self.run_command(args, f"Build flow · {design} / {target}"), exclusive=False, name="make-flow")

    @on(Button.Pressed, "#run-flow")
    def click_run_flow(self) -> None:
        self._start_flow()

    @on(Button.Pressed, "#check")
    def click_check(self) -> None:
        design, target, start, end, extra = self._config()
        self._prepare_stages([])
        self.run_worker(self.run_command(["check", f"DESIGN={design}", f"TARGET={target}", f"FROM={start}", f"TO={end}", *extra], "Check flow"), exclusive=False)

    @on(Button.Pressed, "#synth")
    def click_synth(self) -> None:
        design, target, _, _, extra = self._config()
        self._prepare_stages(["sources", "synth"])
        self.run_worker(self.run_command(["synth", f"DESIGN={design}", f"TARGET={target}", *extra], "Synthesis"), exclusive=False)

    @on(Button.Pressed, "#run-make-target")
    def click_make_target(self) -> None:
        target_name = str(self.query_one("#make-target", Select).value)
        design, board, start, end, extra = self._config()
        if target_name == "uninstall":
            if "CONFIRM_UNINSTALL=YES" not in extra:
                self._log("[bold yellow]Safety check:[/] uninstall deletes install/, third_party/, build/ and the FREISA Conda environment.")
                self._log("To enable it, add [bold]CONFIRM_UNINSTALL=YES[/] to Extra make variables and run the target again.")
                self._set_status("[yellow]● CONFIRMATION REQUIRED[/]  make uninstall", False)
                return
            extra = [item for item in extra if item != "CONFIRM_UNINSTALL=YES"]
        # The target is selected from a fixed allowlist; variable arguments are passed
        # as separate argv items and never evaluated by a shell.
        if target_name == "flow":
            self._start_flow()
            return
        if target_name == "synth":
            self._prepare_stages(["sources", "synth"])
            args = ["synth", f"DESIGN={design}", f"TARGET={board}", *extra]
        elif target_name in {"upload", "uart-test", "doctor", "check"}:
            args = [target_name, f"DESIGN={design}", f"TARGET={board}", *extra]
            self._prepare_stages([])
        else:
            args = [target_name, *extra]
            self._prepare_stages([])
        self.run_worker(self.run_command(args, f"Make target · {target_name}"), exclusive=False)

    @on(Button.Pressed, "#install-all")
    def click_install(self) -> None:
        self._prepare_stages([])
        self.run_worker(self.run_command(["install"], "Install FREISA toolchain"), exclusive=False)

    @on(Button.Pressed, "#clean")
    def click_clean(self) -> None:
        self._prepare_stages([])
        self.run_worker(self.run_command(["clean"], "Clean build outputs"), exclusive=False)

    @on(Button.Pressed, "#stop")
    async def click_stop(self) -> None:
        if self.current_process and self.current_process.returncode is None:
            self._log("[yellow]Sending termination signal to current command…[/]")
            try:
                os.killpg(self.current_process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                self.current_process.terminate()

    @on(Button.Pressed, "#nav-dashboard")
    def nav_dashboard(self) -> None:
        self._set_status("[#7ee787]● READY[/]  Dashboard · configure and launch a flow", self.running)
        self._log("[bold #ffb454]Dashboard[/] — choose design, target and stage range in the left panel.")

    @on(Button.Pressed, "#nav-build")
    def nav_build(self) -> None:
        self._log("[bold #ffb454]Build Flow[/] — set the configuration, then press Run flow or Ctrl+R.")

    @on(Button.Pressed, "#nav-tools")
    def nav_tools(self) -> None:
        design, target, _, _, extra = self._config()
        self._prepare_stages([])
        self.run_worker(self.run_command(["doctor", f"DESIGN={design}", f"TARGET={target}", *extra], "Tool availability / doctor"), exclusive=False)

    @on(Button.Pressed, "#nav-install")
    def nav_install(self) -> None:
        self._log("[bold #ffb454]Install Manager[/]")
        self._log("Install all: make install")
        self._log("Individual targets remain available from the CLI, e.g. make install-xc7, make install-boards, make install-dreamplace.")
        self._log("Use FORCE=1 to rebuild supported toolchains.")

    @on(Button.Pressed, "#nav-logs")
    def nav_logs(self) -> None:
        self._log(f"[bold #ffb454]Session log[/] saved at: {self.log_path}")
        if self.log_path.exists():
            try:
                tail = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
                for line in tail:
                    self.query_one("#log", RichLog).write(line)
            except OSError as exc:
                self._log(f"[red]Cannot read log: {exc}[/]")

    def action_doctor(self) -> None:
        self.nav_tools()

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()
        self._log("Log view cleared.")

    async def action_quit(self) -> None:
        if self.current_process and self.current_process.returncode is None:
            try:
                os.killpg(self.current_process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                self.current_process.terminate()
            try:
                await asyncio.wait_for(self.current_process.wait(), timeout=3)
            except asyncio.TimeoutError:
                try:
                    os.killpg(self.current_process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    self.current_process.kill()
        self.exit()


def main() -> None:
    try:
        FreisaApp().run()
    except FileNotFoundError as exc:
        print(f"FREISA: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
