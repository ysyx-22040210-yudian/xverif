`timescale 1ns/1ps

// P0-6: procedural for mux
//   always_comb: for (i=0; i<N; i++) if (sel==i) y = a[i];
// Query at 15ns: sel=2, a[2]=1
// Expect: if native returns a[sel] → PASS; only block → PARTIAL

module top #(parameter int N = 4);
  logic [N-1:0] a;
  logic [$clog2(N)-1:0] sel;
  logic y;

  always_comb begin
    y = 1'b0;
    for (int i = 0; i < N; i++) begin
      if (sel == i)
        y = a[i];
    end
  end

  initial begin
    a   = 4'b0000;
    sel = 2'b00;
    #5;
    sel = 2'b10;  // sel=2
    a   = 4'b0100;  // a[2]=1
    #10;
    $finish;
  end
endmodule
