`timescale 1ns/1ps

// P0-1: flop temporal boundary
//   assign comb = in0 & in1;
//   always_ff @(posedge clk) q <= comb;
//   assign out = q;
// Expect: out → q (temporal boundary) → comb → in0/in1

module top;
  logic       clk;
  logic       in0, in1;
  logic       comb, q, out;

  assign comb = in0 & in1;
  assign out  = q;

  always_ff @(posedge clk)
    q <= comb;

  // clock: period 10ns
  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    in0 = 1'b0;
    in1 = 1'b0;
    #3;
    in0 = 1'b1;  // comb becomes 1 at 3ns
    in1 = 1'b1;
    #20;         // q samples comb at 15ns posedge
    $finish;
  end
endmodule
