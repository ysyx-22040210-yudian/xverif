class apb_vip_env extends uvm_env;
  `uvm_component_utils(apb_vip_env)

  svt_apb_system_env apb_system_env;

  function new(string name = "apb_vip_env", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    apb_system_env =
        svt_apb_system_env::type_id::create("apb_system_env", this);
  endfunction
endclass
