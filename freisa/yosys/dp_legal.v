// Map primitives yosys emits but DREAMPlaceFPGA's IF library lacks onto ones it has.
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
