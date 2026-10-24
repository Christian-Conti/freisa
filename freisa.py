#!/usr/bin/env python3
# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : FREISA interactive interface: `python freisa.py`. Re-starts itself in the FREISA conda env when needed.
# Module   : freisa.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
import os, shutil, sys

ENV = os.environ.get("ENV_NAME", "freisa")
if os.environ.get("CONDA_DEFAULT_ENV") != ENV:  # views and tools need the FREISA env
    conda = shutil.which("conda") or os.path.expanduser("~/miniconda3/bin/conda")
    if os.environ.get("FREISA_REEXEC") or not os.path.exists(conda):
        sys.exit("FREISA conda env not found: run `make install` first")
    os.environ["FREISA_REEXEC"] = "1"
    os.execv(conda, [conda, "run", "--no-capture-output", "-n", ENV, "python", *sys.argv])

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freisa import tui
tui.main()
