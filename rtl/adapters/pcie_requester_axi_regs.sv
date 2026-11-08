// PCIe0 outbound requester control, CPU-owned through the real 32-bit
// Config FlooNoC. PULP owns AXI4->AXI4-Lite; this module owns bounded
// CSR semantics and native dma_if_pcie descriptor handshakes.
//
// Register ABI (word aligned, full 32-bit writes only):
// 0x00 WR_HOST_LO    0x04 WR_HOST_HI   0x08 WR_RAM_ADDR
// 0x0c WR_LEN        0x10 WR_TAG       0x14 WR_DOORBELL
// 0x18 WR_STATUS [0]=done [1]=busy [2]=error [15:8]=tag [19:16]=errcode
// 0x20 RD_HOST_LO    0x24 RD_HOST_HI   0x28 RD_RAM_ADDR
// 0x2c RD_LEN        0x30 RD_TAG       0x34 RD_DOORBELL
// 0x38 RD_STATUS (same bit layout); 0x3c VERSION (read-only 0x760001).
// One request per direction outstanding: conflicting doorbells get SLVERR,
// never silently overwrite an active descriptor.
module pcie_requester_axi_regs #(
  parameter type axi_req_t = logic,
  parameter type axi_rsp_t = logic,
  parameter type lite_req_t = logic,
  parameter type lite_rsp_t = logic,
  parameter int unsigned AxiIdWidth = 1,
  parameter logic [31:0] CsrBase = 32'h40040000,
  parameter int unsigned RamBytes = 16384
)(
  input logic clk_i, rst_ni,
  input axi_req_t cfg_req_i,
  output axi_rsp_t cfg_rsp_o,
  output logic [63:0] s_axis_write_desc_pcie_addr,
  output logic [15:0] s_axis_write_desc_ram_addr,
  output logic [15:0] s_axis_write_desc_len,
  output logic [7:0] s_axis_write_desc_tag,
  output logic s_axis_write_desc_valid,
  input logic s_axis_write_desc_ready,
  input logic [7:0] m_axis_write_desc_status_tag,
  input logic [3:0] m_axis_write_desc_status_error,
  input logic m_axis_write_desc_status_valid,
  output logic [63:0] s_axis_read_desc_pcie_addr,
  output logic [15:0] s_axis_read_desc_ram_addr,
  output logic [15:0] s_axis_read_desc_len,
  output logic [7:0] s_axis_read_desc_tag,
  output logic s_axis_read_desc_valid,
  input logic s_axis_read_desc_ready,
  input logic [7:0] m_axis_read_desc_status_tag,
  input logic [3:0] m_axis_read_desc_status_error,
  input logic m_axis_read_desc_status_valid
);
  lite_req_t lite_req;
  lite_rsp_t lite_rsp;
  axi_to_axi_lite #(
    .AxiAddrWidth(32), .AxiDataWidth(32), .AxiIdWidth(AxiIdWidth),
    .AxiUserWidth(1), .AxiMaxWriteTxns(2), .AxiMaxReadTxns(2),
    .full_req_t(axi_req_t), .full_resp_t(axi_rsp_t),
    .lite_req_t(lite_req_t), .lite_resp_t(lite_rsp_t)
  ) u_axi4_to_lite (
    .clk_i, .rst_ni, .slv_req_i(cfg_req_i), .slv_resp_o(cfg_rsp_o),
    .mst_req_o(lite_req), .mst_resp_i(lite_rsp)
  );

  logic aw_pending, w_pending, bvalid_q, rvalid_q;
  logic [31:0] aw_addr_q, w_data_q, rdata_q;
  logic [3:0] w_strb_q;
  logic [1:0] bresp_q, rresp_q;
  logic write_fire, read_fire, aw_in_window, ar_in_window;
  logic [31:0] wr_offset, rd_offset;
  logic illegal_write;
  logic [63:0] wr_host_q, rd_host_q;
  logic [15:0] wr_ram_q, rd_ram_q, wr_len_q, rd_len_q;
  logic [7:0] wr_tag_q, rd_tag_q;
  logic wr_busy_q, rd_busy_q, wr_pending_q, rd_pending_q;
  logic wr_done_q, rd_done_q, wr_error_q, rd_error_q;
  logic [3:0] wr_code_q, rd_code_q;
  logic [7:0] wr_status_tag_q, rd_status_tag_q;

  assign lite_rsp.aw_ready = rst_ni && !aw_pending && !bvalid_q;
  assign lite_rsp.w_ready = rst_ni && !w_pending && !bvalid_q;
  assign write_fire = aw_pending && w_pending && !bvalid_q;
  assign lite_rsp.b_valid = bvalid_q;
  assign lite_rsp.b.resp = bresp_q;
  assign lite_rsp.ar_ready = rst_ni && !rvalid_q && !aw_pending &&
                              !w_pending && !bvalid_q;
  assign read_fire = lite_req.ar_valid && lite_rsp.ar_ready;
  assign lite_rsp.r_valid = rvalid_q;
  assign lite_rsp.r.data = rdata_q;
  assign lite_rsp.r.resp = rresp_q;
  assign wr_offset = aw_addr_q - CsrBase;
  assign rd_offset = lite_req.ar.addr - CsrBase;
  assign aw_in_window = aw_addr_q >= CsrBase && wr_offset < 32'h40 &&
                        aw_addr_q[1:0] == 2'b0;
  assign ar_in_window = lite_req.ar.addr >= CsrBase && rd_offset < 32'h40 &&
                        lite_req.ar.addr[1:0] == 2'b0;

  // Each request's entire source/destination must fit the qualified SRAM.
  // The host address is 64-bit and may cross a 4K PCIe boundary.
  always_comb begin
    illegal_write = w_strb_q != 4'hf;
    case (wr_offset)
      32'h00, 32'h04, 32'h08, 32'h0c, 32'h10,
      32'h20, 32'h24, 32'h28, 32'h2c, 32'h30: ;
      32'h14: illegal_write = illegal_write || (w_data_q != 32'd1) ||
                        wr_busy_q || wr_host_q == 64'd0 ||
                        wr_len_q == 16'd0 ||
                        (int'(wr_ram_q) + int'(wr_len_q) > RamBytes);
      32'h34: illegal_write = illegal_write || (w_data_q != 32'd1) ||
                        rd_busy_q || rd_host_q == 64'd0 ||
                        rd_len_q == 16'd0 ||
                        (int'(rd_ram_q) + int'(rd_len_q) > RamBytes);
      default: illegal_write = 1'b1;
    endcase
  end

  assign s_axis_write_desc_pcie_addr = wr_host_q;
  assign s_axis_write_desc_ram_addr = wr_ram_q;
  assign s_axis_write_desc_len = wr_len_q;
  assign s_axis_write_desc_tag = wr_tag_q;
  assign s_axis_write_desc_valid = wr_pending_q;
  assign s_axis_read_desc_pcie_addr = rd_host_q;
  assign s_axis_read_desc_ram_addr = rd_ram_q;
  assign s_axis_read_desc_len = rd_len_q;
  assign s_axis_read_desc_tag = rd_tag_q;
  assign s_axis_read_desc_valid = rd_pending_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      aw_pending <= 0; w_pending <= 0;
      aw_addr_q <= '0; w_data_q <= '0; w_strb_q <= '0;
      bvalid_q <= 0; rvalid_q <= 0; bresp_q <= '0;
      rresp_q <= '0; rdata_q <= '0;
      wr_host_q <= '0; rd_host_q <= '0;
      wr_ram_q <= '0; rd_ram_q <= '0;
      wr_len_q <= '0; rd_len_q <= '0;
      wr_tag_q <= '0; rd_tag_q <= '0;
      wr_busy_q <= 0; rd_busy_q <= 0;
      wr_pending_q <= 0; rd_pending_q <= 0;
      wr_done_q <= 0; rd_done_q <= 0;
      wr_error_q <= 0; rd_error_q <= 0;
      wr_code_q <= '0; rd_code_q <= '0;
      wr_status_tag_q <= '0; rd_status_tag_q <= '0;
    end else begin
      if (lite_req.aw_valid && lite_rsp.aw_ready) begin
        aw_pending <= 1;
        aw_addr_q <= lite_req.aw.addr;
      end
      if (lite_req.w_valid && lite_rsp.w_ready) begin
        w_pending <= 1;
        w_data_q <= lite_req.w.data;
        w_strb_q <= lite_req.w.strb;
      end
      if (write_fire) begin
        aw_pending <= 0;
        w_pending <= 0;
        bvalid_q <= 1;
        bresp_q <= !aw_in_window ? 2'b11 :
                   illegal_write ? 2'b10 : 2'b00;
        if (aw_in_window && !illegal_write) begin
          case (wr_offset)
            32'h00: wr_host_q[31:0] <= w_data_q;
            32'h04: wr_host_q[63:32] <= w_data_q;
            32'h08: wr_ram_q <= w_data_q[15:0];
            32'h0c: wr_len_q <= w_data_q[15:0];
            32'h10: wr_tag_q <= w_data_q[7:0];
            32'h14: begin
              wr_pending_q <= 1;
              wr_busy_q <= 1;
              wr_done_q <= 0;
              wr_error_q <= 0;
              wr_code_q <= '0;
            end
            32'h20: rd_host_q[31:0] <= w_data_q;
            32'h24: rd_host_q[63:32] <= w_data_q;
            32'h28: rd_ram_q <= w_data_q[15:0];
            32'h2c: rd_len_q <= w_data_q[15:0];
            32'h30: rd_tag_q <= w_data_q[7:0];
            32'h34: begin
              rd_pending_q <= 1;
              rd_busy_q <= 1;
              rd_done_q <= 0;
              rd_error_q <= 0;
              rd_code_q <= '0;
            end
            default: ;
          endcase
        end
      end
      if (bvalid_q && lite_req.b_ready) bvalid_q <= 0;
      if (read_fire) begin
        rvalid_q <= 1;
        rresp_q <= ar_in_window ? 2'b00 : 2'b11;
        rdata_q <= 0;
        if (ar_in_window) begin
          case (rd_offset)
            32'h00: rdata_q <= wr_host_q[31:0];
            32'h04: rdata_q <= wr_host_q[63:32];
            32'h08: rdata_q <= {16'd0, wr_ram_q};
            32'h0c: rdata_q <= {16'd0, wr_len_q};
            32'h10: rdata_q <= {24'd0, wr_tag_q};
            32'h18: rdata_q <= {12'd0, wr_code_q, wr_status_tag_q,
                                 5'd0, wr_error_q, wr_busy_q, wr_done_q};
            32'h20: rdata_q <= rd_host_q[31:0];
            32'h24: rdata_q <= rd_host_q[63:32];
            32'h28: rdata_q <= {16'd0, rd_ram_q};
            32'h2c: rdata_q <= {16'd0, rd_len_q};
            32'h30: rdata_q <= {24'd0, rd_tag_q};
            32'h38: rdata_q <= {12'd0, rd_code_q, rd_status_tag_q,
                                 5'd0, rd_error_q, rd_busy_q, rd_done_q};
            32'h3c: rdata_q <= 32'h00760001;
            default: rresp_q <= 2'b11;
          endcase
        end
      end
      if (rvalid_q && lite_req.r_ready) rvalid_q <= 0;

      if (wr_pending_q && s_axis_write_desc_ready) wr_pending_q <= 0;
      if (rd_pending_q && s_axis_read_desc_ready) rd_pending_q <= 0;
      if (m_axis_write_desc_status_valid) begin
        wr_busy_q <= 0;
        wr_pending_q <= 0;
        wr_done_q <= 1;
        wr_status_tag_q <= m_axis_write_desc_status_tag;
        wr_code_q <= m_axis_write_desc_status_error;
        wr_error_q <= m_axis_write_desc_status_error != 0 ||
                      m_axis_write_desc_status_tag != wr_tag_q || !wr_busy_q;
      end
      if (m_axis_read_desc_status_valid) begin
        rd_busy_q <= 0;
        rd_pending_q <= 0;
        rd_done_q <= 1;
        rd_status_tag_q <= m_axis_read_desc_status_tag;
        rd_code_q <= m_axis_read_desc_status_error;
        rd_error_q <= m_axis_read_desc_status_error != 0 ||
                      m_axis_read_desc_status_tag != rd_tag_q || !rd_busy_q;
      end
    end
  end
  initial if (RamBytes != 16384) $fatal(1,"PCIe0 requester SRAM unqualified");
endmodule
