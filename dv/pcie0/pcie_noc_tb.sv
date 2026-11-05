`timescale 1ns/1ps
// Reuse REAL generated compute0 FlooNoC and tc_sram; no new PCIe0 NoC yet.
module pcie_noc_tb (
  input logic clk,
  input logic rst,
  input logic [64-1:0] rx_req_tlp_data,
  input logic [128-1:0] rx_req_tlp_hdr,
  input logic [1-1:0] rx_req_tlp_valid,
  input logic [1-1:0] rx_req_tlp_sop,
  input logic [1-1:0] rx_req_tlp_eop,
  output logic rx_req_tlp_ready,
  output logic [64-1:0] tx_cpl_tlp_data,
  output logic [2-1:0] tx_cpl_tlp_strb,
  output logic [128-1:0] tx_cpl_tlp_hdr,
  output logic [1-1:0] tx_cpl_tlp_valid,
  output logic [1-1:0] tx_cpl_tlp_sop,
  output logic [1-1:0] tx_cpl_tlp_eop,
  input logic tx_cpl_tlp_ready,
  input logic [15:0] completer_id,
  input logic [2:0] max_payload_size,
  output logic status_error_cor,
  output logic status_error_uncor,
  output logic [31:0] sram_write_count,
  output logic [31:0] sram_read_count,
  output logic [63:0] sram_last_write_addr,
  output logic [63:0] sram_last_read_addr
);
 logic [4-1:0] m_axi_awid;
 logic [64-1:0] m_axi_awaddr;
 logic [7:0] m_axi_awlen;
 logic [2:0] m_axi_awsize;
 logic [1:0] m_axi_awburst;
 logic m_axi_awlock;
 logic [3:0] m_axi_awcache;
 logic [2:0] m_axi_awprot;
 logic m_axi_awvalid;
 logic m_axi_awready;
 logic [64-1:0] m_axi_wdata;
 logic [8-1:0] m_axi_wstrb;
 logic m_axi_wlast;
 logic m_axi_wvalid;
 logic m_axi_wready;
 logic [4-1:0] m_axi_bid;
 logic [1:0] m_axi_bresp;
 logic m_axi_bvalid;
 logic m_axi_bready;
 logic [4-1:0] m_axi_arid;
 logic [64-1:0] m_axi_araddr;
 logic [7:0] m_axi_arlen;
 logic [2:0] m_axi_arsize;
 logic [1:0] m_axi_arburst;
 logic m_axi_arlock;
 logic [3:0] m_axi_arcache;
 logic [2:0] m_axi_arprot;
 logic m_axi_arvalid;
 logic m_axi_arready;
 logic [4-1:0] m_axi_rid;
 logic [64-1:0] m_axi_rdata;
 logic [1:0] m_axi_rresp;
 logic m_axi_rlast;
 logic m_axi_rvalid;
 logic m_axi_rready;
  logic [1:0] sram_valid, sram_write;
  logic [127:0] sram_addr, sram_data;
  logic [15:0] sram_strb;

  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      sram_write_count <= '0;
      sram_read_count <= '0;
      sram_last_write_addr <= '0;
      sram_last_read_addr <= '0;
    end else begin
      if (sram_valid[0] && sram_write[0]) begin
        sram_write_count <= sram_write_count + 1;
        sram_last_write_addr <= sram_addr[0 +: 64];
      end
      if (sram_valid[0] && !sram_write[0]) begin
        sram_read_count <= sram_read_count + 1;
        sram_last_read_addr <= sram_addr[0 +: 64];
      end
    end
  end

  pcie_axi_master #(
    .TLP_DATA_WIDTH(64), .TLP_STRB_WIDTH(2), .TLP_HDR_WIDTH(128),
    .TLP_SEG_COUNT(1), .AXI_DATA_WIDTH(64), .AXI_ADDR_WIDTH(64),
    .AXI_STRB_WIDTH(8), .AXI_ID_WIDTH(4), .AXI_MAX_BURST_LEN(256)
  ) u_bridge (
    .clk(clk),
    .rst(rst),
    .rx_req_tlp_data(rx_req_tlp_data),
    .rx_req_tlp_hdr(rx_req_tlp_hdr),
    .rx_req_tlp_valid(rx_req_tlp_valid),
    .rx_req_tlp_sop(rx_req_tlp_sop),
    .rx_req_tlp_eop(rx_req_tlp_eop),
    .rx_req_tlp_ready(rx_req_tlp_ready),
    .tx_cpl_tlp_data(tx_cpl_tlp_data),
    .tx_cpl_tlp_strb(tx_cpl_tlp_strb),
    .tx_cpl_tlp_hdr(tx_cpl_tlp_hdr),
    .tx_cpl_tlp_valid(tx_cpl_tlp_valid),
    .tx_cpl_tlp_sop(tx_cpl_tlp_sop),
    .tx_cpl_tlp_eop(tx_cpl_tlp_eop),
    .tx_cpl_tlp_ready(tx_cpl_tlp_ready),
    .m_axi_awid(m_axi_awid),
    .m_axi_awaddr(m_axi_awaddr),
    .m_axi_awlen(m_axi_awlen),
    .m_axi_awsize(m_axi_awsize),
    .m_axi_awburst(m_axi_awburst),
    .m_axi_awlock(m_axi_awlock),
    .m_axi_awcache(m_axi_awcache),
    .m_axi_awprot(m_axi_awprot),
    .m_axi_awvalid(m_axi_awvalid),
    .m_axi_awready(m_axi_awready),
    .m_axi_wdata(m_axi_wdata),
    .m_axi_wstrb(m_axi_wstrb),
    .m_axi_wlast(m_axi_wlast),
    .m_axi_wvalid(m_axi_wvalid),
    .m_axi_wready(m_axi_wready),
    .m_axi_bid(m_axi_bid),
    .m_axi_bresp(m_axi_bresp),
    .m_axi_bvalid(m_axi_bvalid),
    .m_axi_bready(m_axi_bready),
    .m_axi_arid(m_axi_arid),
    .m_axi_araddr(m_axi_araddr),
    .m_axi_arlen(m_axi_arlen),
    .m_axi_arsize(m_axi_arsize),
    .m_axi_arburst(m_axi_arburst),
    .m_axi_arlock(m_axi_arlock),
    .m_axi_arcache(m_axi_arcache),
    .m_axi_arprot(m_axi_arprot),
    .m_axi_arvalid(m_axi_arvalid),
    .m_axi_arready(m_axi_arready),
    .m_axi_rid(m_axi_rid),
    .m_axi_rdata(m_axi_rdata),
    .m_axi_rresp(m_axi_rresp),
    .m_axi_rlast(m_axi_rlast),
    .m_axi_rvalid(m_axi_rvalid),
    .m_axi_rready(m_axi_rready),
    .completer_id(completer_id),
    .max_payload_size(max_payload_size),
    .status_error_cor(status_error_cor),
    .status_error_uncor(status_error_uncor)
  );
  // DmaTestMode exclusively connects the source to CPU0's real data NI.
  // ProbeEnable=0 guarantees the disabled DMA NI remains inactive.
  soc_top #(.ProbeEnable(1'b0), .DmaEnable(1'b0), .DmaTestMode(1'b1)) u_soc (
    .clk_i(clk),
    .rst_ni(~rst),
    .hold_mask_i(2'b11),
    .dma_irq_o(),
    .dma_irq_pending_o(),
    .released_o(),
    .fetch_valid_o(),
    .fetch_addr_o(),
    .sram_valid_o(sram_valid),
    .sram_write_o(sram_write),
    .sram_addr_o(sram_addr),
    .sram_data_o(sram_data),
    .sram_strb_o(sram_strb),
    .rom_reads_o(),
    .flash_reads_o(),
    .probe_awid(m_axi_awid),
    .probe_awaddr(m_axi_awaddr),
    .probe_awlen(m_axi_awlen),
    .probe_awsize(m_axi_awsize),
    .probe_awburst(m_axi_awburst),
    .probe_awlock(m_axi_awlock),
    .probe_awcache(m_axi_awcache),
    .probe_awprot(m_axi_awprot),
    .probe_awqos('0),
    .probe_awregion('0),
    .probe_awvalid(m_axi_awvalid),
    .probe_awready(m_axi_awready),
    .probe_wdata(m_axi_wdata),
    .probe_wstrb(m_axi_wstrb),
    .probe_wlast(m_axi_wlast),
    .probe_wvalid(m_axi_wvalid),
    .probe_wready(m_axi_wready),
    .probe_bid(m_axi_bid),
    .probe_bresp(m_axi_bresp),
    .probe_bvalid(m_axi_bvalid),
    .probe_bready(m_axi_bready),
    .probe_arid(m_axi_arid),
    .probe_araddr(m_axi_araddr),
    .probe_arlen(m_axi_arlen),
    .probe_arsize(m_axi_arsize),
    .probe_arburst(m_axi_arburst),
    .probe_arlock(m_axi_arlock),
    .probe_arcache(m_axi_arcache),
    .probe_arprot(m_axi_arprot),
    .probe_arqos('0),
    .probe_arregion('0),
    .probe_arvalid(m_axi_arvalid),
    .probe_arready(m_axi_arready),
    .probe_rid(m_axi_rid),
    .probe_rdata(m_axi_rdata),
    .probe_rresp(m_axi_rresp),
    .probe_rlast(m_axi_rlast),
    .probe_rvalid(m_axi_rvalid),
    .probe_rready(m_axi_rready),
    .cfgprobe_awid('0),
    .cfgprobe_awaddr('0),
    .cfgprobe_awlen('0),
    .cfgprobe_awsize('0),
    .cfgprobe_awburst('0),
    .cfgprobe_awlock('0),
    .cfgprobe_awcache('0),
    .cfgprobe_awprot('0),
    .cfgprobe_awqos('0),
    .cfgprobe_awregion('0),
    .cfgprobe_awvalid('0),
    .cfgprobe_awready(),
    .cfgprobe_wdata('0),
    .cfgprobe_wstrb('0),
    .cfgprobe_wlast('0),
    .cfgprobe_wvalid('0),
    .cfgprobe_wready(),
    .cfgprobe_bid(),
    .cfgprobe_bresp(),
    .cfgprobe_bvalid(),
    .cfgprobe_bready('0),
    .cfgprobe_arid('0),
    .cfgprobe_araddr('0),
    .cfgprobe_arlen('0),
    .cfgprobe_arsize('0),
    .cfgprobe_arburst('0),
    .cfgprobe_arlock('0),
    .cfgprobe_arcache('0),
    .cfgprobe_arprot('0),
    .cfgprobe_arqos('0),
    .cfgprobe_arregion('0),
    .cfgprobe_arvalid('0),
    .cfgprobe_arready(),
    .cfgprobe_rid(),
    .cfgprobe_rdata(),
    .cfgprobe_rresp(),
    .cfgprobe_rlast(),
    .cfgprobe_rvalid(),
    .cfgprobe_rready('0)
  );
endmodule
