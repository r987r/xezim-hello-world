// #76: one physical PCIe0 SRAM shared by real routed AXI/iDMA and the
// pinned verilog-pcie dma_if_pcie segmented local-RAM interface.
//
// This is a memory *attachment*, not a custom PCIe TLP or AXI router.
// tc_sram (existing pinned PULP memory) owns all five physical ports:
// AXI4, two requester-read ports and two requester-write ports.
// Software/descriptor ownership MUST serialize conflicting addresses.
module pcie_dma_sram_target #(
  parameter type req_t = logic,
  parameter type rsp_t = logic,
  parameter int unsigned IdWidth = 5,
  parameter logic [63:0] Base = 64'h12000000,
  parameter int unsigned Bytes = 16384
) (
  input logic clk_i, rst_ni,
  input req_t req_i,
  output rsp_t rsp_o,
  output logic mon_valid_o, mon_write_o,
  output logic [63:0] mon_addr_o, mon_data_o,
  output logic [7:0] mon_strb_o,

  input logic [3:0] ram_rd_cmd_sel,
  input logic [23:0] ram_rd_cmd_addr,
  input logic [1:0] ram_rd_cmd_valid,
  output logic [1:0] ram_rd_cmd_ready,
  output logic [127:0] ram_rd_resp_data,
  output logic [1:0] ram_rd_resp_valid,
  input logic [1:0] ram_rd_resp_ready,
  input logic [3:0] ram_wr_cmd_sel,
  input logic [15:0] ram_wr_cmd_be,
  input logic [23:0] ram_wr_cmd_addr,
  input logic [127:0] ram_wr_cmd_data,
  input logic [1:0] ram_wr_cmd_valid,
  output logic [1:0] ram_wr_cmd_ready,
  output logic [1:0] ram_wr_done
);
  localparam int Words = Bytes / 8;
  localparam int WordBits = $clog2(Words);
  localparam int SegmentAddrBits = 12;  // 64K upstream RAM_ADDR_WIDTH - log2(16)
  // Bit 0 of a 64-bit word index selects one of the 2 segmented banks.
  localparam int MaxSegmentAddr = Bytes / 16;

  logic [0:0] axi_request, axi_we, axi_rvalid, axi_error;
  logic [0:0][63:0] axi_addr, axi_wdata;
  logic [0:0][7:0] axi_be;
  logic [4:0] request, we;
  logic [4:0][WordBits-1:0] address;
  logic [4:0][63:0] wdata, rdata;
  logic [4:0][7:0] be;
  logic bad;
  logic [1:0] rd_pending;

  assign bad = axi_addr[0] < Base || axi_addr[0] >= Base + Bytes;
  assign request[0] = axi_request[0] && !bad;
  assign we[0] = axi_we[0];
  assign address[0] = WordBits'((axi_addr[0] - Base) >> 3);
  assign wdata[0] = axi_wdata[0];
  assign be[0] = axi_be[0];
  assign mon_valid_o = rst_ni && axi_request[0] && !bad;
  assign mon_write_o = axi_we[0];
  assign mon_addr_o = axi_addr[0];
  assign mon_data_o = axi_wdata[0];
  assign mon_strb_o = axi_be[0];

  axi_to_detailed_mem #(
    .axi_req_t(req_t), .axi_resp_t(rsp_t), .AddrWidth(64), .DataWidth(64),
    .IdWidth(IdWidth), .UserWidth(1), .NumBanks(1), .BufDepth(1)
  ) u_axi (
    .clk_i, .rst_ni, .busy_o(), .axi_req_i(req_i), .axi_resp_o(rsp_o),
    .mem_req_o(axi_request), .mem_gnt_i(1'b1), .mem_addr_o(axi_addr),
    .mem_wdata_o(axi_wdata), .mem_strb_o(axi_be), .mem_we_o(axi_we),
    .mem_atop_o(), .mem_lock_o(), .mem_id_o(), .mem_user_o(),
    .mem_cache_o(), .mem_prot_o(), .mem_qos_o(), .mem_region_o(),
    .mem_rvalid_i(axi_rvalid), .mem_rdata_i(rdata[0]),
    .mem_err_i(axi_error), .mem_exokay_i('0)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      axi_rvalid <= '0;
      axi_error <= '0;
      rd_pending <= '0;
      ram_wr_done <= '0;
    end else begin
      axi_rvalid <= axi_request;
      axi_error <= axi_request & {1{bad}};
      ram_wr_done <= ram_wr_cmd_valid & ram_wr_cmd_ready;
      for (int k = 0; k < 2; k++) begin
        if (ram_rd_cmd_ready[k])
          rd_pending[k] <= ram_rd_cmd_valid[k];
      end
    end
  end

  for (genvar k = 0; k < 2; k++) begin : gen_seg
    // All accesses are bounded to the actual 16KiB SRAM, not the nominal
    // 64KiB address width of the upstream requester descriptors.
    wire [11:0] rd_addr = ram_rd_cmd_addr[k*12 +: 12];
    wire [11:0] wr_addr = ram_wr_cmd_addr[k*12 +: 12];
    assign ram_rd_cmd_ready[k] = rst_ni && (!rd_pending[k] || ram_rd_resp_ready[k]);
    assign request[1+k] = ram_rd_cmd_valid[k] && ram_rd_cmd_ready[k];
    assign we[1+k] = 1'b0;
    assign address[1+k] = WordBits'((rd_addr << 1) | k);
    assign wdata[1+k] = '0;
    assign be[1+k] = '0;
    assign ram_rd_resp_data[k*64 +: 64] = rdata[1+k];
    assign ram_rd_resp_valid[k] = rd_pending[k];
    assign ram_wr_cmd_ready[k] = rst_ni;
    assign request[3+k] = ram_wr_cmd_valid[k] && ram_wr_cmd_ready[k];
    assign we[3+k] = 1'b1;
    assign address[3+k] = WordBits'((wr_addr << 1) | k);
    assign wdata[3+k] = ram_wr_cmd_data[k*64 +: 64];
    assign be[3+k] = ram_wr_cmd_be[k*8 +: 8];

    // No modulo aliasing of out-of-window requester DMA descriptors.
    always @(posedge clk_i) if (rst_ni) begin
      if (request[1+k] && (rd_addr >= MaxSegmentAddr || (|ram_rd_cmd_sel[k*2 +: 2])))
        $fatal(1, "PCIe outbound RAM read outside SRAM or invalid selection");
      if (request[3+k] && (wr_addr >= MaxSegmentAddr || (|ram_wr_cmd_sel[k*2 +: 2])))
        $fatal(1, "PCIe outbound RAM write outside SRAM or invalid selection");
      if (request[3+k] && request[0] && we[0] && address[3+k] == address[0])
        $fatal(1, "PCIe requester write collided with AXI memory write");
    end
  end

  tc_sram #(
    .NumWords(Words), .DataWidth(64), .NumPorts(5),
    .Latency(1), .SimInit("none")
  ) u_ram (
    .clk_i, .rst_ni, .req_i(request), .we_i(we),
    .addr_i(address), .wdata_i(wdata), .be_i(be), .rdata_o(rdata)
  );

  initial begin
    if (Bytes != 16384 || Base != 64'h12000000)
      $fatal(1, "Unqualified PCIe0 outbound SRAM layout");
  end
endmodule
