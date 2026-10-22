module blinky(input clk, output reg led);
  reg [25:0] c = 0;
  always @(posedge clk) begin c <= c + 1; led <= c[25]; end
endmodule
