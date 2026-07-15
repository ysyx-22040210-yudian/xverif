class apb_vip_test extends uvm_test;
  `uvm_component_utils(apb_vip_test)

  apb_vip_env env;

  function new(string name = "apb_vip_test", uvm_component parent = null);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    svt_apb_system_configuration cfg;

    super.build_phase(phase);
    cfg = new("cfg");
    cfg.num_slaves = 1;
    cfg.create_sub_cfgs(1);
    cfg.pdata_width = svt_apb_system_configuration::PDATA_WIDTH_32;
    cfg.paddr_width = svt_apb_system_configuration::PADDR_WIDTH_32;
    cfg.is_active = 1;
    cfg.slave_cfg[0].is_active = 0;
    uvm_config_db#(svt_apb_system_configuration)::set(
        this,
        "env.apb_system_env",
        "cfg",
        cfg
    );
    env = apb_vip_env::type_id::create("env", this);
  endfunction

  task run_phase(uvm_phase phase);
    apb_vip_sequence seq;

    phase.raise_objection(this);
    seq = apb_vip_sequence::type_id::create("seq");
    seq.start(env.apb_system_env.master.sequencer);
    #50ns;
    phase.drop_objection(this);
  endtask
endclass
