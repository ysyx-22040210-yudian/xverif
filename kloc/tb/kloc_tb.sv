`include "uvm_macros.svh"

module kloc_tb;

  import uvm_pkg::*;
  import kloc_pkg::*;

  kloc_report_server loc_svr;

  initial begin
    loc_svr = new();
    loc_svr.copy(uvm_coreservice_t::get().get_report_server());
    uvm_coreservice_t::get().set_report_server(loc_svr);

    `uvm_info("KLOC_TB", "test starting", UVM_LOW)

    // --- errors from this file ---
    `uvm_error("FILE_OPEN", "cannot open config file")
    `uvm_error("FILE_OPEN", "cannot open config file")   // duplicate: same loc_id
    `uvm_warning("TIMEOUT", "response took longer than expected")

    // --- call test in another file ---
    simple_test();

    `uvm_info("KLOC_TB", "test done", UVM_LOW)
  end

  `include "simple_test.sv"

endmodule
