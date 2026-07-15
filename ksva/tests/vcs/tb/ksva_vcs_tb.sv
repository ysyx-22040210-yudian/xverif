// ksva VCS testbench
// Minimal testbench: generates clock, reset, and runs simulation.
// Individual DUTs and assertions are `included from case directories.

module ksva_vcs_tb;

  // ── Clock & Reset ──
  reg clk = 0;
  reg rst_n = 0;

  always #5 clk = ~clk;  // 100MHz

  // ── DUT signals (common interface) ──
  reg  req;
  reg  ack;
  reg  done;
  reg  [31:0] data;
  reg  [31:0] rsp_data;

  // ── Stimulus ──
  initial begin
    repeat(5) @(posedge clk);
    rst_n = 1;
    repeat(3) @(posedge clk);

    // Default stimulus: req pulse, ack response, data pattern
    req <= 1;
    data <= 32'hdead_beef;
    @(posedge clk);
    req <= 0;

    // ack after 2 cycles
    repeat(2) @(posedge clk);
    ack <= 1;
    rsp_data <= 32'hdead_beef;
    @(posedge clk);
    ack <= 0;

    repeat(20) @(posedge clk);

    $finish;
  end

  // ── Assertions from case directory ──
  // VCS assertion results are automatically reported in sim.log
  // Assertions are in cases/<name>/assertions.sv

`include "cases/simple_impl/assertions.sv"
`include "cases/ranged_delay/assertions.sv"
`include "cases/rose_fell/assertions.sv"
`include "cases/overlap_nonoverlap/assertions.sv"

endmodule
