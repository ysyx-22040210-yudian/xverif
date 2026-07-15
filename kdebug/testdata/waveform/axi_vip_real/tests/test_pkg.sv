`ifndef GUARD_TEST_PKG_SV
`define GUARD_TEST_PKG_SV

//=======================================================================
// Test Package - Includes all test components
//=======================================================================

import uvm_pkg::*;
  import svt_uvm_pkg::*;
  import svt_axi_uvm_pkg::*;
`include "axi_base_test.sv"
`include "axi_multi_id_wr_rd_seq.sv"
`include "axi_slave_mem_delayed_seq.sv"
`include "axi_multi_id_test.sv"

`endif
