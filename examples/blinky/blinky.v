// Copyright 2026 FREISA contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
//
// Info     : Blinks an LED from a free-running counter.
// Module   : blinky
// Author   : Christian Conti
// Contact  : christian.conti@mail.it

module blinky(input clk, output reg led);
  reg [25:0] c = 0;
  always @(posedge clk) begin c <= c + 1; led <= c[25]; end
endmodule
