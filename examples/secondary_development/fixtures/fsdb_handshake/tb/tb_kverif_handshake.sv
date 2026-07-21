`timescale 1ns/1ps

module tb_kverif_handshake;
  logic       clk;
  logic       rst_n;
  logic       req_valid;
  logic       req_ready;
  logic [7:0] req_data;
  logic       rsp_valid;
  logic [7:0] rsp_data;
  logic [3:0] accepted_count;

  kverif_handshake_dut dut (
    .clk            (clk),
    .rst_n          (rst_n),
    .req_valid      (req_valid),
    .req_ready      (req_ready),
    .req_data       (req_data),
    .rsp_valid      (rsp_valid),
    .rsp_data       (rsp_data),
    .accepted_count (accepted_count)
  );

  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    $fsdbDumpfile("waves.fsdb");
    $fsdbDumpvars(0, tb_kverif_handshake);
    $fsdbDumpMDA(0, tb_kverif_handshake);
  end

  initial begin
    rst_n     = 1'b0;
    req_valid = 1'b0;
    req_ready = 1'b0;
    req_data  = 8'h00;

    repeat (3) @(posedge clk);
    rst_n <= 1'b1;

    @(negedge clk);
    req_valid <= 1'b1;
    req_ready <= 1'b0;
    req_data  <= 8'h12;

    @(negedge clk);
    req_ready <= 1'b1;

    @(negedge clk);
    req_data <= 8'h34;

    @(negedge clk);
    req_valid <= 1'b0;
    req_ready <= 1'b0;

    @(negedge clk);
    req_valid <= 1'b1;
    req_ready <= 1'b1;
    req_data  <= 8'ha5;

    @(negedge clk);
    req_ready <= 1'b0;
    req_data  <= 8'hb6;

    @(negedge clk);
    req_ready <= 1'b1;

    @(negedge clk);
    req_valid <= 1'b0;
    req_ready <= 1'b0;

    repeat (3) @(posedge clk);
    $finish;
  end

endmodule
