module apb_slave_dut (
    input  logic        pclk,
    input  logic        presetn,
    input  logic [31:0] paddr,
    input  logic        psel,
    input  logic        penable,
    input  logic        pwrite,
    input  logic [31:0] pwdata,
    input  logic [3:0]  pstrb,
    output logic [31:0] prdata,
    output logic        pready,
    output logic        pslverr
);
  logic [31:0] registers [0:3];
  logic [2:0] wait_count;
  integer i;

  always_ff @(posedge pclk or negedge presetn) begin
    if (!presetn) begin
      prdata <= '0;
      pready <= 1'b0;
      pslverr <= 1'b0;
      wait_count <= '0;
      for (i = 0; i < 4; i++) registers[i] <= '0;
    end else begin
      pready <= 1'b0;
      pslverr <= 1'b0;

      if (psel && !penable) begin
        wait_count <= {1'b0, paddr[3:2]};
      end else if (psel && penable) begin
        if (wait_count != 0) begin
          wait_count <= wait_count - 1'b1;
        end else begin
          pready <= 1'b1;
          pslverr <= (paddr[7:0] == 8'hF0);
          if (paddr[7:0] == 8'hF0) begin
            prdata <= 32'hBAD0_00F0;
          end else if (pwrite) begin
            if (pstrb[0]) registers[paddr[3:2]][7:0] <= pwdata[7:0];
            if (pstrb[1]) registers[paddr[3:2]][15:8] <= pwdata[15:8];
            if (pstrb[2]) registers[paddr[3:2]][23:16] <= pwdata[23:16];
            if (pstrb[3]) registers[paddr[3:2]][31:24] <= pwdata[31:24];
          end else begin
            prdata <= registers[paddr[3:2]];
          end
        end
      end
    end
  end
endmodule
