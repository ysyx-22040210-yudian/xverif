class apb_vip_sequence extends svt_apb_master_base_sequence;
  `uvm_object_utils(apb_vip_sequence)

  int unsigned write_count;
  int unsigned read_count;
  int unsigned error_count;

  function new(string name = "apb_vip_sequence");
    super.new(name);
  endfunction

  virtual task body();
    super.body();

    apb_write(32'h00, 32'h1122_3344, 4'b1111);
    apb_write(32'h04, 32'h5566_7788, 4'b1111);
    apb_write(32'h08, 32'hA5A5_5A5A, 4'b1111);
    apb_write(32'h0C, 32'hDEAD_BEEF, 4'b1111);
    apb_write(32'h04, 32'h0000_ABCD, 4'b0011);

    apb_read_check(32'h00, 32'h1122_3344, 1'b0);
    apb_read_check(32'h04, 32'h5566_ABCD, 1'b0);
    apb_read_check(32'h08, 32'hA5A5_5A5A, 1'b0);
    apb_read_check(32'h0C, 32'hDEAD_BEEF, 1'b0);
    apb_read_check(32'hF0, 32'hBAD0_00F0, 1'b1);

    `uvm_info(
        "APB_FIXTURE",
        $sformatf(
            "APB VIP fixture completed: writes=%0d reads=%0d errors=%0d",
            write_count,
            read_count,
            error_count
        ),
        UVM_LOW
    )
  endtask

  task apb_write(
      bit [31:0] address,
      bit [31:0] data,
      bit [3:0] pstrb
  );
    svt_apb_master_transaction tr;
    tr = svt_apb_master_transaction::type_id::create("write_tr");
    tr.xact_type = svt_apb_transaction::WRITE;
    tr.address = address;
    tr.data = data;
    tr.pstrb = pstrb;
    start_item(tr);
    finish_item(tr);
    get_response(tr);
    write_count++;
  endtask

  task apb_read_check(
      bit [31:0] address,
      bit [31:0] expected,
      bit expected_error
  );
    svt_apb_master_transaction tr;
    tr = svt_apb_master_transaction::type_id::create("read_tr");
    tr.xact_type = svt_apb_transaction::READ;
    tr.address = address;
    start_item(tr);
    finish_item(tr);
    get_response(tr);
    read_count++;

    if (tr.pslverr_enable !== expected_error) begin
      `uvm_error(
          "APB_FIXTURE",
          $sformatf(
              "error response mismatch address=0x%08h expected=%0b actual=%0b",
              address,
              expected_error,
              tr.pslverr_enable
          )
      )
    end
    if (expected_error) begin
      error_count++;
    end else if (tr.data !== expected) begin
      `uvm_error(
          "APB_FIXTURE",
          $sformatf(
              "read mismatch address=0x%08h expected=0x%08h actual=0x%08h",
              address,
              expected,
              tr.data
          )
      )
    end
  endtask
endclass
