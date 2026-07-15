`ifndef GUARD_AXI_TB_ENV_SV
`define GUARD_AXI_TB_ENV_SV

`include "axi_scoreboard.sv"
`include "axi_virtual_sequencer.sv"

//=======================================================================
// AXI Testbench Environment
// Configured for multi-ID transactions with memory slave
//=======================================================================
class axi_tb_env extends uvm_env;

  `uvm_component_utils(axi_tb_env)

  // AXI System Environment (VIP)
  svt_axi_system_env axi_system_env;

  // Testbench components
  axi_scoreboard scoreboard;
  axi_virtual_sequencer sequencer;

  // Configuration
  svt_axi_system_configuration axi_cfg;

  // Constructor
  function new(string name="axi_tb_env", uvm_component parent=null);
    super.new(name, parent);
  endfunction

  // Build phase
  virtual function void build_phase(uvm_phase phase);
    `uvm_info("ENV", "Build phase started", UVM_MEDIUM)
    super.build_phase(phase);

    // Create AXI system configuration
    axi_cfg = create_configuration();

    // Set configuration for VIP
    uvm_config_db#(svt_axi_system_configuration)::set(
      this, "axi_system_env", "cfg", axi_cfg
    );

    // Create VIP system environment
    axi_system_env = svt_axi_system_env::type_id::create("axi_system_env", this);

    // Create scoreboard
    scoreboard = axi_scoreboard::type_id::create("scoreboard", this);

    // Create virtual sequencer
    sequencer = axi_virtual_sequencer::type_id::create("sequencer", this);

    `uvm_info("ENV", "Build phase completed", UVM_MEDIUM)
  endfunction

  // Connect phase
  virtual function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);

    // Connect master agent to scoreboard
    if (axi_system_env.master[0] != null) begin
      axi_system_env.master[0].monitor.item_observed_port.connect(
        scoreboard.master_export
      );
      sequencer.master_sequencer = axi_system_env.master[0].sequencer;
    end

    // Connect slave agent to scoreboard
    if (axi_system_env.slave[0] != null) begin
      axi_system_env.slave[0].monitor.item_observed_port.connect(
        scoreboard.slave_export
      );
      axi_system_env.slave[0].monitor.item_started_port.connect(
        scoreboard.slave_started_export
      );
      sequencer.slave_sequencer = axi_system_env.slave[0].sequencer;
    end

    `uvm_info("ENV", "Connect phase completed", UVM_MEDIUM)
  endfunction

  // End of elaboration phase
  virtual function void end_of_elaboration_phase(uvm_phase phase);
    super.end_of_elaboration_phase(phase);
    `uvm_info("ENV", $sformatf("%s", this.sprint()), UVM_HIGH)
  endfunction

  // Create and configure AXI system configuration
  virtual function svt_axi_system_configuration create_configuration();
    svt_axi_system_configuration cfg;
    int num_ids = 4;
    int outstanding_depth = 16;
    int max_outstanding;

    cfg = svt_axi_system_configuration::type_id::create("axi_cfg");

    void'($value$plusargs("num_ids=%0d", num_ids));
    void'($value$plusargs("outstanding_depth=%0d", outstanding_depth));
    max_outstanding = num_ids * outstanding_depth * 2;
    if (max_outstanding < 32)
      max_outstanding = 32;

    // Configure for 1 master, 1 slave
    cfg.num_masters = 1;
    cfg.num_slaves = 1;
    cfg.create_sub_cfgs(1, 1);

    // Configure master agent for multi-ID support
    cfg.master_cfg[0].axi_interface_type = svt_axi_port_configuration::AXI4;
    cfg.master_cfg[0].data_width = 64;
    cfg.master_cfg[0].addr_width = 32;
    cfg.master_cfg[0].id_width = 4;  // Support 16 IDs (0-15)
    cfg.master_cfg[0].num_outstanding_xact = max_outstanding;

    // Configure slave agent for memory mode with multi-ID
    cfg.slave_cfg[0].axi_interface_type = svt_axi_port_configuration::AXI4;
    cfg.slave_cfg[0].data_width = 64;
    cfg.slave_cfg[0].addr_width = 32;
    cfg.slave_cfg[0].id_width = 4;
    cfg.slave_cfg[0].num_outstanding_xact = max_outstanding;

    // Set address range for slave
    cfg.set_addr_range(0, 64'h0000_0000, 64'h0001_FFFF);

    // Keep the VIP monitor analysis ports enabled, but disable VIP transaction
    // reporting/XML so the large stress run only logs the compact golden JSON.
    cfg.master_cfg[0].enable_reporting = 0;
    cfg.slave_cfg[0].enable_reporting = 0;
    cfg.master_cfg[0].enable_xml_gen = 0;
    cfg.slave_cfg[0].enable_xml_gen = 0;

    `uvm_info("ENV", "AXI Configuration created:", UVM_LOW)
    `uvm_info("ENV", $sformatf("  Data Width: %0d", cfg.master_cfg[0].data_width), UVM_LOW)
    `uvm_info("ENV", $sformatf("  ID Width: %0d", cfg.master_cfg[0].id_width), UVM_LOW)
    `uvm_info("ENV", $sformatf("  Max Outstanding: %0d", cfg.master_cfg[0].num_outstanding_xact), UVM_LOW)

    return cfg;
  endfunction

endclass

`endif
