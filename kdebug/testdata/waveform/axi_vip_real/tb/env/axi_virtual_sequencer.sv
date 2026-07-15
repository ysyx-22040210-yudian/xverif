`ifndef GUARD_AXI_VIRTUAL_SEQUENCER_SV
`define GUARD_AXI_VIRTUAL_SEQUENCER_SV

//=======================================================================
// AXI Virtual Sequencer
// Provides access to master and slave sequencers
//=======================================================================
class axi_virtual_sequencer extends uvm_sequencer;

  `uvm_component_utils(axi_virtual_sequencer)

  // Master and slave sequencer handles
  uvm_sequencer_base master_sequencer;
  uvm_sequencer_base slave_sequencer;

  // Constructor
  function new(string name="axi_virtual_sequencer", uvm_component parent=null);
    super.new(name, parent);
  endfunction

endclass

`endif
