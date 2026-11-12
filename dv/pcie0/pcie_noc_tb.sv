`timescale 1ns/1ps
// Reuse REAL generated pcie0 FlooNoC and tc_sram; no new PCIe0 NoC yet.
module pcie_noc_tb #(
  // Opt-in isolated TLP-only relocation; NOT qualified digital PCIe link.
  parameter bit BAR0_RELOCATE = 1'b0
) (
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
  output logic [63:0] sram_last_read_addr,
  output logic bar0_relocation_enabled
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

  // One actual generated FlooNoC: use PCIe0's 64-bit host-initiator NI; it is an independent generated NoC.
  floo_xezim_pcie0_local_data_noc_pkg::axi_in_req_t pcie_req;
  floo_xezim_pcie0_local_data_noc_pkg::axi_in_rsp_t pcie_rsp;
  floo_xezim_pcie0_local_data_noc_pkg::axi_out_req_t sram_req;
  floo_xezim_pcie0_local_data_noc_pkg::axi_out_rsp_t sram_rsp;
  logic mem_valid, mem_write;
  logic [63:0] mem_addr, mem_data;
  logic [7:0] mem_strb;
  assign bar0_relocation_enabled = BAR0_RELOCATE;

  // Real pinned TLP->AXI master below emits HOST PCIe bus addresses.
  // Before entering FlooNoC, translate and authorize complete AW/AR bursts.
  // These fixed address settings belong only to this standalone fixture.
  logic [31:0] aw_local_addr, ar_local_addr;
  logic aw_in_window, ar_in_window, aw_blocked, ar_blocked;
  logic [31:0] aw_transfer_bytes, ar_transfer_bytes;
  logic aw_authorized, ar_authorized;
  assign aw_transfer_bytes = ({24'd0, m_axi_awlen} + 32'd1) << m_axi_awsize;
  assign ar_transfer_bytes = ({24'd0, m_axi_arlen} + 32'd1) << m_axi_arsize;

  pcie_bar0_noc_translate u_aw_relocate (
    .request_valid_i(m_axi_awvalid), .pci_address_i(m_axi_awaddr[31:0]),
    .request_bytes_i(aw_transfer_bytes),
    .host_bar0_bus_base_i(32'h80001000),
    .bar0_aperture_i(32'h00001000),
    .bar0_local_target_i(32'h12000000),
    .bar0_committed_i(1'b1), .bar_mem_ready_i(1'b1),
    .request_in_window_o(aw_in_window),
    .noc_address_o(aw_local_addr), .blocked_o(aw_blocked)
  );
  pcie_bar0_noc_translate u_ar_relocate (
    .request_valid_i(m_axi_arvalid), .pci_address_i(m_axi_araddr[31:0]),
    .request_bytes_i(ar_transfer_bytes),
    .host_bar0_bus_base_i(32'h80001000),
    .bar0_aperture_i(32'h00001000),
    .bar0_local_target_i(32'h12000000),
    .bar0_committed_i(1'b1), .bar_mem_ready_i(1'b1),
    .request_in_window_o(ar_in_window),
    .noc_address_o(ar_local_addr), .blocked_o(ar_blocked)
  );
  // Never discard upper 32 bits when translating a 64-bit AXI address.
  assign aw_authorized = (m_axi_awaddr[63:32] == 32'd0) && aw_in_window;
  assign ar_authorized = (m_axi_araddr[63:32] == 32'd0) && ar_in_window;
  // This diagnostic fixture fails hard on illegal traffic. Production
  // integration requires actual UR/CA/DECERR completion semantics.
  always_ff @(posedge clk) begin
    if (!rst && BAR0_RELOCATE) begin
      if (m_axi_awvalid && !aw_authorized)
        $fatal(1, "PCIe BAR0 invalid AW addr=%h bytes=%0d", m_axi_awaddr, aw_transfer_bytes);
      if (m_axi_arvalid && !ar_authorized)
        $fatal(1, "PCIe BAR0 invalid AR addr=%h bytes=%0d", m_axi_araddr, ar_transfer_bytes);
    end
  end

  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      sram_write_count <= 0;
      sram_read_count <= 0;
      sram_last_write_addr <= 0;
      sram_last_read_addr <= 0;
    end else if (mem_valid) begin
      if (mem_write) begin
        sram_write_count <= sram_write_count + 1;
        sram_last_write_addr <= mem_addr;
      end else begin
        sram_read_count <= sram_read_count + 1;
        sram_last_read_addr <= mem_addr;
      end
    end
  end

  assign pcie_req.aw.id = m_axi_awid;
  assign pcie_req.aw.addr = BAR0_RELOCATE ? {32'd0, aw_local_addr} : m_axi_awaddr;
  assign pcie_req.aw.len = m_axi_awlen;
  assign pcie_req.aw.size = m_axi_awsize;
  assign pcie_req.aw.burst = m_axi_awburst;
  assign pcie_req.aw.lock = m_axi_awlock;
  assign pcie_req.aw.cache = m_axi_awcache;
  assign pcie_req.aw.prot = m_axi_awprot;
  assign pcie_req.w.data = m_axi_wdata;
  assign pcie_req.w.strb = m_axi_wstrb;
  assign pcie_req.w.last = m_axi_wlast;
  assign pcie_req.ar.id = m_axi_arid;
  assign pcie_req.ar.addr = BAR0_RELOCATE ? {32'd0, ar_local_addr} : m_axi_araddr;
  assign pcie_req.ar.len = m_axi_arlen;
  assign pcie_req.ar.size = m_axi_arsize;
  assign pcie_req.ar.burst = m_axi_arburst;
  assign pcie_req.ar.lock = m_axi_arlock;
  assign pcie_req.ar.cache = m_axi_arcache;
  assign pcie_req.ar.prot = m_axi_arprot;
  assign pcie_req.aw.qos = '0;
  assign pcie_req.aw.region = '0;
  assign pcie_req.aw.user = '0;
  assign pcie_req.ar.qos = '0;
  assign pcie_req.ar.region = '0;
  assign pcie_req.ar.user = '0;
  assign pcie_req.aw.atop = '0;
  assign pcie_req.w.user = '0;
  assign pcie_req.aw_valid = m_axi_awvalid && (!BAR0_RELOCATE || aw_authorized);
  assign pcie_req.w_valid = m_axi_wvalid;
  assign pcie_req.ar_valid = m_axi_arvalid && (!BAR0_RELOCATE || ar_authorized);
  assign pcie_req.b_ready = m_axi_bready;
  assign pcie_req.r_ready = m_axi_rready;
  assign m_axi_awready = pcie_rsp.aw_ready && (!BAR0_RELOCATE || aw_authorized);
  assign m_axi_wready = pcie_rsp.w_ready;
  assign m_axi_arready = pcie_rsp.ar_ready && (!BAR0_RELOCATE || ar_authorized);
  assign m_axi_bvalid = pcie_rsp.b_valid;
  assign m_axi_rvalid = pcie_rsp.r_valid;
  assign m_axi_bid = pcie_rsp.b.id;
  assign m_axi_bresp = pcie_rsp.b.resp;
  assign m_axi_rid = pcie_rsp.r.id;
  assign m_axi_rdata = pcie_rsp.r.data;
  assign m_axi_rresp = pcie_rsp.r.resp;
  assign m_axi_rlast = pcie_rsp.r.last;

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
  // Reuse the genuine PCIe0 local data NoC from the shared SoC generator.

  floo_xezim_pcie0_local_data_noc u_noc (
    .clk_i(clk), .rst_ni(~rst), .test_enable_i(1'b0),
    .host_axi_in_req_i(pcie_req), .host_axi_in_rsp_o(pcie_rsp),
    .global_in_axi_in_req_i('0), .global_in_axi_in_rsp_o(),
    .sram_axi_out_req_o(sram_req), .sram_axi_out_rsp_i(sram_rsp),
    .global_out_axi_out_req_o(), .global_out_axi_out_rsp_i('0)
  );

  axi_sram_target #(
    .req_t(floo_xezim_pcie0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_pcie0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(5),
    .Base(64'h0000000012000000),
    .Bytes(16384),
    .ReadOnly(1'b0)
  ) u_sram (
    .clk_i(clk), .rst_ni(~rst),
    .req_i(sram_req), .rsp_o(sram_rsp),
    .mon_valid_o(mem_valid), .mon_write_o(mem_write),
    .mon_addr_o(mem_addr), .mon_data_o(mem_data),
    .mon_strb_o(mem_strb)
  );
endmodule
