# ZCU106: 300 MHz user SI570 clock, PL LED 0. Pins from XilinxBoardStore zcu106 2.6
set_property PACKAGE_PIN AH12 [get_ports clk_p]
set_property PACKAGE_PIN AJ12 [get_ports clk_n]
set_property IOSTANDARD DIFF_SSTL12 [get_ports {clk_p clk_n}]
create_clock -period 3.333 -name clk_p [get_ports clk_p]
set_property PACKAGE_PIN AL11 [get_ports led]
set_property IOSTANDARD LVCMOS12 [get_ports led]
