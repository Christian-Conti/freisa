# Copyright 2026 FREISA contributors
# Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
#
# Info     : Pin and IO constraints of the uart_loopback example on the ZCU106.
# Module   : zcu106.xdc
# Author   : Christian Conti
# Contact  : christian.conti@mail.it

# 300 MHz user SI570 clock, PL UART (uart2_PL_TX/RX), PL LED 0; pins from XilinxBoardStore zcu106 2.6
set_property PACKAGE_PIN AH12 [get_ports clk_p]
set_property PACKAGE_PIN AJ12 [get_ports clk_n]
set_property IOSTANDARD DIFF_SSTL12 [get_ports {clk_p clk_n}]
create_clock -period 3.333 -name clk_p [get_ports clk_p]
set_property PACKAGE_PIN AL17 [get_ports tx]
set_property PACKAGE_PIN AH17 [get_ports rx]
set_property IOSTANDARD LVCMOS12 [get_ports {tx rx}]
set_property PACKAGE_PIN AL11 [get_ports led]
set_property IOSTANDARD LVCMOS12 [get_ports led]
