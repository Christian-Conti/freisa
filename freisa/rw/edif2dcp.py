# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Converts an EDIF netlist to a DCP via RapidWright.
# Module   : edif2dcp.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import sys, rapidwright
from com.xilinx.rapidwright.design import Design
from com.xilinx.rapidwright.edif import EDIFTools
edif, part, out = sys.argv[1:4]
n = EDIFTools.readEdifFile(edif)
n.removeUnusedCellsFromAllWorkLibraries()  # yosys declares every Xilinx primitive; keep only the instantiated ones
d = Design(n.getName() or "top", part)
d.setNetlist(n)
d.setAutoIOBuffers(False)
d.writeCheckpoint(out)
print("wrote", out)
