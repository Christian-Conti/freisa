# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Interactive interface: the tabs, in order. A new tab: a Tab subclass in its own file, added to TABS.
# Module   : __init__.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it
from .home import Home
from .flow import Flow
from .builds import Builds
from .boards import Boards
from .hardware import Hardware
from .tools import Tools

TABS = [Home, Flow, Builds, Boards, Hardware, Tools]  # add a tab here
