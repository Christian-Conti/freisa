module uart_tx #(parameter DIV = 868)(input clk, input [7:0] data, input start, output reg tx, output busy);
  reg [15:0] cnt = 0; reg [3:0] nb = 0; reg [9:0] sh = 10'h3ff; reg run = 0;
  assign busy = run;
  always @(posedge clk) begin
    if (!run) begin tx <= 1; if (start) begin sh <= {1'b1, data, 1'b0}; run <= 1; cnt <= 0; nb <= 0; end end
    else if (cnt == DIV-1) begin cnt <= 0; tx <= sh[0]; sh <= {1'b1, sh[9:1]}; nb <= nb + 1; if (nb == 10) run <= 0; end
    else cnt <= cnt + 1;
  end
endmodule
