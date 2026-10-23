# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Terminal styling shared by every FREISA message: colors only on a terminal, never in files or with NO_COLOR.
# Module   : term.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import os, re, sys

_ON = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

def _c(code):
    return (lambda s: f"\033[{code}m{s}\033[0m") if _ON else (lambda s: str(s))

orange = _c("38;2;255;165;0")   # FREISA accent (same as the progress bar)
bold   = _c("1")
dim    = _c("2")
green  = _c("32")
red    = _c("31")
yellow = _c("33")
cyan   = _c("36")

OK, FAIL, WARN, ARROW, DOT = (green("✔"), red("✘"), yellow("!"), orange("▶"), dim("·")) if _ON else ("ok", "FAIL", "!", ">>", "-")

def plain(s):
    """Text without color codes (for log files)."""
    return _ANSI.sub("", str(s))

def error(msg):
    """Message for SystemExit: red title line, rest unchanged."""
    first, _, rest = str(msg).partition("\n")
    return f"{FAIL} {red(first)}" + (f"\n{rest}" if rest else "")

def note(msg):
    return f"{WARN} {yellow(msg)}"

def banner(title, sub=""):
    line = "─" * max(len(plain(title)), len(plain(sub))) if _ON else "=" * 60
    return "\n".join([orange(line), bold(orange(title)) + (f"\n{dim(sub)}" if sub else ""), orange(line)])
