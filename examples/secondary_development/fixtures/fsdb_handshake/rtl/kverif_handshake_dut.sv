`timescale 1ns/1ps

module kverif_handshake_dut (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       req_valid,
  input  logic       req_ready,
  input  logic [7:0] req_data,
  output logic       rsp_valid,
  output logic [7:0] rsp_data,
  output logic [3:0] accepted_count
);

  typedef enum logic [1:0] {
    IDLE       = 2'b00,
    WAIT_READY = 2'b01,
    RESPOND    = 2'b10
  } state_t;

  state_t state_q;
  logic [7:0] last_accepted_q;
  logic       req_fire;

  assign req_fire = req_valid && req_ready;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state_q         <= IDLE;
      last_accepted_q <= 8'h00;
      rsp_valid       <= 1'b0;
      rsp_data        <= 8'h00;
      accepted_count  <= 4'h0;
    end else begin
      rsp_valid <= req_fire;

      if (req_fire) begin
        last_accepted_q <= req_data;
        rsp_data        <= req_data ^ 8'h5a;
        accepted_count  <= accepted_count + 4'h1;
        state_q         <= RESPOND;
      end else if (req_valid) begin
        state_q <= WAIT_READY;
      end else begin
        state_q <= IDLE;
      end
    end
  end

endmodule
