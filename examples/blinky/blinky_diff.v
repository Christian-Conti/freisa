// Top for boards whose only PL clock is a differential oscillator (ZCU104, ZCU106).
module blinky_diff(input clk_p, input clk_n, output led);
  wire clk;
  IBUFDS ibufds (.I(clk_p), .IB(clk_n), .O(clk));
  blinky core (.clk(clk), .led(led));
endmodule
