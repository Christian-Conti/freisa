// Copyright 2026 FREISA contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
//
// Info     : Registered 16-bit ALU with a multiplier mapped to a DSP.
// Module   : alu
// Author   : Christian Conti
// Contact  : christian.conti@mail.it

module alu(input logic clk, input logic [15:0] a, b, input logic [1:0] op, output logic [31:0] y);
  logic [31:0] r;
  always_comb case (op) 0: r = a + b; 1: r = a - b; 2: r = a * b; default: r = {a, b} ^ 32'hA5A5A5A5; endcase
  always_ff @(posedge clk) y <= r;  // multiplier -> DSP
endmodule
