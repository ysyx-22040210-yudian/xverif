`ifndef GUARD_AXI_MULTI_ID_TEST_SV
`define GUARD_AXI_MULTI_ID_TEST_SV

`include "axi_base_test.sv"
`include "axi_multi_id_wr_rd_seq.sv"
`include "axi_slave_mem_delayed_seq.sv"

//=======================================================================
// AXI Multi-ID Test
// Tests multiple ID transactions with memory slave and random delays
//=======================================================================
class axi_multi_id_test extends axi_base_test;

  `uvm_component_utils(axi_multi_id_test)

  // Test parameters (can be overridden via config_db)
  int num_ids = 4;
  int trans_per_id = 200;
  int min_delay = 100;
  int max_delay = 300;
  int single_beat_pct = 30;
  int outstanding_depth = 16;

  // Constructor
  function new(string name="axi_multi_id_test", uvm_component parent=null);
    super.new(name, parent);
  endfunction

  // Build phase - get configuration
  virtual function void build_phase(uvm_phase phase);
    super.build_phase(phase);

    // Get test parameters from plusargs
    void'($value$plusargs("num_ids=%0d", num_ids));
    void'($value$plusargs("trans_per_id=%0d", trans_per_id));
    void'($value$plusargs("min_delay=%0d", min_delay));
    void'($value$plusargs("max_delay=%0d", max_delay));
    void'($value$plusargs("single_beat_pct=%0d", single_beat_pct));
    void'($value$plusargs("outstanding_depth=%0d", outstanding_depth));

    `uvm_info("TEST", "=============================================", UVM_LOW)
    `uvm_info("TEST", "Multi-ID Test Configuration:", UVM_LOW)
    `uvm_info("TEST", $sformatf("  Number of IDs: %0d", num_ids), UVM_LOW)
    `uvm_info("TEST", $sformatf("  Transactions per ID: %0d", trans_per_id), UVM_LOW)
    `uvm_info("TEST", $sformatf("  Outstanding depth per ID/direction: %0d", outstanding_depth), UVM_LOW)
    `uvm_info("TEST", $sformatf("  Total transactions: %0d", num_ids * trans_per_id * 2), UVM_LOW)
    `uvm_info("TEST", $sformatf("  Slave delay range: %0d - %0d cycles", min_delay, max_delay), UVM_LOW)
    `uvm_info("TEST", $sformatf("  Single-beat percentage: %0d%%", single_beat_pct), UVM_LOW)
    `uvm_info("TEST", "=============================================", UVM_LOW)
  endfunction

  // Main test sequence
  virtual task run_main_sequence(uvm_phase phase);
    axi_multi_id_master_seq master_seq;
    axi_slave_mem_delayed_seq slave_seq;
    int expected_transactions;

    // Create sequences
    master_seq = axi_multi_id_master_seq::type_id::create("master_seq");
    slave_seq = axi_slave_mem_delayed_seq::type_id::create("slave_seq");

    // Configure slave sequence
    slave_seq.min_resp_delay = min_delay;
    slave_seq.max_resp_delay = max_delay;
    slave_seq.init_mem_random = 1;

    // Configure master sequence
    master_seq.num_ids = num_ids;
    master_seq.trans_per_id = trans_per_id;
    master_seq.single_beat_pct = single_beat_pct;
    master_seq.outstanding_depth = outstanding_depth;
    expected_transactions = num_ids * trans_per_id;

    // Start slave sequence in background
    `uvm_info("TEST", "Starting slave memory sequence...", UVM_MEDIUM)
    fork
      begin
        slave_seq.start(env.sequencer.slave_sequencer);
      end
    join_none

    // Small delay to ensure slave is ready
    #100;

    // Run master sequence
    `uvm_info("TEST", "=============================================", UVM_LOW)
    `uvm_info("TEST", "Starting master multi-ID sequence...", UVM_LOW)
    `uvm_info("TEST", "=============================================", UVM_LOW)

    // Set starting phase for automatic objection management
    master_seq.starting_phase = phase;
    master_seq.start(env.sequencer.master_sequencer);

    // Wait for all outstanding slave responses before stopping the reactive slave.
    `uvm_info("TEST", "Master sequence completed, waiting for slave responses...", UVM_MEDIUM)
    fork
      begin
        wait (slave_seq.num_wr_responses >= expected_transactions &&
              slave_seq.num_rd_responses >= expected_transactions);
      end
      begin
        #(expected_transactions * (max_delay + 100) * 20);
        `uvm_fatal("TEST", $sformatf("Timed out waiting for slave responses: wr=%0d/%0d rd=%0d/%0d",
                  slave_seq.num_wr_responses, expected_transactions,
                  slave_seq.num_rd_responses, expected_transactions))
      end
    join_any
    disable fork;

    // Stop slave sequence
    slave_seq.kill();

    `uvm_info("TEST", "=============================================", UVM_LOW)
    `uvm_info("TEST", "All sequences completed", UVM_LOW)
    `uvm_info("TEST", "=============================================", UVM_LOW)
  endtask

endclass

`endif
