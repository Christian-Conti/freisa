# Copyright 2026 FREISA contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
#
# Info     : Pin and IO constraints of the blinky example on the AUP-ZU3.
# Module   : aup-zu3-8gb.xdc
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

# 100 MHz PL clock (CLK_100_P/N) and white LED 0 (PL_USER_LED[0]); pins from the AUP-ZU3 board files (RealDigital BSP)
set_property PACKAGE_PIN D7 [get_ports clk_p]
set_property PACKAGE_PIN D6 [get_ports clk_n]
set_property IOSTANDARD LVDS [get_ports {clk_p clk_n}]
create_clock -period 10.000 -name clk_p [get_ports clk_p]
set_property PACKAGE_PIN AF5 [get_ports led]
set_property IOSTANDARD LVCMOS12 [get_ports led]
