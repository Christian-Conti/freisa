// Copyright 2026 FREISA contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
//
// Info     : Blinky top for boards with a differential PL clock (ZCU104, ZCU106).
// Module   : blinky_diff.v
// Author   : Christian Conti
// Contact  : christian.conti@mail.it

module blinky_diff(input clk_p, input clk_n, output led);
  wire clk;
  IBUFDS ibufds (.I(clk_p), .IB(clk_n), .O(clk));
  blinky core (.clk(clk), .led(led));
endmodule
