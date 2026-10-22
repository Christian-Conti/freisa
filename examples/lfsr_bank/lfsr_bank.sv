// Copyright 2026 FREISA contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
//
// Info     : Bank of LFSRs seeded from one input.
// Module   : lfsr_bank
// Author   : Christian Conti
// Contact  : christian.conti@mail.it

module lfsr_bank #(parameter N = 64)(input logic clk, rst, input logic [31:0] seed, output logic [31:0] y);
  logic [31:0] s [N];
  logic [31:0] acc;
  for (genvar i = 0; i < N; i++) begin : g
    always_ff @(posedge clk)
      if (rst) s[i] <= seed ^ (32'h9E3779B9 * (i + 1));
      else     s[i] <= {s[i][30:0], s[i][31] ^ s[i][21] ^ s[i][1] ^ s[i][0]} ^ {s[(i + 1) % N][7:0], 24'b0};
  end
  always_comb begin acc = '0; for (int i = 0; i < N; i++) acc ^= s[i]; end
  always_ff @(posedge clk) y <= acc;
endmodule
