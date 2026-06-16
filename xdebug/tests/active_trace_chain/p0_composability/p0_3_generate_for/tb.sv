`timescale 1ns/1ps

// P0-3: generate for + module instance
//   genvar i; for (i=0; i<N; i++) begin : gen_u
//     leaf u_leaf(.a(a[i]), .b(b[i]), .y(y[i]));
// Expect: top.y[2] → top.gen_u[2].u_leaf.y → top.a[2]/top.b[2]

module leaf(input logic a, b, output logic y);
  assign y = a & b;
endmodule

module top;
  parameter int N = 4;
  logic [N-1:0] a, b, y;

  genvar i;
  generate
    for (i = 0; i < N; i++) begin : gen_u
      leaf u_leaf(.a(a[i]), .b(b[i]), .y(y[i]));
    end
  endgenerate

  initial begin
    a = 4'b0000;
    b = 4'b0000;
    #5;
    a = 4'b1111;
    b = 4'b1111;  // all y bits become 1
    #20;
    $finish;
  end
endmodule
