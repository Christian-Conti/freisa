// Copyright 2026 FREISA contributors
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1
//
// Info     : Techmap of primitives unsupported by DREAMPlaceFPGA.
// Module   : _dp_bufg
// Author   : Christian Conti
// Contact  : christian.conti@mail.it

(* techmap_celltype = "BUFG" *)
module _dp_bufg (input I, output O);
  BUFGCE bufg (.I(I), .CE(1'b1), .O(O));
endmodule

(* techmap_celltype = "INV" *)
module _dp_inv (input I, output O);
  LUT1 #(.INIT(2'b01)) inv (.I0(I), .O(O));
endmodule

(* techmap_celltype = "LUT0" *)
module _dp_lut0 (output O);
  parameter [0:0] INIT = 1'b0;
  assign O = INIT;
endmodule
