// Copyright 2026 FREISA contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
//
// Info     : UART loopback: the serial line received from the PC is sent back unchanged (any baud rate).
//            rx is synchronised with two flip-flops, then drives tx; the LED shows activity.
// Module   : uart_loopback
// Author   : Christian Conti
// Contact  : christian.conti@mail.it

module uart_loopback(input clk, input rx, output reg tx, output reg led);
  reg rx_s1 = 1'b1, rx_s2 = 1'b1;
  reg [23:0] hold = 0;
  always @(posedge clk) begin
    rx_s1 <= rx;                // two-stage synchroniser: rx comes from another clock domain (the PC)
    rx_s2 <= rx_s1;
    tx    <= rx_s2;             // loopback
    hold  <= (rx_s2 == 1'b0) ? 24'hffffff : (hold != 0 ? hold - 1'b1 : 0);   // ~50 ms LED pulse per start bit
    led   <= hold != 0;
  end
endmodule
