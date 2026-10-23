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

// FDSE (synchronous set) -> FDRE storing the inverted value: same behaviour, a cell type the placer knows.
(* techmap_celltype = "FDSE" *)
module _dp_fdse (output Q, input C, input CE, input S, input D);
  parameter [0:0] INIT = 1'b1;
  parameter [0:0] IS_C_INVERTED = 1'b0;
  parameter [0:0] IS_D_INVERTED = 1'b0;
  parameter [0:0] IS_S_INVERTED = 1'b0;
  wire dn, qn;
  LUT1 #(.INIT(IS_D_INVERTED ? 2'b10 : 2'b01)) inv_d (.I0(D), .O(dn));
  FDRE #(.INIT(~INIT), .IS_C_INVERTED(IS_C_INVERTED), .IS_R_INVERTED(IS_S_INVERTED)) ff (.Q(qn), .C(C), .CE(CE), .R(S), .D(dn));
  LUT1 #(.INIT(2'b01)) inv_q (.I0(qn), .O(Q));
endmodule
