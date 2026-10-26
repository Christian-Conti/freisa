# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive interface (`python freisa.py`): a curses application with one tab per activity.
#            Layout: data.py (repository), draw.py (drawing, popups), jobs.py (background commands, UART),
#            tabs/ (one file per tab), app.py (the application).
# Module   : __init__.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
from .app import main
