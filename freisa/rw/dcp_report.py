# Copyright 2026 FREISA contributors
# Apache License, Version 2.0, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0
#
# Info     : Prints a utilization report of a DCP via RapidWright.
# Module   : dcp_report.py
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

import sys, collections, rapidwright
from com.xilinx.rapidwright.design import Design
d = Design.readCheckpoint(sys.argv[1])
cells, sites, placed = collections.Counter(), set(), 0
for c in d.getCells():
    cells[str(c.getType())] += 1
    if c.isPlaced(): placed += 1; sites.add(str(c.getSiteInst().getName()))
nets = [n for n in d.getNets() if not n.isStaticNet() and n.getSource() is not None]
routed = sum(1 for n in nets if n.hasPIPs())
print(f"part            {d.getPartName()}\ncells           {sum(cells.values())}\nplaced cells    {placed}\nsites used      {len(sites)}")
print(f"nets (routable) {len(nets)}\nnets with PIPs  {routed}\n\ncell type usage")
for t, n in cells.most_common(): print(f"  {t:16} {n}")
