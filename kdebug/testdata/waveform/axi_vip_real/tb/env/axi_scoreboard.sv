`ifndef GUARD_AXI_SCOREBOARD_SV
`define GUARD_AXI_SCOREBOARD_SV

//=======================================================================
// AXI Scoreboard - Compares Master and Slave transactions
//=======================================================================
class axi_sb_read_snapshot;
  bit [31:0] addr;
  int unsigned id;
  int unsigned burst_length;
  int unsigned burst_size;
  bit compare_valid[];
  bit [63:0] expected_data[];

  function new(svt_axi_transaction xact);
    addr = xact.addr;
    id = xact.id;
    burst_length = xact.burst_length;
    burst_size = xact.burst_size;
    compare_valid = new[xact.burst_length];
    expected_data = new[xact.burst_length];
  endfunction
endclass

typedef struct {
  bit [31:0] first_addr;
  bit [31:0] last_addr;
  int unsigned id;
  int unsigned burst_length;
  int unsigned burst_size;
} axi_sb_write_range_t;

class axi_scoreboard extends uvm_scoreboard;

  `uvm_component_utils(axi_scoreboard)

  // Analysis exports for master and slave
  uvm_analysis_export#(svt_axi_transaction) master_export;
  uvm_analysis_export#(svt_axi_transaction) slave_export;
  uvm_analysis_export#(svt_axi_transaction) slave_started_export;

  // TLM analysis fifos
  uvm_tlm_analysis_fifo#(svt_axi_transaction) master_fifo;
  uvm_tlm_analysis_fifo#(svt_axi_transaction) slave_fifo;
  uvm_tlm_analysis_fifo#(svt_axi_transaction) slave_started_fifo;

  // Statistics
  int num_master_wr = 0;
  int num_master_rd = 0;
  int num_slave_wr = 0;
  int num_slave_rd = 0;
  int num_compare_ok = 0;
  int num_compare_error = 0;
  longint unsigned expected_completion_order = 0;
  longint unsigned expected_request_order = 0;
  longint unsigned expected_write_index_by_id[int unsigned];
  longint unsigned expected_read_index_by_id[int unsigned];

  // Expected data for read-after-write check
  bit [63:0] expected_mem[bit [31:0]];
  axi_sb_write_range_t in_flight_writes[$];
  axi_sb_read_snapshot read_snapshots[$];

  // Constructor
  function new(string name="axi_scoreboard", uvm_component parent=null);
    super.new(name, parent);
  endfunction

  // Build phase
  virtual function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    master_export = new("master_export", this);
    slave_export = new("slave_export", this);
    slave_started_export = new("slave_started_export", this);
    master_fifo = new("master_fifo", this);
    slave_fifo = new("slave_fifo", this);
    slave_started_fifo = new("slave_started_fifo", this);
  endfunction

  // Connect phase
  virtual function void connect_phase(uvm_phase phase);
    super.connect_phase(phase);
    master_export.connect(master_fifo.analysis_export);
    slave_export.connect(slave_fifo.analysis_export);
    slave_started_export.connect(slave_started_fifo.analysis_export);
  endfunction

  // Run phase - compare transactions
  virtual task run_phase(uvm_phase phase);
    svt_axi_transaction master_xact, slave_xact;
    fork
      forever begin
        master_fifo.get(master_xact);
        process_master_transaction(master_xact);
      end
      forever begin
        slave_fifo.get(slave_xact);
        process_slave_transaction(slave_xact);
      end
      forever begin
        slave_started_fifo.get(slave_xact);
        process_slave_started_transaction(slave_xact);
      end
    join
  endtask

  virtual function bit ranges_overlap(bit [31:0] first_a, bit [31:0] last_a,
                                      bit [31:0] first_b, bit [31:0] last_b);
    return (first_a <= last_b) && (first_b <= last_a);
  endfunction

  virtual function bit has_in_flight_write(bit [31:0] beat_addr);
    foreach (in_flight_writes[i]) begin
      if (ranges_overlap(beat_addr, beat_addr,
                         in_flight_writes[i].first_addr,
                         in_flight_writes[i].last_addr)) begin
        return 1;
      end
    end
    return 0;
  endfunction

  virtual function void remove_in_flight_write(svt_axi_transaction xact);
    bit [31:0] last_addr;

    last_addr = xact.addr + ((xact.burst_length - 1) * (1 << xact.burst_size));
    foreach (in_flight_writes[i]) begin
      if (in_flight_writes[i].first_addr == xact.addr &&
          in_flight_writes[i].last_addr == last_addr &&
          in_flight_writes[i].id == xact.id &&
          in_flight_writes[i].burst_length == xact.burst_length &&
          in_flight_writes[i].burst_size == xact.burst_size) begin
        in_flight_writes.delete(i);
        return;
      end
    end
  endfunction

  virtual function int find_read_snapshot(svt_axi_transaction xact);
    foreach (read_snapshots[i]) begin
      if (read_snapshots[i].addr == xact.addr &&
          read_snapshots[i].id == xact.id &&
          read_snapshots[i].burst_length == xact.burst_length &&
          read_snapshots[i].burst_size == xact.burst_size) begin
        return i;
      end
    end
    return -1;
  endfunction

  virtual function longint unsigned axi_len_field(svt_axi_transaction xact);
    if (xact.burst_length == 0)
      return 0;
    return xact.burst_length - 1;
  endfunction

  virtual function void print_expected_transaction(svt_axi_transaction xact);
    string dir;
    longint unsigned id_index;
    longint unsigned len_field;
    longint unsigned beat_count;
    longint unsigned completion_time_ps;

    expected_request_order++;
    expected_completion_order++;
    len_field = axi_len_field(xact);
    beat_count = xact.burst_length;
    completion_time_ps = $time;

    if (xact.xact_type == svt_axi_transaction::WRITE) begin
      dir = "WR";
      expected_write_index_by_id[xact.id]++;
      id_index = expected_write_index_by_id[xact.id];
    end
    else begin
      dir = "RD";
      expected_read_index_by_id[xact.id]++;
      id_index = expected_read_index_by_id[xact.id];
    end

    $display("AXI_EXPECTED_TXN_JSON {\"dir\":\"%s\",\"id\":\"'h%0h\",\"addr\":\"'h%0h\",\"len\":\"'h%0h\",\"size\":\"'h%0h\",\"burst\":\"'h%0h\",\"resp\":\"'h0\",\"request_index\":%0d,\"id_index\":%0d,\"completion_order\":%0d,\"completion_time_ps\":%0d,\"latency_ps\":0,\"beat_count\":%0d,\"expected_beat_count\":%0d}",
      dir, xact.id, xact.addr, len_field, xact.burst_size, xact.burst_type,
      expected_request_order, id_index, expected_completion_order,
      completion_time_ps, beat_count, beat_count);
  endfunction

  virtual function void process_slave_started_transaction(svt_axi_transaction xact);
    if (xact.xact_type == svt_axi_transaction::WRITE) begin
      axi_sb_write_range_t write_range;

      write_range.first_addr = xact.addr;
      write_range.last_addr = xact.addr + ((xact.burst_length - 1) * (1 << xact.burst_size));
      write_range.id = xact.id;
      write_range.burst_length = xact.burst_length;
      write_range.burst_size = xact.burst_size;
      in_flight_writes.push_back(write_range);
    end
    else begin
      axi_sb_read_snapshot snapshot;

      snapshot = new(xact);
      foreach (snapshot.expected_data[i]) begin
        bit [31:0] beat_addr = xact.addr + (i * (1 << xact.burst_size));
        if (expected_mem.exists(beat_addr) && !has_in_flight_write(beat_addr)) begin
          snapshot.compare_valid[i] = 1;
          snapshot.expected_data[i] = expected_mem[beat_addr];
        end
      end
      read_snapshots.push_back(snapshot);
    end
  endfunction

  // Process master transaction
  virtual function void process_master_transaction(svt_axi_transaction xact);
    if (xact.xact_type == svt_axi_transaction::WRITE) begin
      num_master_wr++;
      print_expected_transaction(xact);
      `uvm_info("SCOREBOARD", $sformatf("Master WRITE: id=%0d, addr=0x%0h, len=%0d",
                xact.id, xact.addr, xact.burst_length), UVM_HIGH)
    end
    else begin
      num_master_rd++;
      print_expected_transaction(xact);
      `uvm_info("SCOREBOARD", $sformatf("Master READ: id=%0d, addr=0x%0h, len=%0d",
                xact.id, xact.addr, xact.burst_length), UVM_HIGH)
    end
  endfunction

  // Process slave transaction
  virtual function void process_slave_transaction(svt_axi_transaction xact);
    if (xact.xact_type == svt_axi_transaction::WRITE) begin
      num_slave_wr++;
      // Store completed write data for later read comparison.
      foreach (xact.data[i]) begin
        bit [31:0] beat_addr = xact.addr + (i * (1 << xact.burst_size));
        expected_mem[beat_addr] = xact.data[i];
      end
      remove_in_flight_write(xact);
    end
    else begin
      axi_sb_read_snapshot snapshot;
      int snapshot_idx;

      num_slave_rd++;
      // Verify read data matches expected
      snapshot_idx = find_read_snapshot(xact);
      if (snapshot_idx >= 0) begin
        snapshot = read_snapshots[snapshot_idx];
        foreach (xact.data[i]) begin
          bit [31:0] beat_addr = xact.addr + (i * (1 << xact.burst_size));
          if (i < snapshot.compare_valid.size() && snapshot.compare_valid[i]) begin
            if (xact.data[i] == snapshot.expected_data[i]) begin
              num_compare_ok++;
            end
            else begin
              num_compare_error++;
              `uvm_error("SCOREBOARD", $sformatf("READ DATA MISMATCH at addr=0x%0h: expected=0x%0h, actual=0x%0h",
                        beat_addr, snapshot.expected_data[i], xact.data[i]))
            end
          end
        end
        read_snapshots.delete(snapshot_idx);
      end
      else begin
        foreach (xact.data[i]) begin
          bit [31:0] beat_addr = xact.addr + (i * (1 << xact.burst_size));
          if (expected_mem.exists(beat_addr)) begin
            num_compare_ok++;
          end
        end
      end
    end
  endfunction

  // Report phase
  virtual function void report_phase(uvm_phase phase);
    `uvm_info("SCOREBOARD", "=============================================", UVM_LOW)
    `uvm_info("SCOREBOARD", "           SCOREBOARD REPORT                 ", UVM_LOW)
    `uvm_info("SCOREBOARD", "=============================================", UVM_LOW)
    `uvm_info("SCOREBOARD", $sformatf("Master WRITE transactions: %0d", num_master_wr), UVM_LOW)
    `uvm_info("SCOREBOARD", $sformatf("Master READ transactions:  %0d", num_master_rd), UVM_LOW)
    `uvm_info("SCOREBOARD", $sformatf("Slave WRITE transactions:  %0d", num_slave_wr), UVM_LOW)
    `uvm_info("SCOREBOARD", $sformatf("Slave READ transactions:   %0d", num_slave_rd), UVM_LOW)
    `uvm_info("SCOREBOARD", $sformatf("Data compare OK:           %0d", num_compare_ok), UVM_LOW)
    `uvm_info("SCOREBOARD", $sformatf("Data compare ERROR:        %0d", num_compare_error), UVM_LOW)
    `uvm_info("SCOREBOARD", "=============================================", UVM_LOW)

    if (num_compare_error == 0)
      `uvm_info("SCOREBOARD", "TEST PASSED - All data comparisons OK", UVM_LOW)
    else
      `uvm_error("SCOREBOARD", "TEST FAILED - Data mismatches detected")
  endfunction

endclass

`endif
