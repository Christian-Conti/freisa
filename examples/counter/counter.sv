module counter #(parameter W = 8)(input logic clk, rst, en, output logic [W-1:0] q);
  always_ff @(posedge clk) if (rst) q <= '0; else if (en) q <= q + 1'b1;
endmodule
