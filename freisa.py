#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : FREISA interactive interface: `python freisa.py`. Re-starts itself in the FREISA conda env when needed.
# Module   : freisa.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import os, shutil, subprocess, sys

ENV = os.environ.get("ENV_NAME", "freisa")
if os.environ.get("CONDA_DEFAULT_ENV") != ENV:  # views and tools need the FREISA env
    # exec the env's python directly (not `conda run`: it sits in between, catches Ctrl+C and prints its own errors)
    conda = shutil.which("conda") or os.path.expanduser("~/miniconda3/bin/conda")
    base = subprocess.run([conda, "info", "--base"], capture_output=True, text=True).stdout.strip() if os.path.exists(conda) else ""
    prefix = os.path.join(base, "envs", ENV)
    py = os.path.join(prefix, "bin", "python")
    if os.environ.get("FREISA_REEXEC") or not os.path.exists(py):
        sys.exit(f"FREISA conda env '{ENV}' not found: run `make install` first")
    os.environ.update(FREISA_REEXEC="1", CONDA_DEFAULT_ENV=ENV, CONDA_PREFIX=prefix,
                      PATH=os.path.join(prefix, "bin") + os.pathsep + os.environ.get("PATH", ""))
    os.execv(py, [py, *sys.argv])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freisa import tui
tui.main()
