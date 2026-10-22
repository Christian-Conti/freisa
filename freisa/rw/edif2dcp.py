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
