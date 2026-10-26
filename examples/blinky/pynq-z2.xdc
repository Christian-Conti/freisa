# Copyright 2026 FREISA contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
#
# Info     : Pin and IO constraints of the blinky example.
# Module   : pynq-z2.xdc
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

set_property LOC H16 [get_ports clk]
set_property IOSTANDARD LVCMOS33 [get_ports clk]
set_property LOC R14 [get_ports led]
set_property IOSTANDARD LVCMOS33 [get_ports led]
