`timescale 1ns/1ps

// P0-5: mux branch handling
//   assign y = sel ? a : b;
// Scene A (10ns): sel=1, only a toggles → expect continue to a
// Scene B (30ns): sel=1, both a and b toggle → native decides or stops
// Scene C (50ns): a/b stable, sel toggles → control-caused transition

module top;
  logic a, b, sel, y;

  assign y = sel ? a : b;

  initial begin
    a   = 1'b0;
    b   = 1'b0;
    sel = 1'b0;

    // Scene A: sel=1, only a toggles at 10ns
    #10;
    sel = 1'b1;
    a   = 1'b1;  // only a changes; b stays 0

    // Scene B: sel=1, both a and b toggle at 30ns
    #20;
    a = 1'b0;
    b = 1'b0;  // both change
    #1;
    a = 1'b1;
    b = 1'b0;  // a high, b low, sel=1 → y=a

    // Scene C: a/b stable, sel toggles at 50ns
    #19;  // ~50ns
    a = 1'b0;
    b = 1'b1;
    sel = 1'b0;  // sel=0 selects b
    #2;
    sel = 1'b1;  // sel toggles → selects a
    // a=0, b=1: y transitions from 1 to 0 due to sel change

    #20;
    $finish;
  end
endmodule
