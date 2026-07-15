`ifndef GUARD_AXI_BASE_TEST_SV
`define GUARD_AXI_BASE_TEST_SV

`include "axi_tb_env.sv"

//=======================================================================
// AXI Base Test Class
// Provides common setup and utility functions for all tests
//=======================================================================
class axi_base_test extends uvm_test;

  `uvm_component_utils(axi_base_test)

  // Testbench environment
  axi_tb_env env;

  // Constructor
  function new(string name="axi_base_test", uvm_component parent=null);
    super.new(name, parent);
  endfunction

  // Build phase
  virtual function void build_phase(uvm_phase phase);
    `uvm_info("TEST", "Build phase started", UVM_MEDIUM)
    super.build_phase(phase);

    // Create environment
    env = axi_tb_env::type_id::create("env", this);

    `uvm_info("TEST", "Build phase completed", UVM_MEDIUM)
  endfunction

  // End of elaboration phase
  virtual function void end_of_elaboration_phase(uvm_phase phase);
    super.end_of_elaboration_phase(phase);
    `uvm_info("TEST", $sformatf("%s", this.sprint()), UVM_HIGH)
  endfunction

  // Run phase - main test entry
  virtual task run_phase(uvm_phase phase);
    phase.raise_objection(this);
    `uvm_info("TEST", "=============================================", UVM_LOW)
    `uvm_info("TEST", "Starting test...", UVM_LOW)
    `uvm_info("TEST", "=============================================", UVM_LOW)

    // Wait for reset to complete
    wait_for_reset();

    // Run main test sequence
    run_main_sequence(phase);

    // Wait for all transactions to complete
    `uvm_info("TEST", "Waiting for transactions to complete...", UVM_MEDIUM)
    #10000;

    phase.drop_objection(this);
    `uvm_info("TEST", "=============================================", UVM_LOW)
    `uvm_info("TEST", "Test completed", UVM_LOW)
    `uvm_info("TEST", "=============================================", UVM_LOW)
  endtask

  // Wait for reset
  virtual task wait_for_reset();
    `uvm_info("TEST", "Waiting for reset...", UVM_MEDIUM)
    // Simple delay for reset - could be enhanced with reset interface
    #300ns;
    `uvm_info("TEST", "Reset completed", UVM_MEDIUM)
  endtask

  // Main test sequence - to be overridden by derived tests
  virtual task run_main_sequence(uvm_phase phase);
    `uvm_info("TEST", "Base test - no sequence defined", UVM_LOW)
  endtask

endclass

`endif
