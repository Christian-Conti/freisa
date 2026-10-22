# ZCU104: 300 MHz user clock (CLK_300_P/N), PL LED 0. Pins from XilinxBoardStore zcu104 1.1
set_property PACKAGE_PIN AH18 [get_ports clk_p]
set_property PACKAGE_PIN AH17 [get_ports clk_n]
set_property IOSTANDARD DIFF_SSTL12 [get_ports {clk_p clk_n}]
create_clock -period 3.333 -name clk_p [get_ports clk_p]
set_property PACKAGE_PIN D5 [get_ports led]
set_property IOSTANDARD LVCMOS33 [get_ports led]
