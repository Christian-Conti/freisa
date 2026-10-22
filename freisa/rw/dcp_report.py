"""Utilization/routing report of a checkpoint using RapidWright only (no Vivado): cells by type, site usage, net routing state."""
import sys, collections, rapidwright
from com.xilinx.rapidwright.design import Design
d = Design.readCheckpoint(sys.argv[1])
cells, sites, placed = collections.Counter(), set(), 0
for c in d.getCells():
    cells[c.getType()] += 1
    if c.isPlaced(): placed += 1; sites.add(c.getSiteInst().getName())
nets = [n for n in d.getNets() if not n.isStaticSource() and n.getSource() is not None]
routed = sum(1 for n in nets if n.hasPIPs())
print(f"part            {d.getPartName()}\ncells           {sum(cells.values())}\nplaced cells    {placed}\nsites used      {len(sites)}")
print(f"nets (routable) {len(nets)}\nnets with PIPs  {routed}\n\ncell type usage")
for t, n in cells.most_common(): print(f"  {t:16} {n}")
