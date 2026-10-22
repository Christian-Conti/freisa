// Copyright 2026 FREISA contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
//
// Info     : Enabled up-counter with synchronous reset.
// Module   : counter
// Author   : Christian Conti
// Contact  : christian.conti@mail.it

module counter #(parameter W = 8)(input logic clk, rst, en, output logic [W-1:0] q);
  always_ff @(posedge clk) if (rst) q <= '0; else if (en) q <= q + 1'b1;
endmodule
