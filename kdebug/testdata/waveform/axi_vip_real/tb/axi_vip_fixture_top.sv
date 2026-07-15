`timescale 1ns/1ps

module axi_vip_fixture_top;
  import uvm_pkg::*;
  import svt_uvm_pkg::*;
  import svt_axi_uvm_pkg::*;

  parameter int simulation_cycle = 10;
  bit clk;
  bit rst_n;

  initial begin
    clk = 0;
    forever #(simulation_cycle / 2) clk = ~clk;
  end

  initial begin
    rst_n = 0;
    repeat (20) @(posedge clk);
    rst_n = 1;
  end

  svt_axi_if axi_vip_if();
  assign axi_vip_if.common_aclk = clk;
  assign axi_vip_if.master_if[0].aresetn = rst_n;
  assign axi_vip_if.slave_if[0].aresetn = rst_n;

  axi_dut_wrapper dut_wrapper (
    .clk(clk),
    .rst_n(rst_n),
    .axi_if(axi_vip_if)
  );

  initial begin
    $fsdbDumpfile("waves.fsdb");
    $fsdbDumpvars("+all");
    $fsdbDumpSVA();
    $fsdbDumpMDA(0, axi_vip_fixture_top);
  end

  initial begin
    uvm_config_db#(svt_axi_vif)::set(
      uvm_root::get(),
      "uvm_test_top.env.axi_system_env",
      "vif",
      axi_vip_if
    );
    run_test();
  end

  initial begin
    #200ms;
    `uvm_fatal("TIMEOUT", "AXI VIP fixture timeout")
  end
endmodule
