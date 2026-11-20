`timescale 1ns/1ps
// Generated chip boot + DMA configuration: see gen/chip/manifest.json.
module soc_top #(parameter bit ProbeEnable = 0, DmaEnable = 0, DmaTestMode = 0) (input logic clk_i, rst_ni,
  input logic [1:0] hold_mask_i,
  input logic ddr_init_mode_i,
  input logic ddr_negative_mode_i,
  output logic [1:0] dma_irq_o, dma_irq_pending_o,
  output logic [1:0] released_o, fetch_valid_o,
  output logic [63:0] fetch_addr_o,
  output logic [1:0] sram_valid_o, sram_write_o,
  output logic [127:0] sram_addr_o, sram_data_o,
  output logic [15:0] sram_strb_o,
  output logic [31:0] rom_reads_o, flash_reads_o,
  input logic [3:0] probe_awid,
  input logic [63:0] probe_awaddr,
  input logic [7:0] probe_awlen,
  input logic [2:0] probe_awsize,
  input logic [1:0] probe_awburst,
  input logic probe_awlock,
  input logic [3:0] probe_awcache,
  input logic [2:0] probe_awprot,
  input logic [3:0] probe_awqos,
  input logic [3:0] probe_awregion,
  input logic probe_awvalid,
  output logic probe_awready,
  input logic [63:0] probe_wdata,
  input logic [7:0] probe_wstrb,
  input logic probe_wlast,
  input logic probe_wvalid,
  output logic probe_wready,
  output logic [3:0] probe_bid,
  output logic [1:0] probe_bresp,
  output logic probe_bvalid,
  input logic probe_bready,
  input logic [3:0] probe_arid,
  input logic [63:0] probe_araddr,
  input logic [7:0] probe_arlen,
  input logic [2:0] probe_arsize,
  input logic [1:0] probe_arburst,
  input logic probe_arlock,
  input logic [3:0] probe_arcache,
  input logic [2:0] probe_arprot,
  input logic [3:0] probe_arqos,
  input logic [3:0] probe_arregion,
  input logic probe_arvalid,
  output logic probe_arready,
  output logic [3:0] probe_rid,
  output logic [63:0] probe_rdata,
  output logic [1:0] probe_rresp,
  output logic probe_rlast,
  output logic probe_rvalid,
  input logic probe_rready,
  input logic cfgprobe_awid,
  input logic [31:0] cfgprobe_awaddr,
  input logic [7:0] cfgprobe_awlen,
  input logic [2:0] cfgprobe_awsize,
  input logic [1:0] cfgprobe_awburst,
  input logic cfgprobe_awlock,
  input logic [3:0] cfgprobe_awcache,
  input logic [2:0] cfgprobe_awprot,
  input logic [3:0] cfgprobe_awqos,
  input logic [3:0] cfgprobe_awregion,
  input logic cfgprobe_awvalid,
  output logic cfgprobe_awready,
  input logic [31:0] cfgprobe_wdata,
  input logic [3:0] cfgprobe_wstrb,
  input logic cfgprobe_wlast,
  input logic cfgprobe_wvalid,
  output logic cfgprobe_wready,
  output logic cfgprobe_bid,
  output logic [1:0] cfgprobe_bresp,
  output logic cfgprobe_bvalid,
  input logic cfgprobe_bready,
  input logic cfgprobe_arid,
  input logic [31:0] cfgprobe_araddr,
  input logic [7:0] cfgprobe_arlen,
  input logic [2:0] cfgprobe_arsize,
  input logic [1:0] cfgprobe_arburst,
  input logic cfgprobe_arlock,
  input logic [3:0] cfgprobe_arcache,
  input logic [2:0] cfgprobe_arprot,
  input logic [3:0] cfgprobe_arqos,
  input logic [3:0] cfgprobe_arregion,
  input logic cfgprobe_arvalid,
  output logic cfgprobe_arready,
  output logic cfgprobe_rid,
  output logic [31:0] cfgprobe_rdata,
  output logic [1:0] cfgprobe_rresp,
  output logic cfgprobe_rlast,
  output logic cfgprobe_rvalid,
  input logic cfgprobe_rready,
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
  output logic [31:0] pcie_sram_write_count, pcie_sram_read_count,
  output logic [63:0] pcie_sram_last_write_addr, pcie_sram_last_read_addr,
  input logic gmii_rx_clk, gmii_rx_rst, gmii_tx_clk, gmii_tx_rst,
  input logic [7:0] gmii_rxd,
  input logic gmii_rx_dv, gmii_rx_er,
  output logic [7:0] gmii_txd,
  output logic gmii_tx_en, gmii_tx_er, eth_irq_o, eth_drop_o,
  output logic eth_bad_fcs_o, eth_tx_failed_o
);
  import chip_types_pkg::*;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t m_compute0_local_config_cpu_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_rsp_t m_compute0_local_config_cpu_rsp;
  assign m_compute0_local_config_cpu_rsp.b.user = '0;
  assign m_compute0_local_config_cpu_rsp.r.user = '0;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t m_compute0_local_data_cpu_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t m_compute0_local_data_cpu_rsp;
  assign m_compute0_local_data_cpu_rsp.b.user = '0;
  assign m_compute0_local_data_cpu_rsp.r.user = '0;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t m_compute0_local_data_dma_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t m_compute0_local_data_dma_rsp;
  assign m_compute0_local_data_dma_rsp.b.user = '0;
  assign m_compute0_local_data_dma_rsp.r.user = '0;
  floo_xezim_compute1_local_config_noc_pkg::axi_in_req_t m_compute1_local_config_cpu_req;
  floo_xezim_compute1_local_config_noc_pkg::axi_in_rsp_t m_compute1_local_config_cpu_rsp;
  assign m_compute1_local_config_cpu_rsp.b.user = '0;
  assign m_compute1_local_config_cpu_rsp.r.user = '0;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_req_t m_compute1_local_data_cpu_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_rsp_t m_compute1_local_data_cpu_rsp;
  assign m_compute1_local_data_cpu_rsp.b.user = '0;
  assign m_compute1_local_data_cpu_rsp.r.user = '0;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_req_t m_compute1_local_data_dma_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_rsp_t m_compute1_local_data_dma_rsp;
  assign m_compute1_local_data_dma_rsp.b.user = '0;
  assign m_compute1_local_data_dma_rsp.r.user = '0;
  floo_xezim_ethernet0_local_config_noc_pkg::axi_in_req_t m_ethernet0_local_config_management_req;
  floo_xezim_ethernet0_local_config_noc_pkg::axi_in_rsp_t m_ethernet0_local_config_management_rsp;
  assign m_ethernet0_local_config_management_rsp.b.user = '0;
  assign m_ethernet0_local_config_management_rsp.r.user = '0;
  floo_xezim_ethernet0_local_data_noc_pkg::axi_in_req_t m_ethernet0_local_data_packet_dma_req;
  floo_xezim_ethernet0_local_data_noc_pkg::axi_in_rsp_t m_ethernet0_local_data_packet_dma_rsp;
  assign m_ethernet0_local_data_packet_dma_rsp.b.user = '0;
  assign m_ethernet0_local_data_packet_dma_rsp.r.user = '0;
  floo_xezim_pcie0_local_config_noc_pkg::axi_in_req_t m_pcie0_local_config_management_req;
  floo_xezim_pcie0_local_config_noc_pkg::axi_in_rsp_t m_pcie0_local_config_management_rsp;
  assign m_pcie0_local_config_management_rsp.b.user = '0;
  assign m_pcie0_local_config_management_rsp.r.user = '0;
  floo_xezim_pcie0_local_data_noc_pkg::axi_in_req_t m_pcie0_local_data_host_req;
  floo_xezim_pcie0_local_data_noc_pkg::axi_in_rsp_t m_pcie0_local_data_host_rsp;
  assign m_pcie0_local_data_host_rsp.b.user = '0;
  assign m_pcie0_local_data_host_rsp.r.user = '0;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t s_compute0_local_config_dma_regs_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t s_compute0_local_config_dma_regs_rsp;
  assign s_compute0_local_config_dma_regs_req.aw.user = '0;
  assign s_compute0_local_config_dma_regs_req.w.user = '0;
  assign s_compute0_local_config_dma_regs_req.ar.user = '0;
  assign s_compute0_local_config_dma_regs_req.aw.atop = '0;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t s_compute0_local_config_reset_ctrl_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t s_compute0_local_config_reset_ctrl_rsp;
  assign s_compute0_local_config_reset_ctrl_req.aw.user = '0;
  assign s_compute0_local_config_reset_ctrl_req.w.user = '0;
  assign s_compute0_local_config_reset_ctrl_req.ar.user = '0;
  assign s_compute0_local_config_reset_ctrl_req.aw.atop = '0;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t s_compute0_local_data_boot_flash_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t s_compute0_local_data_boot_flash_rsp;
  assign s_compute0_local_data_boot_flash_req.aw.user = '0;
  assign s_compute0_local_data_boot_flash_req.w.user = '0;
  assign s_compute0_local_data_boot_flash_req.ar.user = '0;
  assign s_compute0_local_data_boot_flash_req.aw.atop = '0;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t s_compute0_local_data_boot_rom_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t s_compute0_local_data_boot_rom_rsp;
  assign s_compute0_local_data_boot_rom_req.aw.user = '0;
  assign s_compute0_local_data_boot_rom_req.w.user = '0;
  assign s_compute0_local_data_boot_rom_req.ar.user = '0;
  assign s_compute0_local_data_boot_rom_req.aw.atop = '0;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t s_compute0_local_data_sram_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t s_compute0_local_data_sram_rsp;
  assign s_compute0_local_data_sram_req.aw.user = '0;
  assign s_compute0_local_data_sram_req.w.user = '0;
  assign s_compute0_local_data_sram_req.ar.user = '0;
  assign s_compute0_local_data_sram_req.aw.atop = '0;
  floo_xezim_compute1_local_config_noc_pkg::axi_out_req_t s_compute1_local_config_dma_regs_req;
  floo_xezim_compute1_local_config_noc_pkg::axi_out_rsp_t s_compute1_local_config_dma_regs_rsp;
  assign s_compute1_local_config_dma_regs_req.aw.user = '0;
  assign s_compute1_local_config_dma_regs_req.w.user = '0;
  assign s_compute1_local_config_dma_regs_req.ar.user = '0;
  assign s_compute1_local_config_dma_regs_req.aw.atop = '0;
  floo_xezim_compute1_local_data_noc_pkg::axi_out_req_t s_compute1_local_data_sram_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_out_rsp_t s_compute1_local_data_sram_rsp;
  assign s_compute1_local_data_sram_req.aw.user = '0;
  assign s_compute1_local_data_sram_req.w.user = '0;
  assign s_compute1_local_data_sram_req.ar.user = '0;
  assign s_compute1_local_data_sram_req.aw.atop = '0;
  floo_xezim_ethernet0_local_config_noc_pkg::axi_out_req_t s_ethernet0_local_config_controller_regs_req;
  floo_xezim_ethernet0_local_config_noc_pkg::axi_out_rsp_t s_ethernet0_local_config_controller_regs_rsp;
  assign s_ethernet0_local_config_controller_regs_req.aw.user = '0;
  assign s_ethernet0_local_config_controller_regs_req.w.user = '0;
  assign s_ethernet0_local_config_controller_regs_req.ar.user = '0;
  assign s_ethernet0_local_config_controller_regs_req.aw.atop = '0;
  floo_xezim_ethernet0_local_data_noc_pkg::axi_out_req_t s_ethernet0_local_data_sram_req;
  floo_xezim_ethernet0_local_data_noc_pkg::axi_out_rsp_t s_ethernet0_local_data_sram_rsp;
  assign s_ethernet0_local_data_sram_req.aw.user = '0;
  assign s_ethernet0_local_data_sram_req.w.user = '0;
  assign s_ethernet0_local_data_sram_req.ar.user = '0;
  assign s_ethernet0_local_data_sram_req.aw.atop = '0;
  floo_xezim_memory0_local_config_noc_pkg::axi_out_req_t s_memory0_local_config_controller_regs_req;
  floo_xezim_memory0_local_config_noc_pkg::axi_out_rsp_t s_memory0_local_config_controller_regs_rsp;
  assign s_memory0_local_config_controller_regs_req.aw.user = '0;
  assign s_memory0_local_config_controller_regs_req.w.user = '0;
  assign s_memory0_local_config_controller_regs_req.ar.user = '0;
  assign s_memory0_local_config_controller_regs_req.aw.atop = '0;
  floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t s_memory0_local_data_target_crossbar_req;
  floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t s_memory0_local_data_target_crossbar_rsp;
  assign s_memory0_local_data_target_crossbar_req.aw.user = '0;
  assign s_memory0_local_data_target_crossbar_req.w.user = '0;
  assign s_memory0_local_data_target_crossbar_req.ar.user = '0;
  assign s_memory0_local_data_target_crossbar_req.aw.atop = '0;
  floo_xezim_pcie0_local_config_noc_pkg::axi_out_req_t s_pcie0_local_config_controller_regs_req;
  floo_xezim_pcie0_local_config_noc_pkg::axi_out_rsp_t s_pcie0_local_config_controller_regs_rsp;
  assign s_pcie0_local_config_controller_regs_req.aw.user = '0;
  assign s_pcie0_local_config_controller_regs_req.w.user = '0;
  assign s_pcie0_local_config_controller_regs_req.ar.user = '0;
  assign s_pcie0_local_config_controller_regs_req.aw.atop = '0;
  floo_xezim_pcie0_local_data_noc_pkg::axi_out_req_t s_pcie0_local_data_sram_req;
  floo_xezim_pcie0_local_data_noc_pkg::axi_out_rsp_t s_pcie0_local_data_sram_rsp;
  assign s_pcie0_local_data_sram_req.aw.user = '0;
  assign s_pcie0_local_data_sram_req.w.user = '0;
  assign s_pcie0_local_data_sram_req.ar.user = '0;
  assign s_pcie0_local_data_sram_req.aw.atop = '0;
  soc_noc u_noc (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .m_compute0_local_config_cpu_awid(m_compute0_local_config_cpu_req.aw.id),
    .m_compute0_local_config_cpu_awaddr(m_compute0_local_config_cpu_req.aw.addr),
    .m_compute0_local_config_cpu_awlen(m_compute0_local_config_cpu_req.aw.len),
    .m_compute0_local_config_cpu_awsize(m_compute0_local_config_cpu_req.aw.size),
    .m_compute0_local_config_cpu_awburst(m_compute0_local_config_cpu_req.aw.burst),
    .m_compute0_local_config_cpu_awlock(m_compute0_local_config_cpu_req.aw.lock),
    .m_compute0_local_config_cpu_awcache(m_compute0_local_config_cpu_req.aw.cache),
    .m_compute0_local_config_cpu_awprot(m_compute0_local_config_cpu_req.aw.prot),
    .m_compute0_local_config_cpu_awqos(m_compute0_local_config_cpu_req.aw.qos),
    .m_compute0_local_config_cpu_awregion(m_compute0_local_config_cpu_req.aw.region),
    .m_compute0_local_config_cpu_awvalid(m_compute0_local_config_cpu_req.aw_valid),
    .m_compute0_local_config_cpu_awready(m_compute0_local_config_cpu_rsp.aw_ready),
    .m_compute0_local_config_cpu_wdata(m_compute0_local_config_cpu_req.w.data),
    .m_compute0_local_config_cpu_wstrb(m_compute0_local_config_cpu_req.w.strb),
    .m_compute0_local_config_cpu_wlast(m_compute0_local_config_cpu_req.w.last),
    .m_compute0_local_config_cpu_wvalid(m_compute0_local_config_cpu_req.w_valid),
    .m_compute0_local_config_cpu_wready(m_compute0_local_config_cpu_rsp.w_ready),
    .m_compute0_local_config_cpu_bid(m_compute0_local_config_cpu_rsp.b.id),
    .m_compute0_local_config_cpu_bresp(m_compute0_local_config_cpu_rsp.b.resp),
    .m_compute0_local_config_cpu_bvalid(m_compute0_local_config_cpu_rsp.b_valid),
    .m_compute0_local_config_cpu_bready(m_compute0_local_config_cpu_req.b_ready),
    .m_compute0_local_config_cpu_arid(m_compute0_local_config_cpu_req.ar.id),
    .m_compute0_local_config_cpu_araddr(m_compute0_local_config_cpu_req.ar.addr),
    .m_compute0_local_config_cpu_arlen(m_compute0_local_config_cpu_req.ar.len),
    .m_compute0_local_config_cpu_arsize(m_compute0_local_config_cpu_req.ar.size),
    .m_compute0_local_config_cpu_arburst(m_compute0_local_config_cpu_req.ar.burst),
    .m_compute0_local_config_cpu_arlock(m_compute0_local_config_cpu_req.ar.lock),
    .m_compute0_local_config_cpu_arcache(m_compute0_local_config_cpu_req.ar.cache),
    .m_compute0_local_config_cpu_arprot(m_compute0_local_config_cpu_req.ar.prot),
    .m_compute0_local_config_cpu_arqos(m_compute0_local_config_cpu_req.ar.qos),
    .m_compute0_local_config_cpu_arregion(m_compute0_local_config_cpu_req.ar.region),
    .m_compute0_local_config_cpu_arvalid(m_compute0_local_config_cpu_req.ar_valid),
    .m_compute0_local_config_cpu_arready(m_compute0_local_config_cpu_rsp.ar_ready),
    .m_compute0_local_config_cpu_rid(m_compute0_local_config_cpu_rsp.r.id),
    .m_compute0_local_config_cpu_rdata(m_compute0_local_config_cpu_rsp.r.data),
    .m_compute0_local_config_cpu_rresp(m_compute0_local_config_cpu_rsp.r.resp),
    .m_compute0_local_config_cpu_rlast(m_compute0_local_config_cpu_rsp.r.last),
    .m_compute0_local_config_cpu_rvalid(m_compute0_local_config_cpu_rsp.r_valid),
    .m_compute0_local_config_cpu_rready(m_compute0_local_config_cpu_req.r_ready),
    .m_compute0_local_data_cpu_awid(m_compute0_local_data_cpu_req.aw.id),
    .m_compute0_local_data_cpu_awaddr(m_compute0_local_data_cpu_req.aw.addr),
    .m_compute0_local_data_cpu_awlen(m_compute0_local_data_cpu_req.aw.len),
    .m_compute0_local_data_cpu_awsize(m_compute0_local_data_cpu_req.aw.size),
    .m_compute0_local_data_cpu_awburst(m_compute0_local_data_cpu_req.aw.burst),
    .m_compute0_local_data_cpu_awlock(m_compute0_local_data_cpu_req.aw.lock),
    .m_compute0_local_data_cpu_awcache(m_compute0_local_data_cpu_req.aw.cache),
    .m_compute0_local_data_cpu_awprot(m_compute0_local_data_cpu_req.aw.prot),
    .m_compute0_local_data_cpu_awqos(m_compute0_local_data_cpu_req.aw.qos),
    .m_compute0_local_data_cpu_awregion(m_compute0_local_data_cpu_req.aw.region),
    .m_compute0_local_data_cpu_awvalid(m_compute0_local_data_cpu_req.aw_valid),
    .m_compute0_local_data_cpu_awready(m_compute0_local_data_cpu_rsp.aw_ready),
    .m_compute0_local_data_cpu_wdata(m_compute0_local_data_cpu_req.w.data),
    .m_compute0_local_data_cpu_wstrb(m_compute0_local_data_cpu_req.w.strb),
    .m_compute0_local_data_cpu_wlast(m_compute0_local_data_cpu_req.w.last),
    .m_compute0_local_data_cpu_wvalid(m_compute0_local_data_cpu_req.w_valid),
    .m_compute0_local_data_cpu_wready(m_compute0_local_data_cpu_rsp.w_ready),
    .m_compute0_local_data_cpu_bid(m_compute0_local_data_cpu_rsp.b.id),
    .m_compute0_local_data_cpu_bresp(m_compute0_local_data_cpu_rsp.b.resp),
    .m_compute0_local_data_cpu_bvalid(m_compute0_local_data_cpu_rsp.b_valid),
    .m_compute0_local_data_cpu_bready(m_compute0_local_data_cpu_req.b_ready),
    .m_compute0_local_data_cpu_arid(m_compute0_local_data_cpu_req.ar.id),
    .m_compute0_local_data_cpu_araddr(m_compute0_local_data_cpu_req.ar.addr),
    .m_compute0_local_data_cpu_arlen(m_compute0_local_data_cpu_req.ar.len),
    .m_compute0_local_data_cpu_arsize(m_compute0_local_data_cpu_req.ar.size),
    .m_compute0_local_data_cpu_arburst(m_compute0_local_data_cpu_req.ar.burst),
    .m_compute0_local_data_cpu_arlock(m_compute0_local_data_cpu_req.ar.lock),
    .m_compute0_local_data_cpu_arcache(m_compute0_local_data_cpu_req.ar.cache),
    .m_compute0_local_data_cpu_arprot(m_compute0_local_data_cpu_req.ar.prot),
    .m_compute0_local_data_cpu_arqos(m_compute0_local_data_cpu_req.ar.qos),
    .m_compute0_local_data_cpu_arregion(m_compute0_local_data_cpu_req.ar.region),
    .m_compute0_local_data_cpu_arvalid(m_compute0_local_data_cpu_req.ar_valid),
    .m_compute0_local_data_cpu_arready(m_compute0_local_data_cpu_rsp.ar_ready),
    .m_compute0_local_data_cpu_rid(m_compute0_local_data_cpu_rsp.r.id),
    .m_compute0_local_data_cpu_rdata(m_compute0_local_data_cpu_rsp.r.data),
    .m_compute0_local_data_cpu_rresp(m_compute0_local_data_cpu_rsp.r.resp),
    .m_compute0_local_data_cpu_rlast(m_compute0_local_data_cpu_rsp.r.last),
    .m_compute0_local_data_cpu_rvalid(m_compute0_local_data_cpu_rsp.r_valid),
    .m_compute0_local_data_cpu_rready(m_compute0_local_data_cpu_req.r_ready),
    .m_compute0_local_data_dma_awid(m_compute0_local_data_dma_req.aw.id),
    .m_compute0_local_data_dma_awaddr(m_compute0_local_data_dma_req.aw.addr),
    .m_compute0_local_data_dma_awlen(m_compute0_local_data_dma_req.aw.len),
    .m_compute0_local_data_dma_awsize(m_compute0_local_data_dma_req.aw.size),
    .m_compute0_local_data_dma_awburst(m_compute0_local_data_dma_req.aw.burst),
    .m_compute0_local_data_dma_awlock(m_compute0_local_data_dma_req.aw.lock),
    .m_compute0_local_data_dma_awcache(m_compute0_local_data_dma_req.aw.cache),
    .m_compute0_local_data_dma_awprot(m_compute0_local_data_dma_req.aw.prot),
    .m_compute0_local_data_dma_awqos(m_compute0_local_data_dma_req.aw.qos),
    .m_compute0_local_data_dma_awregion(m_compute0_local_data_dma_req.aw.region),
    .m_compute0_local_data_dma_awvalid(m_compute0_local_data_dma_req.aw_valid),
    .m_compute0_local_data_dma_awready(m_compute0_local_data_dma_rsp.aw_ready),
    .m_compute0_local_data_dma_wdata(m_compute0_local_data_dma_req.w.data),
    .m_compute0_local_data_dma_wstrb(m_compute0_local_data_dma_req.w.strb),
    .m_compute0_local_data_dma_wlast(m_compute0_local_data_dma_req.w.last),
    .m_compute0_local_data_dma_wvalid(m_compute0_local_data_dma_req.w_valid),
    .m_compute0_local_data_dma_wready(m_compute0_local_data_dma_rsp.w_ready),
    .m_compute0_local_data_dma_bid(m_compute0_local_data_dma_rsp.b.id),
    .m_compute0_local_data_dma_bresp(m_compute0_local_data_dma_rsp.b.resp),
    .m_compute0_local_data_dma_bvalid(m_compute0_local_data_dma_rsp.b_valid),
    .m_compute0_local_data_dma_bready(m_compute0_local_data_dma_req.b_ready),
    .m_compute0_local_data_dma_arid(m_compute0_local_data_dma_req.ar.id),
    .m_compute0_local_data_dma_araddr(m_compute0_local_data_dma_req.ar.addr),
    .m_compute0_local_data_dma_arlen(m_compute0_local_data_dma_req.ar.len),
    .m_compute0_local_data_dma_arsize(m_compute0_local_data_dma_req.ar.size),
    .m_compute0_local_data_dma_arburst(m_compute0_local_data_dma_req.ar.burst),
    .m_compute0_local_data_dma_arlock(m_compute0_local_data_dma_req.ar.lock),
    .m_compute0_local_data_dma_arcache(m_compute0_local_data_dma_req.ar.cache),
    .m_compute0_local_data_dma_arprot(m_compute0_local_data_dma_req.ar.prot),
    .m_compute0_local_data_dma_arqos(m_compute0_local_data_dma_req.ar.qos),
    .m_compute0_local_data_dma_arregion(m_compute0_local_data_dma_req.ar.region),
    .m_compute0_local_data_dma_arvalid(m_compute0_local_data_dma_req.ar_valid),
    .m_compute0_local_data_dma_arready(m_compute0_local_data_dma_rsp.ar_ready),
    .m_compute0_local_data_dma_rid(m_compute0_local_data_dma_rsp.r.id),
    .m_compute0_local_data_dma_rdata(m_compute0_local_data_dma_rsp.r.data),
    .m_compute0_local_data_dma_rresp(m_compute0_local_data_dma_rsp.r.resp),
    .m_compute0_local_data_dma_rlast(m_compute0_local_data_dma_rsp.r.last),
    .m_compute0_local_data_dma_rvalid(m_compute0_local_data_dma_rsp.r_valid),
    .m_compute0_local_data_dma_rready(m_compute0_local_data_dma_req.r_ready),
    .m_compute1_local_config_cpu_awid(m_compute1_local_config_cpu_req.aw.id),
    .m_compute1_local_config_cpu_awaddr(m_compute1_local_config_cpu_req.aw.addr),
    .m_compute1_local_config_cpu_awlen(m_compute1_local_config_cpu_req.aw.len),
    .m_compute1_local_config_cpu_awsize(m_compute1_local_config_cpu_req.aw.size),
    .m_compute1_local_config_cpu_awburst(m_compute1_local_config_cpu_req.aw.burst),
    .m_compute1_local_config_cpu_awlock(m_compute1_local_config_cpu_req.aw.lock),
    .m_compute1_local_config_cpu_awcache(m_compute1_local_config_cpu_req.aw.cache),
    .m_compute1_local_config_cpu_awprot(m_compute1_local_config_cpu_req.aw.prot),
    .m_compute1_local_config_cpu_awqos(m_compute1_local_config_cpu_req.aw.qos),
    .m_compute1_local_config_cpu_awregion(m_compute1_local_config_cpu_req.aw.region),
    .m_compute1_local_config_cpu_awvalid(m_compute1_local_config_cpu_req.aw_valid),
    .m_compute1_local_config_cpu_awready(m_compute1_local_config_cpu_rsp.aw_ready),
    .m_compute1_local_config_cpu_wdata(m_compute1_local_config_cpu_req.w.data),
    .m_compute1_local_config_cpu_wstrb(m_compute1_local_config_cpu_req.w.strb),
    .m_compute1_local_config_cpu_wlast(m_compute1_local_config_cpu_req.w.last),
    .m_compute1_local_config_cpu_wvalid(m_compute1_local_config_cpu_req.w_valid),
    .m_compute1_local_config_cpu_wready(m_compute1_local_config_cpu_rsp.w_ready),
    .m_compute1_local_config_cpu_bid(m_compute1_local_config_cpu_rsp.b.id),
    .m_compute1_local_config_cpu_bresp(m_compute1_local_config_cpu_rsp.b.resp),
    .m_compute1_local_config_cpu_bvalid(m_compute1_local_config_cpu_rsp.b_valid),
    .m_compute1_local_config_cpu_bready(m_compute1_local_config_cpu_req.b_ready),
    .m_compute1_local_config_cpu_arid(m_compute1_local_config_cpu_req.ar.id),
    .m_compute1_local_config_cpu_araddr(m_compute1_local_config_cpu_req.ar.addr),
    .m_compute1_local_config_cpu_arlen(m_compute1_local_config_cpu_req.ar.len),
    .m_compute1_local_config_cpu_arsize(m_compute1_local_config_cpu_req.ar.size),
    .m_compute1_local_config_cpu_arburst(m_compute1_local_config_cpu_req.ar.burst),
    .m_compute1_local_config_cpu_arlock(m_compute1_local_config_cpu_req.ar.lock),
    .m_compute1_local_config_cpu_arcache(m_compute1_local_config_cpu_req.ar.cache),
    .m_compute1_local_config_cpu_arprot(m_compute1_local_config_cpu_req.ar.prot),
    .m_compute1_local_config_cpu_arqos(m_compute1_local_config_cpu_req.ar.qos),
    .m_compute1_local_config_cpu_arregion(m_compute1_local_config_cpu_req.ar.region),
    .m_compute1_local_config_cpu_arvalid(m_compute1_local_config_cpu_req.ar_valid),
    .m_compute1_local_config_cpu_arready(m_compute1_local_config_cpu_rsp.ar_ready),
    .m_compute1_local_config_cpu_rid(m_compute1_local_config_cpu_rsp.r.id),
    .m_compute1_local_config_cpu_rdata(m_compute1_local_config_cpu_rsp.r.data),
    .m_compute1_local_config_cpu_rresp(m_compute1_local_config_cpu_rsp.r.resp),
    .m_compute1_local_config_cpu_rlast(m_compute1_local_config_cpu_rsp.r.last),
    .m_compute1_local_config_cpu_rvalid(m_compute1_local_config_cpu_rsp.r_valid),
    .m_compute1_local_config_cpu_rready(m_compute1_local_config_cpu_req.r_ready),
    .m_compute1_local_data_cpu_awid(m_compute1_local_data_cpu_req.aw.id),
    .m_compute1_local_data_cpu_awaddr(m_compute1_local_data_cpu_req.aw.addr),
    .m_compute1_local_data_cpu_awlen(m_compute1_local_data_cpu_req.aw.len),
    .m_compute1_local_data_cpu_awsize(m_compute1_local_data_cpu_req.aw.size),
    .m_compute1_local_data_cpu_awburst(m_compute1_local_data_cpu_req.aw.burst),
    .m_compute1_local_data_cpu_awlock(m_compute1_local_data_cpu_req.aw.lock),
    .m_compute1_local_data_cpu_awcache(m_compute1_local_data_cpu_req.aw.cache),
    .m_compute1_local_data_cpu_awprot(m_compute1_local_data_cpu_req.aw.prot),
    .m_compute1_local_data_cpu_awqos(m_compute1_local_data_cpu_req.aw.qos),
    .m_compute1_local_data_cpu_awregion(m_compute1_local_data_cpu_req.aw.region),
    .m_compute1_local_data_cpu_awvalid(m_compute1_local_data_cpu_req.aw_valid),
    .m_compute1_local_data_cpu_awready(m_compute1_local_data_cpu_rsp.aw_ready),
    .m_compute1_local_data_cpu_wdata(m_compute1_local_data_cpu_req.w.data),
    .m_compute1_local_data_cpu_wstrb(m_compute1_local_data_cpu_req.w.strb),
    .m_compute1_local_data_cpu_wlast(m_compute1_local_data_cpu_req.w.last),
    .m_compute1_local_data_cpu_wvalid(m_compute1_local_data_cpu_req.w_valid),
    .m_compute1_local_data_cpu_wready(m_compute1_local_data_cpu_rsp.w_ready),
    .m_compute1_local_data_cpu_bid(m_compute1_local_data_cpu_rsp.b.id),
    .m_compute1_local_data_cpu_bresp(m_compute1_local_data_cpu_rsp.b.resp),
    .m_compute1_local_data_cpu_bvalid(m_compute1_local_data_cpu_rsp.b_valid),
    .m_compute1_local_data_cpu_bready(m_compute1_local_data_cpu_req.b_ready),
    .m_compute1_local_data_cpu_arid(m_compute1_local_data_cpu_req.ar.id),
    .m_compute1_local_data_cpu_araddr(m_compute1_local_data_cpu_req.ar.addr),
    .m_compute1_local_data_cpu_arlen(m_compute1_local_data_cpu_req.ar.len),
    .m_compute1_local_data_cpu_arsize(m_compute1_local_data_cpu_req.ar.size),
    .m_compute1_local_data_cpu_arburst(m_compute1_local_data_cpu_req.ar.burst),
    .m_compute1_local_data_cpu_arlock(m_compute1_local_data_cpu_req.ar.lock),
    .m_compute1_local_data_cpu_arcache(m_compute1_local_data_cpu_req.ar.cache),
    .m_compute1_local_data_cpu_arprot(m_compute1_local_data_cpu_req.ar.prot),
    .m_compute1_local_data_cpu_arqos(m_compute1_local_data_cpu_req.ar.qos),
    .m_compute1_local_data_cpu_arregion(m_compute1_local_data_cpu_req.ar.region),
    .m_compute1_local_data_cpu_arvalid(m_compute1_local_data_cpu_req.ar_valid),
    .m_compute1_local_data_cpu_arready(m_compute1_local_data_cpu_rsp.ar_ready),
    .m_compute1_local_data_cpu_rid(m_compute1_local_data_cpu_rsp.r.id),
    .m_compute1_local_data_cpu_rdata(m_compute1_local_data_cpu_rsp.r.data),
    .m_compute1_local_data_cpu_rresp(m_compute1_local_data_cpu_rsp.r.resp),
    .m_compute1_local_data_cpu_rlast(m_compute1_local_data_cpu_rsp.r.last),
    .m_compute1_local_data_cpu_rvalid(m_compute1_local_data_cpu_rsp.r_valid),
    .m_compute1_local_data_cpu_rready(m_compute1_local_data_cpu_req.r_ready),
    .m_compute1_local_data_dma_awid(m_compute1_local_data_dma_req.aw.id),
    .m_compute1_local_data_dma_awaddr(m_compute1_local_data_dma_req.aw.addr),
    .m_compute1_local_data_dma_awlen(m_compute1_local_data_dma_req.aw.len),
    .m_compute1_local_data_dma_awsize(m_compute1_local_data_dma_req.aw.size),
    .m_compute1_local_data_dma_awburst(m_compute1_local_data_dma_req.aw.burst),
    .m_compute1_local_data_dma_awlock(m_compute1_local_data_dma_req.aw.lock),
    .m_compute1_local_data_dma_awcache(m_compute1_local_data_dma_req.aw.cache),
    .m_compute1_local_data_dma_awprot(m_compute1_local_data_dma_req.aw.prot),
    .m_compute1_local_data_dma_awqos(m_compute1_local_data_dma_req.aw.qos),
    .m_compute1_local_data_dma_awregion(m_compute1_local_data_dma_req.aw.region),
    .m_compute1_local_data_dma_awvalid(m_compute1_local_data_dma_req.aw_valid),
    .m_compute1_local_data_dma_awready(m_compute1_local_data_dma_rsp.aw_ready),
    .m_compute1_local_data_dma_wdata(m_compute1_local_data_dma_req.w.data),
    .m_compute1_local_data_dma_wstrb(m_compute1_local_data_dma_req.w.strb),
    .m_compute1_local_data_dma_wlast(m_compute1_local_data_dma_req.w.last),
    .m_compute1_local_data_dma_wvalid(m_compute1_local_data_dma_req.w_valid),
    .m_compute1_local_data_dma_wready(m_compute1_local_data_dma_rsp.w_ready),
    .m_compute1_local_data_dma_bid(m_compute1_local_data_dma_rsp.b.id),
    .m_compute1_local_data_dma_bresp(m_compute1_local_data_dma_rsp.b.resp),
    .m_compute1_local_data_dma_bvalid(m_compute1_local_data_dma_rsp.b_valid),
    .m_compute1_local_data_dma_bready(m_compute1_local_data_dma_req.b_ready),
    .m_compute1_local_data_dma_arid(m_compute1_local_data_dma_req.ar.id),
    .m_compute1_local_data_dma_araddr(m_compute1_local_data_dma_req.ar.addr),
    .m_compute1_local_data_dma_arlen(m_compute1_local_data_dma_req.ar.len),
    .m_compute1_local_data_dma_arsize(m_compute1_local_data_dma_req.ar.size),
    .m_compute1_local_data_dma_arburst(m_compute1_local_data_dma_req.ar.burst),
    .m_compute1_local_data_dma_arlock(m_compute1_local_data_dma_req.ar.lock),
    .m_compute1_local_data_dma_arcache(m_compute1_local_data_dma_req.ar.cache),
    .m_compute1_local_data_dma_arprot(m_compute1_local_data_dma_req.ar.prot),
    .m_compute1_local_data_dma_arqos(m_compute1_local_data_dma_req.ar.qos),
    .m_compute1_local_data_dma_arregion(m_compute1_local_data_dma_req.ar.region),
    .m_compute1_local_data_dma_arvalid(m_compute1_local_data_dma_req.ar_valid),
    .m_compute1_local_data_dma_arready(m_compute1_local_data_dma_rsp.ar_ready),
    .m_compute1_local_data_dma_rid(m_compute1_local_data_dma_rsp.r.id),
    .m_compute1_local_data_dma_rdata(m_compute1_local_data_dma_rsp.r.data),
    .m_compute1_local_data_dma_rresp(m_compute1_local_data_dma_rsp.r.resp),
    .m_compute1_local_data_dma_rlast(m_compute1_local_data_dma_rsp.r.last),
    .m_compute1_local_data_dma_rvalid(m_compute1_local_data_dma_rsp.r_valid),
    .m_compute1_local_data_dma_rready(m_compute1_local_data_dma_req.r_ready),
    .m_ethernet0_local_config_management_awid(m_ethernet0_local_config_management_req.aw.id),
    .m_ethernet0_local_config_management_awaddr(m_ethernet0_local_config_management_req.aw.addr),
    .m_ethernet0_local_config_management_awlen(m_ethernet0_local_config_management_req.aw.len),
    .m_ethernet0_local_config_management_awsize(m_ethernet0_local_config_management_req.aw.size),
    .m_ethernet0_local_config_management_awburst(m_ethernet0_local_config_management_req.aw.burst),
    .m_ethernet0_local_config_management_awlock(m_ethernet0_local_config_management_req.aw.lock),
    .m_ethernet0_local_config_management_awcache(m_ethernet0_local_config_management_req.aw.cache),
    .m_ethernet0_local_config_management_awprot(m_ethernet0_local_config_management_req.aw.prot),
    .m_ethernet0_local_config_management_awqos(m_ethernet0_local_config_management_req.aw.qos),
    .m_ethernet0_local_config_management_awregion(m_ethernet0_local_config_management_req.aw.region),
    .m_ethernet0_local_config_management_awvalid(m_ethernet0_local_config_management_req.aw_valid),
    .m_ethernet0_local_config_management_awready(m_ethernet0_local_config_management_rsp.aw_ready),
    .m_ethernet0_local_config_management_wdata(m_ethernet0_local_config_management_req.w.data),
    .m_ethernet0_local_config_management_wstrb(m_ethernet0_local_config_management_req.w.strb),
    .m_ethernet0_local_config_management_wlast(m_ethernet0_local_config_management_req.w.last),
    .m_ethernet0_local_config_management_wvalid(m_ethernet0_local_config_management_req.w_valid),
    .m_ethernet0_local_config_management_wready(m_ethernet0_local_config_management_rsp.w_ready),
    .m_ethernet0_local_config_management_bid(m_ethernet0_local_config_management_rsp.b.id),
    .m_ethernet0_local_config_management_bresp(m_ethernet0_local_config_management_rsp.b.resp),
    .m_ethernet0_local_config_management_bvalid(m_ethernet0_local_config_management_rsp.b_valid),
    .m_ethernet0_local_config_management_bready(m_ethernet0_local_config_management_req.b_ready),
    .m_ethernet0_local_config_management_arid(m_ethernet0_local_config_management_req.ar.id),
    .m_ethernet0_local_config_management_araddr(m_ethernet0_local_config_management_req.ar.addr),
    .m_ethernet0_local_config_management_arlen(m_ethernet0_local_config_management_req.ar.len),
    .m_ethernet0_local_config_management_arsize(m_ethernet0_local_config_management_req.ar.size),
    .m_ethernet0_local_config_management_arburst(m_ethernet0_local_config_management_req.ar.burst),
    .m_ethernet0_local_config_management_arlock(m_ethernet0_local_config_management_req.ar.lock),
    .m_ethernet0_local_config_management_arcache(m_ethernet0_local_config_management_req.ar.cache),
    .m_ethernet0_local_config_management_arprot(m_ethernet0_local_config_management_req.ar.prot),
    .m_ethernet0_local_config_management_arqos(m_ethernet0_local_config_management_req.ar.qos),
    .m_ethernet0_local_config_management_arregion(m_ethernet0_local_config_management_req.ar.region),
    .m_ethernet0_local_config_management_arvalid(m_ethernet0_local_config_management_req.ar_valid),
    .m_ethernet0_local_config_management_arready(m_ethernet0_local_config_management_rsp.ar_ready),
    .m_ethernet0_local_config_management_rid(m_ethernet0_local_config_management_rsp.r.id),
    .m_ethernet0_local_config_management_rdata(m_ethernet0_local_config_management_rsp.r.data),
    .m_ethernet0_local_config_management_rresp(m_ethernet0_local_config_management_rsp.r.resp),
    .m_ethernet0_local_config_management_rlast(m_ethernet0_local_config_management_rsp.r.last),
    .m_ethernet0_local_config_management_rvalid(m_ethernet0_local_config_management_rsp.r_valid),
    .m_ethernet0_local_config_management_rready(m_ethernet0_local_config_management_req.r_ready),
    .m_ethernet0_local_data_packet_dma_awid(m_ethernet0_local_data_packet_dma_req.aw.id),
    .m_ethernet0_local_data_packet_dma_awaddr(m_ethernet0_local_data_packet_dma_req.aw.addr),
    .m_ethernet0_local_data_packet_dma_awlen(m_ethernet0_local_data_packet_dma_req.aw.len),
    .m_ethernet0_local_data_packet_dma_awsize(m_ethernet0_local_data_packet_dma_req.aw.size),
    .m_ethernet0_local_data_packet_dma_awburst(m_ethernet0_local_data_packet_dma_req.aw.burst),
    .m_ethernet0_local_data_packet_dma_awlock(m_ethernet0_local_data_packet_dma_req.aw.lock),
    .m_ethernet0_local_data_packet_dma_awcache(m_ethernet0_local_data_packet_dma_req.aw.cache),
    .m_ethernet0_local_data_packet_dma_awprot(m_ethernet0_local_data_packet_dma_req.aw.prot),
    .m_ethernet0_local_data_packet_dma_awqos(m_ethernet0_local_data_packet_dma_req.aw.qos),
    .m_ethernet0_local_data_packet_dma_awregion(m_ethernet0_local_data_packet_dma_req.aw.region),
    .m_ethernet0_local_data_packet_dma_awvalid(m_ethernet0_local_data_packet_dma_req.aw_valid),
    .m_ethernet0_local_data_packet_dma_awready(m_ethernet0_local_data_packet_dma_rsp.aw_ready),
    .m_ethernet0_local_data_packet_dma_wdata(m_ethernet0_local_data_packet_dma_req.w.data),
    .m_ethernet0_local_data_packet_dma_wstrb(m_ethernet0_local_data_packet_dma_req.w.strb),
    .m_ethernet0_local_data_packet_dma_wlast(m_ethernet0_local_data_packet_dma_req.w.last),
    .m_ethernet0_local_data_packet_dma_wvalid(m_ethernet0_local_data_packet_dma_req.w_valid),
    .m_ethernet0_local_data_packet_dma_wready(m_ethernet0_local_data_packet_dma_rsp.w_ready),
    .m_ethernet0_local_data_packet_dma_bid(m_ethernet0_local_data_packet_dma_rsp.b.id),
    .m_ethernet0_local_data_packet_dma_bresp(m_ethernet0_local_data_packet_dma_rsp.b.resp),
    .m_ethernet0_local_data_packet_dma_bvalid(m_ethernet0_local_data_packet_dma_rsp.b_valid),
    .m_ethernet0_local_data_packet_dma_bready(m_ethernet0_local_data_packet_dma_req.b_ready),
    .m_ethernet0_local_data_packet_dma_arid(m_ethernet0_local_data_packet_dma_req.ar.id),
    .m_ethernet0_local_data_packet_dma_araddr(m_ethernet0_local_data_packet_dma_req.ar.addr),
    .m_ethernet0_local_data_packet_dma_arlen(m_ethernet0_local_data_packet_dma_req.ar.len),
    .m_ethernet0_local_data_packet_dma_arsize(m_ethernet0_local_data_packet_dma_req.ar.size),
    .m_ethernet0_local_data_packet_dma_arburst(m_ethernet0_local_data_packet_dma_req.ar.burst),
    .m_ethernet0_local_data_packet_dma_arlock(m_ethernet0_local_data_packet_dma_req.ar.lock),
    .m_ethernet0_local_data_packet_dma_arcache(m_ethernet0_local_data_packet_dma_req.ar.cache),
    .m_ethernet0_local_data_packet_dma_arprot(m_ethernet0_local_data_packet_dma_req.ar.prot),
    .m_ethernet0_local_data_packet_dma_arqos(m_ethernet0_local_data_packet_dma_req.ar.qos),
    .m_ethernet0_local_data_packet_dma_arregion(m_ethernet0_local_data_packet_dma_req.ar.region),
    .m_ethernet0_local_data_packet_dma_arvalid(m_ethernet0_local_data_packet_dma_req.ar_valid),
    .m_ethernet0_local_data_packet_dma_arready(m_ethernet0_local_data_packet_dma_rsp.ar_ready),
    .m_ethernet0_local_data_packet_dma_rid(m_ethernet0_local_data_packet_dma_rsp.r.id),
    .m_ethernet0_local_data_packet_dma_rdata(m_ethernet0_local_data_packet_dma_rsp.r.data),
    .m_ethernet0_local_data_packet_dma_rresp(m_ethernet0_local_data_packet_dma_rsp.r.resp),
    .m_ethernet0_local_data_packet_dma_rlast(m_ethernet0_local_data_packet_dma_rsp.r.last),
    .m_ethernet0_local_data_packet_dma_rvalid(m_ethernet0_local_data_packet_dma_rsp.r_valid),
    .m_ethernet0_local_data_packet_dma_rready(m_ethernet0_local_data_packet_dma_req.r_ready),
    .m_pcie0_local_config_management_awid(m_pcie0_local_config_management_req.aw.id),
    .m_pcie0_local_config_management_awaddr(m_pcie0_local_config_management_req.aw.addr),
    .m_pcie0_local_config_management_awlen(m_pcie0_local_config_management_req.aw.len),
    .m_pcie0_local_config_management_awsize(m_pcie0_local_config_management_req.aw.size),
    .m_pcie0_local_config_management_awburst(m_pcie0_local_config_management_req.aw.burst),
    .m_pcie0_local_config_management_awlock(m_pcie0_local_config_management_req.aw.lock),
    .m_pcie0_local_config_management_awcache(m_pcie0_local_config_management_req.aw.cache),
    .m_pcie0_local_config_management_awprot(m_pcie0_local_config_management_req.aw.prot),
    .m_pcie0_local_config_management_awqos(m_pcie0_local_config_management_req.aw.qos),
    .m_pcie0_local_config_management_awregion(m_pcie0_local_config_management_req.aw.region),
    .m_pcie0_local_config_management_awvalid(m_pcie0_local_config_management_req.aw_valid),
    .m_pcie0_local_config_management_awready(m_pcie0_local_config_management_rsp.aw_ready),
    .m_pcie0_local_config_management_wdata(m_pcie0_local_config_management_req.w.data),
    .m_pcie0_local_config_management_wstrb(m_pcie0_local_config_management_req.w.strb),
    .m_pcie0_local_config_management_wlast(m_pcie0_local_config_management_req.w.last),
    .m_pcie0_local_config_management_wvalid(m_pcie0_local_config_management_req.w_valid),
    .m_pcie0_local_config_management_wready(m_pcie0_local_config_management_rsp.w_ready),
    .m_pcie0_local_config_management_bid(m_pcie0_local_config_management_rsp.b.id),
    .m_pcie0_local_config_management_bresp(m_pcie0_local_config_management_rsp.b.resp),
    .m_pcie0_local_config_management_bvalid(m_pcie0_local_config_management_rsp.b_valid),
    .m_pcie0_local_config_management_bready(m_pcie0_local_config_management_req.b_ready),
    .m_pcie0_local_config_management_arid(m_pcie0_local_config_management_req.ar.id),
    .m_pcie0_local_config_management_araddr(m_pcie0_local_config_management_req.ar.addr),
    .m_pcie0_local_config_management_arlen(m_pcie0_local_config_management_req.ar.len),
    .m_pcie0_local_config_management_arsize(m_pcie0_local_config_management_req.ar.size),
    .m_pcie0_local_config_management_arburst(m_pcie0_local_config_management_req.ar.burst),
    .m_pcie0_local_config_management_arlock(m_pcie0_local_config_management_req.ar.lock),
    .m_pcie0_local_config_management_arcache(m_pcie0_local_config_management_req.ar.cache),
    .m_pcie0_local_config_management_arprot(m_pcie0_local_config_management_req.ar.prot),
    .m_pcie0_local_config_management_arqos(m_pcie0_local_config_management_req.ar.qos),
    .m_pcie0_local_config_management_arregion(m_pcie0_local_config_management_req.ar.region),
    .m_pcie0_local_config_management_arvalid(m_pcie0_local_config_management_req.ar_valid),
    .m_pcie0_local_config_management_arready(m_pcie0_local_config_management_rsp.ar_ready),
    .m_pcie0_local_config_management_rid(m_pcie0_local_config_management_rsp.r.id),
    .m_pcie0_local_config_management_rdata(m_pcie0_local_config_management_rsp.r.data),
    .m_pcie0_local_config_management_rresp(m_pcie0_local_config_management_rsp.r.resp),
    .m_pcie0_local_config_management_rlast(m_pcie0_local_config_management_rsp.r.last),
    .m_pcie0_local_config_management_rvalid(m_pcie0_local_config_management_rsp.r_valid),
    .m_pcie0_local_config_management_rready(m_pcie0_local_config_management_req.r_ready),
    .m_pcie0_local_data_host_awid(m_pcie0_local_data_host_req.aw.id),
    .m_pcie0_local_data_host_awaddr(m_pcie0_local_data_host_req.aw.addr),
    .m_pcie0_local_data_host_awlen(m_pcie0_local_data_host_req.aw.len),
    .m_pcie0_local_data_host_awsize(m_pcie0_local_data_host_req.aw.size),
    .m_pcie0_local_data_host_awburst(m_pcie0_local_data_host_req.aw.burst),
    .m_pcie0_local_data_host_awlock(m_pcie0_local_data_host_req.aw.lock),
    .m_pcie0_local_data_host_awcache(m_pcie0_local_data_host_req.aw.cache),
    .m_pcie0_local_data_host_awprot(m_pcie0_local_data_host_req.aw.prot),
    .m_pcie0_local_data_host_awqos(m_pcie0_local_data_host_req.aw.qos),
    .m_pcie0_local_data_host_awregion(m_pcie0_local_data_host_req.aw.region),
    .m_pcie0_local_data_host_awvalid(m_pcie0_local_data_host_req.aw_valid),
    .m_pcie0_local_data_host_awready(m_pcie0_local_data_host_rsp.aw_ready),
    .m_pcie0_local_data_host_wdata(m_pcie0_local_data_host_req.w.data),
    .m_pcie0_local_data_host_wstrb(m_pcie0_local_data_host_req.w.strb),
    .m_pcie0_local_data_host_wlast(m_pcie0_local_data_host_req.w.last),
    .m_pcie0_local_data_host_wvalid(m_pcie0_local_data_host_req.w_valid),
    .m_pcie0_local_data_host_wready(m_pcie0_local_data_host_rsp.w_ready),
    .m_pcie0_local_data_host_bid(m_pcie0_local_data_host_rsp.b.id),
    .m_pcie0_local_data_host_bresp(m_pcie0_local_data_host_rsp.b.resp),
    .m_pcie0_local_data_host_bvalid(m_pcie0_local_data_host_rsp.b_valid),
    .m_pcie0_local_data_host_bready(m_pcie0_local_data_host_req.b_ready),
    .m_pcie0_local_data_host_arid(m_pcie0_local_data_host_req.ar.id),
    .m_pcie0_local_data_host_araddr(m_pcie0_local_data_host_req.ar.addr),
    .m_pcie0_local_data_host_arlen(m_pcie0_local_data_host_req.ar.len),
    .m_pcie0_local_data_host_arsize(m_pcie0_local_data_host_req.ar.size),
    .m_pcie0_local_data_host_arburst(m_pcie0_local_data_host_req.ar.burst),
    .m_pcie0_local_data_host_arlock(m_pcie0_local_data_host_req.ar.lock),
    .m_pcie0_local_data_host_arcache(m_pcie0_local_data_host_req.ar.cache),
    .m_pcie0_local_data_host_arprot(m_pcie0_local_data_host_req.ar.prot),
    .m_pcie0_local_data_host_arqos(m_pcie0_local_data_host_req.ar.qos),
    .m_pcie0_local_data_host_arregion(m_pcie0_local_data_host_req.ar.region),
    .m_pcie0_local_data_host_arvalid(m_pcie0_local_data_host_req.ar_valid),
    .m_pcie0_local_data_host_arready(m_pcie0_local_data_host_rsp.ar_ready),
    .m_pcie0_local_data_host_rid(m_pcie0_local_data_host_rsp.r.id),
    .m_pcie0_local_data_host_rdata(m_pcie0_local_data_host_rsp.r.data),
    .m_pcie0_local_data_host_rresp(m_pcie0_local_data_host_rsp.r.resp),
    .m_pcie0_local_data_host_rlast(m_pcie0_local_data_host_rsp.r.last),
    .m_pcie0_local_data_host_rvalid(m_pcie0_local_data_host_rsp.r_valid),
    .m_pcie0_local_data_host_rready(m_pcie0_local_data_host_req.r_ready),
    .s_compute0_local_config_dma_regs_awid(s_compute0_local_config_dma_regs_req.aw.id),
    .s_compute0_local_config_dma_regs_awaddr(s_compute0_local_config_dma_regs_req.aw.addr),
    .s_compute0_local_config_dma_regs_awlen(s_compute0_local_config_dma_regs_req.aw.len),
    .s_compute0_local_config_dma_regs_awsize(s_compute0_local_config_dma_regs_req.aw.size),
    .s_compute0_local_config_dma_regs_awburst(s_compute0_local_config_dma_regs_req.aw.burst),
    .s_compute0_local_config_dma_regs_awlock(s_compute0_local_config_dma_regs_req.aw.lock),
    .s_compute0_local_config_dma_regs_awcache(s_compute0_local_config_dma_regs_req.aw.cache),
    .s_compute0_local_config_dma_regs_awprot(s_compute0_local_config_dma_regs_req.aw.prot),
    .s_compute0_local_config_dma_regs_awqos(s_compute0_local_config_dma_regs_req.aw.qos),
    .s_compute0_local_config_dma_regs_awregion(s_compute0_local_config_dma_regs_req.aw.region),
    .s_compute0_local_config_dma_regs_awvalid(s_compute0_local_config_dma_regs_req.aw_valid),
    .s_compute0_local_config_dma_regs_awready(s_compute0_local_config_dma_regs_rsp.aw_ready),
    .s_compute0_local_config_dma_regs_wdata(s_compute0_local_config_dma_regs_req.w.data),
    .s_compute0_local_config_dma_regs_wstrb(s_compute0_local_config_dma_regs_req.w.strb),
    .s_compute0_local_config_dma_regs_wlast(s_compute0_local_config_dma_regs_req.w.last),
    .s_compute0_local_config_dma_regs_wvalid(s_compute0_local_config_dma_regs_req.w_valid),
    .s_compute0_local_config_dma_regs_wready(s_compute0_local_config_dma_regs_rsp.w_ready),
    .s_compute0_local_config_dma_regs_bid(s_compute0_local_config_dma_regs_rsp.b.id),
    .s_compute0_local_config_dma_regs_bresp(s_compute0_local_config_dma_regs_rsp.b.resp),
    .s_compute0_local_config_dma_regs_bvalid(s_compute0_local_config_dma_regs_rsp.b_valid),
    .s_compute0_local_config_dma_regs_bready(s_compute0_local_config_dma_regs_req.b_ready),
    .s_compute0_local_config_dma_regs_arid(s_compute0_local_config_dma_regs_req.ar.id),
    .s_compute0_local_config_dma_regs_araddr(s_compute0_local_config_dma_regs_req.ar.addr),
    .s_compute0_local_config_dma_regs_arlen(s_compute0_local_config_dma_regs_req.ar.len),
    .s_compute0_local_config_dma_regs_arsize(s_compute0_local_config_dma_regs_req.ar.size),
    .s_compute0_local_config_dma_regs_arburst(s_compute0_local_config_dma_regs_req.ar.burst),
    .s_compute0_local_config_dma_regs_arlock(s_compute0_local_config_dma_regs_req.ar.lock),
    .s_compute0_local_config_dma_regs_arcache(s_compute0_local_config_dma_regs_req.ar.cache),
    .s_compute0_local_config_dma_regs_arprot(s_compute0_local_config_dma_regs_req.ar.prot),
    .s_compute0_local_config_dma_regs_arqos(s_compute0_local_config_dma_regs_req.ar.qos),
    .s_compute0_local_config_dma_regs_arregion(s_compute0_local_config_dma_regs_req.ar.region),
    .s_compute0_local_config_dma_regs_arvalid(s_compute0_local_config_dma_regs_req.ar_valid),
    .s_compute0_local_config_dma_regs_arready(s_compute0_local_config_dma_regs_rsp.ar_ready),
    .s_compute0_local_config_dma_regs_rid(s_compute0_local_config_dma_regs_rsp.r.id),
    .s_compute0_local_config_dma_regs_rdata(s_compute0_local_config_dma_regs_rsp.r.data),
    .s_compute0_local_config_dma_regs_rresp(s_compute0_local_config_dma_regs_rsp.r.resp),
    .s_compute0_local_config_dma_regs_rlast(s_compute0_local_config_dma_regs_rsp.r.last),
    .s_compute0_local_config_dma_regs_rvalid(s_compute0_local_config_dma_regs_rsp.r_valid),
    .s_compute0_local_config_dma_regs_rready(s_compute0_local_config_dma_regs_req.r_ready),
    .s_compute0_local_config_reset_ctrl_awid(s_compute0_local_config_reset_ctrl_req.aw.id),
    .s_compute0_local_config_reset_ctrl_awaddr(s_compute0_local_config_reset_ctrl_req.aw.addr),
    .s_compute0_local_config_reset_ctrl_awlen(s_compute0_local_config_reset_ctrl_req.aw.len),
    .s_compute0_local_config_reset_ctrl_awsize(s_compute0_local_config_reset_ctrl_req.aw.size),
    .s_compute0_local_config_reset_ctrl_awburst(s_compute0_local_config_reset_ctrl_req.aw.burst),
    .s_compute0_local_config_reset_ctrl_awlock(s_compute0_local_config_reset_ctrl_req.aw.lock),
    .s_compute0_local_config_reset_ctrl_awcache(s_compute0_local_config_reset_ctrl_req.aw.cache),
    .s_compute0_local_config_reset_ctrl_awprot(s_compute0_local_config_reset_ctrl_req.aw.prot),
    .s_compute0_local_config_reset_ctrl_awqos(s_compute0_local_config_reset_ctrl_req.aw.qos),
    .s_compute0_local_config_reset_ctrl_awregion(s_compute0_local_config_reset_ctrl_req.aw.region),
    .s_compute0_local_config_reset_ctrl_awvalid(s_compute0_local_config_reset_ctrl_req.aw_valid),
    .s_compute0_local_config_reset_ctrl_awready(s_compute0_local_config_reset_ctrl_rsp.aw_ready),
    .s_compute0_local_config_reset_ctrl_wdata(s_compute0_local_config_reset_ctrl_req.w.data),
    .s_compute0_local_config_reset_ctrl_wstrb(s_compute0_local_config_reset_ctrl_req.w.strb),
    .s_compute0_local_config_reset_ctrl_wlast(s_compute0_local_config_reset_ctrl_req.w.last),
    .s_compute0_local_config_reset_ctrl_wvalid(s_compute0_local_config_reset_ctrl_req.w_valid),
    .s_compute0_local_config_reset_ctrl_wready(s_compute0_local_config_reset_ctrl_rsp.w_ready),
    .s_compute0_local_config_reset_ctrl_bid(s_compute0_local_config_reset_ctrl_rsp.b.id),
    .s_compute0_local_config_reset_ctrl_bresp(s_compute0_local_config_reset_ctrl_rsp.b.resp),
    .s_compute0_local_config_reset_ctrl_bvalid(s_compute0_local_config_reset_ctrl_rsp.b_valid),
    .s_compute0_local_config_reset_ctrl_bready(s_compute0_local_config_reset_ctrl_req.b_ready),
    .s_compute0_local_config_reset_ctrl_arid(s_compute0_local_config_reset_ctrl_req.ar.id),
    .s_compute0_local_config_reset_ctrl_araddr(s_compute0_local_config_reset_ctrl_req.ar.addr),
    .s_compute0_local_config_reset_ctrl_arlen(s_compute0_local_config_reset_ctrl_req.ar.len),
    .s_compute0_local_config_reset_ctrl_arsize(s_compute0_local_config_reset_ctrl_req.ar.size),
    .s_compute0_local_config_reset_ctrl_arburst(s_compute0_local_config_reset_ctrl_req.ar.burst),
    .s_compute0_local_config_reset_ctrl_arlock(s_compute0_local_config_reset_ctrl_req.ar.lock),
    .s_compute0_local_config_reset_ctrl_arcache(s_compute0_local_config_reset_ctrl_req.ar.cache),
    .s_compute0_local_config_reset_ctrl_arprot(s_compute0_local_config_reset_ctrl_req.ar.prot),
    .s_compute0_local_config_reset_ctrl_arqos(s_compute0_local_config_reset_ctrl_req.ar.qos),
    .s_compute0_local_config_reset_ctrl_arregion(s_compute0_local_config_reset_ctrl_req.ar.region),
    .s_compute0_local_config_reset_ctrl_arvalid(s_compute0_local_config_reset_ctrl_req.ar_valid),
    .s_compute0_local_config_reset_ctrl_arready(s_compute0_local_config_reset_ctrl_rsp.ar_ready),
    .s_compute0_local_config_reset_ctrl_rid(s_compute0_local_config_reset_ctrl_rsp.r.id),
    .s_compute0_local_config_reset_ctrl_rdata(s_compute0_local_config_reset_ctrl_rsp.r.data),
    .s_compute0_local_config_reset_ctrl_rresp(s_compute0_local_config_reset_ctrl_rsp.r.resp),
    .s_compute0_local_config_reset_ctrl_rlast(s_compute0_local_config_reset_ctrl_rsp.r.last),
    .s_compute0_local_config_reset_ctrl_rvalid(s_compute0_local_config_reset_ctrl_rsp.r_valid),
    .s_compute0_local_config_reset_ctrl_rready(s_compute0_local_config_reset_ctrl_req.r_ready),
    .s_compute0_local_data_boot_flash_awid(s_compute0_local_data_boot_flash_req.aw.id),
    .s_compute0_local_data_boot_flash_awaddr(s_compute0_local_data_boot_flash_req.aw.addr),
    .s_compute0_local_data_boot_flash_awlen(s_compute0_local_data_boot_flash_req.aw.len),
    .s_compute0_local_data_boot_flash_awsize(s_compute0_local_data_boot_flash_req.aw.size),
    .s_compute0_local_data_boot_flash_awburst(s_compute0_local_data_boot_flash_req.aw.burst),
    .s_compute0_local_data_boot_flash_awlock(s_compute0_local_data_boot_flash_req.aw.lock),
    .s_compute0_local_data_boot_flash_awcache(s_compute0_local_data_boot_flash_req.aw.cache),
    .s_compute0_local_data_boot_flash_awprot(s_compute0_local_data_boot_flash_req.aw.prot),
    .s_compute0_local_data_boot_flash_awqos(s_compute0_local_data_boot_flash_req.aw.qos),
    .s_compute0_local_data_boot_flash_awregion(s_compute0_local_data_boot_flash_req.aw.region),
    .s_compute0_local_data_boot_flash_awvalid(s_compute0_local_data_boot_flash_req.aw_valid),
    .s_compute0_local_data_boot_flash_awready(s_compute0_local_data_boot_flash_rsp.aw_ready),
    .s_compute0_local_data_boot_flash_wdata(s_compute0_local_data_boot_flash_req.w.data),
    .s_compute0_local_data_boot_flash_wstrb(s_compute0_local_data_boot_flash_req.w.strb),
    .s_compute0_local_data_boot_flash_wlast(s_compute0_local_data_boot_flash_req.w.last),
    .s_compute0_local_data_boot_flash_wvalid(s_compute0_local_data_boot_flash_req.w_valid),
    .s_compute0_local_data_boot_flash_wready(s_compute0_local_data_boot_flash_rsp.w_ready),
    .s_compute0_local_data_boot_flash_bid(s_compute0_local_data_boot_flash_rsp.b.id),
    .s_compute0_local_data_boot_flash_bresp(s_compute0_local_data_boot_flash_rsp.b.resp),
    .s_compute0_local_data_boot_flash_bvalid(s_compute0_local_data_boot_flash_rsp.b_valid),
    .s_compute0_local_data_boot_flash_bready(s_compute0_local_data_boot_flash_req.b_ready),
    .s_compute0_local_data_boot_flash_arid(s_compute0_local_data_boot_flash_req.ar.id),
    .s_compute0_local_data_boot_flash_araddr(s_compute0_local_data_boot_flash_req.ar.addr),
    .s_compute0_local_data_boot_flash_arlen(s_compute0_local_data_boot_flash_req.ar.len),
    .s_compute0_local_data_boot_flash_arsize(s_compute0_local_data_boot_flash_req.ar.size),
    .s_compute0_local_data_boot_flash_arburst(s_compute0_local_data_boot_flash_req.ar.burst),
    .s_compute0_local_data_boot_flash_arlock(s_compute0_local_data_boot_flash_req.ar.lock),
    .s_compute0_local_data_boot_flash_arcache(s_compute0_local_data_boot_flash_req.ar.cache),
    .s_compute0_local_data_boot_flash_arprot(s_compute0_local_data_boot_flash_req.ar.prot),
    .s_compute0_local_data_boot_flash_arqos(s_compute0_local_data_boot_flash_req.ar.qos),
    .s_compute0_local_data_boot_flash_arregion(s_compute0_local_data_boot_flash_req.ar.region),
    .s_compute0_local_data_boot_flash_arvalid(s_compute0_local_data_boot_flash_req.ar_valid),
    .s_compute0_local_data_boot_flash_arready(s_compute0_local_data_boot_flash_rsp.ar_ready),
    .s_compute0_local_data_boot_flash_rid(s_compute0_local_data_boot_flash_rsp.r.id),
    .s_compute0_local_data_boot_flash_rdata(s_compute0_local_data_boot_flash_rsp.r.data),
    .s_compute0_local_data_boot_flash_rresp(s_compute0_local_data_boot_flash_rsp.r.resp),
    .s_compute0_local_data_boot_flash_rlast(s_compute0_local_data_boot_flash_rsp.r.last),
    .s_compute0_local_data_boot_flash_rvalid(s_compute0_local_data_boot_flash_rsp.r_valid),
    .s_compute0_local_data_boot_flash_rready(s_compute0_local_data_boot_flash_req.r_ready),
    .s_compute0_local_data_boot_rom_awid(s_compute0_local_data_boot_rom_req.aw.id),
    .s_compute0_local_data_boot_rom_awaddr(s_compute0_local_data_boot_rom_req.aw.addr),
    .s_compute0_local_data_boot_rom_awlen(s_compute0_local_data_boot_rom_req.aw.len),
    .s_compute0_local_data_boot_rom_awsize(s_compute0_local_data_boot_rom_req.aw.size),
    .s_compute0_local_data_boot_rom_awburst(s_compute0_local_data_boot_rom_req.aw.burst),
    .s_compute0_local_data_boot_rom_awlock(s_compute0_local_data_boot_rom_req.aw.lock),
    .s_compute0_local_data_boot_rom_awcache(s_compute0_local_data_boot_rom_req.aw.cache),
    .s_compute0_local_data_boot_rom_awprot(s_compute0_local_data_boot_rom_req.aw.prot),
    .s_compute0_local_data_boot_rom_awqos(s_compute0_local_data_boot_rom_req.aw.qos),
    .s_compute0_local_data_boot_rom_awregion(s_compute0_local_data_boot_rom_req.aw.region),
    .s_compute0_local_data_boot_rom_awvalid(s_compute0_local_data_boot_rom_req.aw_valid),
    .s_compute0_local_data_boot_rom_awready(s_compute0_local_data_boot_rom_rsp.aw_ready),
    .s_compute0_local_data_boot_rom_wdata(s_compute0_local_data_boot_rom_req.w.data),
    .s_compute0_local_data_boot_rom_wstrb(s_compute0_local_data_boot_rom_req.w.strb),
    .s_compute0_local_data_boot_rom_wlast(s_compute0_local_data_boot_rom_req.w.last),
    .s_compute0_local_data_boot_rom_wvalid(s_compute0_local_data_boot_rom_req.w_valid),
    .s_compute0_local_data_boot_rom_wready(s_compute0_local_data_boot_rom_rsp.w_ready),
    .s_compute0_local_data_boot_rom_bid(s_compute0_local_data_boot_rom_rsp.b.id),
    .s_compute0_local_data_boot_rom_bresp(s_compute0_local_data_boot_rom_rsp.b.resp),
    .s_compute0_local_data_boot_rom_bvalid(s_compute0_local_data_boot_rom_rsp.b_valid),
    .s_compute0_local_data_boot_rom_bready(s_compute0_local_data_boot_rom_req.b_ready),
    .s_compute0_local_data_boot_rom_arid(s_compute0_local_data_boot_rom_req.ar.id),
    .s_compute0_local_data_boot_rom_araddr(s_compute0_local_data_boot_rom_req.ar.addr),
    .s_compute0_local_data_boot_rom_arlen(s_compute0_local_data_boot_rom_req.ar.len),
    .s_compute0_local_data_boot_rom_arsize(s_compute0_local_data_boot_rom_req.ar.size),
    .s_compute0_local_data_boot_rom_arburst(s_compute0_local_data_boot_rom_req.ar.burst),
    .s_compute0_local_data_boot_rom_arlock(s_compute0_local_data_boot_rom_req.ar.lock),
    .s_compute0_local_data_boot_rom_arcache(s_compute0_local_data_boot_rom_req.ar.cache),
    .s_compute0_local_data_boot_rom_arprot(s_compute0_local_data_boot_rom_req.ar.prot),
    .s_compute0_local_data_boot_rom_arqos(s_compute0_local_data_boot_rom_req.ar.qos),
    .s_compute0_local_data_boot_rom_arregion(s_compute0_local_data_boot_rom_req.ar.region),
    .s_compute0_local_data_boot_rom_arvalid(s_compute0_local_data_boot_rom_req.ar_valid),
    .s_compute0_local_data_boot_rom_arready(s_compute0_local_data_boot_rom_rsp.ar_ready),
    .s_compute0_local_data_boot_rom_rid(s_compute0_local_data_boot_rom_rsp.r.id),
    .s_compute0_local_data_boot_rom_rdata(s_compute0_local_data_boot_rom_rsp.r.data),
    .s_compute0_local_data_boot_rom_rresp(s_compute0_local_data_boot_rom_rsp.r.resp),
    .s_compute0_local_data_boot_rom_rlast(s_compute0_local_data_boot_rom_rsp.r.last),
    .s_compute0_local_data_boot_rom_rvalid(s_compute0_local_data_boot_rom_rsp.r_valid),
    .s_compute0_local_data_boot_rom_rready(s_compute0_local_data_boot_rom_req.r_ready),
    .s_compute0_local_data_sram_awid(s_compute0_local_data_sram_req.aw.id),
    .s_compute0_local_data_sram_awaddr(s_compute0_local_data_sram_req.aw.addr),
    .s_compute0_local_data_sram_awlen(s_compute0_local_data_sram_req.aw.len),
    .s_compute0_local_data_sram_awsize(s_compute0_local_data_sram_req.aw.size),
    .s_compute0_local_data_sram_awburst(s_compute0_local_data_sram_req.aw.burst),
    .s_compute0_local_data_sram_awlock(s_compute0_local_data_sram_req.aw.lock),
    .s_compute0_local_data_sram_awcache(s_compute0_local_data_sram_req.aw.cache),
    .s_compute0_local_data_sram_awprot(s_compute0_local_data_sram_req.aw.prot),
    .s_compute0_local_data_sram_awqos(s_compute0_local_data_sram_req.aw.qos),
    .s_compute0_local_data_sram_awregion(s_compute0_local_data_sram_req.aw.region),
    .s_compute0_local_data_sram_awvalid(s_compute0_local_data_sram_req.aw_valid),
    .s_compute0_local_data_sram_awready(s_compute0_local_data_sram_rsp.aw_ready),
    .s_compute0_local_data_sram_wdata(s_compute0_local_data_sram_req.w.data),
    .s_compute0_local_data_sram_wstrb(s_compute0_local_data_sram_req.w.strb),
    .s_compute0_local_data_sram_wlast(s_compute0_local_data_sram_req.w.last),
    .s_compute0_local_data_sram_wvalid(s_compute0_local_data_sram_req.w_valid),
    .s_compute0_local_data_sram_wready(s_compute0_local_data_sram_rsp.w_ready),
    .s_compute0_local_data_sram_bid(s_compute0_local_data_sram_rsp.b.id),
    .s_compute0_local_data_sram_bresp(s_compute0_local_data_sram_rsp.b.resp),
    .s_compute0_local_data_sram_bvalid(s_compute0_local_data_sram_rsp.b_valid),
    .s_compute0_local_data_sram_bready(s_compute0_local_data_sram_req.b_ready),
    .s_compute0_local_data_sram_arid(s_compute0_local_data_sram_req.ar.id),
    .s_compute0_local_data_sram_araddr(s_compute0_local_data_sram_req.ar.addr),
    .s_compute0_local_data_sram_arlen(s_compute0_local_data_sram_req.ar.len),
    .s_compute0_local_data_sram_arsize(s_compute0_local_data_sram_req.ar.size),
    .s_compute0_local_data_sram_arburst(s_compute0_local_data_sram_req.ar.burst),
    .s_compute0_local_data_sram_arlock(s_compute0_local_data_sram_req.ar.lock),
    .s_compute0_local_data_sram_arcache(s_compute0_local_data_sram_req.ar.cache),
    .s_compute0_local_data_sram_arprot(s_compute0_local_data_sram_req.ar.prot),
    .s_compute0_local_data_sram_arqos(s_compute0_local_data_sram_req.ar.qos),
    .s_compute0_local_data_sram_arregion(s_compute0_local_data_sram_req.ar.region),
    .s_compute0_local_data_sram_arvalid(s_compute0_local_data_sram_req.ar_valid),
    .s_compute0_local_data_sram_arready(s_compute0_local_data_sram_rsp.ar_ready),
    .s_compute0_local_data_sram_rid(s_compute0_local_data_sram_rsp.r.id),
    .s_compute0_local_data_sram_rdata(s_compute0_local_data_sram_rsp.r.data),
    .s_compute0_local_data_sram_rresp(s_compute0_local_data_sram_rsp.r.resp),
    .s_compute0_local_data_sram_rlast(s_compute0_local_data_sram_rsp.r.last),
    .s_compute0_local_data_sram_rvalid(s_compute0_local_data_sram_rsp.r_valid),
    .s_compute0_local_data_sram_rready(s_compute0_local_data_sram_req.r_ready),
    .s_compute1_local_config_dma_regs_awid(s_compute1_local_config_dma_regs_req.aw.id),
    .s_compute1_local_config_dma_regs_awaddr(s_compute1_local_config_dma_regs_req.aw.addr),
    .s_compute1_local_config_dma_regs_awlen(s_compute1_local_config_dma_regs_req.aw.len),
    .s_compute1_local_config_dma_regs_awsize(s_compute1_local_config_dma_regs_req.aw.size),
    .s_compute1_local_config_dma_regs_awburst(s_compute1_local_config_dma_regs_req.aw.burst),
    .s_compute1_local_config_dma_regs_awlock(s_compute1_local_config_dma_regs_req.aw.lock),
    .s_compute1_local_config_dma_regs_awcache(s_compute1_local_config_dma_regs_req.aw.cache),
    .s_compute1_local_config_dma_regs_awprot(s_compute1_local_config_dma_regs_req.aw.prot),
    .s_compute1_local_config_dma_regs_awqos(s_compute1_local_config_dma_regs_req.aw.qos),
    .s_compute1_local_config_dma_regs_awregion(s_compute1_local_config_dma_regs_req.aw.region),
    .s_compute1_local_config_dma_regs_awvalid(s_compute1_local_config_dma_regs_req.aw_valid),
    .s_compute1_local_config_dma_regs_awready(s_compute1_local_config_dma_regs_rsp.aw_ready),
    .s_compute1_local_config_dma_regs_wdata(s_compute1_local_config_dma_regs_req.w.data),
    .s_compute1_local_config_dma_regs_wstrb(s_compute1_local_config_dma_regs_req.w.strb),
    .s_compute1_local_config_dma_regs_wlast(s_compute1_local_config_dma_regs_req.w.last),
    .s_compute1_local_config_dma_regs_wvalid(s_compute1_local_config_dma_regs_req.w_valid),
    .s_compute1_local_config_dma_regs_wready(s_compute1_local_config_dma_regs_rsp.w_ready),
    .s_compute1_local_config_dma_regs_bid(s_compute1_local_config_dma_regs_rsp.b.id),
    .s_compute1_local_config_dma_regs_bresp(s_compute1_local_config_dma_regs_rsp.b.resp),
    .s_compute1_local_config_dma_regs_bvalid(s_compute1_local_config_dma_regs_rsp.b_valid),
    .s_compute1_local_config_dma_regs_bready(s_compute1_local_config_dma_regs_req.b_ready),
    .s_compute1_local_config_dma_regs_arid(s_compute1_local_config_dma_regs_req.ar.id),
    .s_compute1_local_config_dma_regs_araddr(s_compute1_local_config_dma_regs_req.ar.addr),
    .s_compute1_local_config_dma_regs_arlen(s_compute1_local_config_dma_regs_req.ar.len),
    .s_compute1_local_config_dma_regs_arsize(s_compute1_local_config_dma_regs_req.ar.size),
    .s_compute1_local_config_dma_regs_arburst(s_compute1_local_config_dma_regs_req.ar.burst),
    .s_compute1_local_config_dma_regs_arlock(s_compute1_local_config_dma_regs_req.ar.lock),
    .s_compute1_local_config_dma_regs_arcache(s_compute1_local_config_dma_regs_req.ar.cache),
    .s_compute1_local_config_dma_regs_arprot(s_compute1_local_config_dma_regs_req.ar.prot),
    .s_compute1_local_config_dma_regs_arqos(s_compute1_local_config_dma_regs_req.ar.qos),
    .s_compute1_local_config_dma_regs_arregion(s_compute1_local_config_dma_regs_req.ar.region),
    .s_compute1_local_config_dma_regs_arvalid(s_compute1_local_config_dma_regs_req.ar_valid),
    .s_compute1_local_config_dma_regs_arready(s_compute1_local_config_dma_regs_rsp.ar_ready),
    .s_compute1_local_config_dma_regs_rid(s_compute1_local_config_dma_regs_rsp.r.id),
    .s_compute1_local_config_dma_regs_rdata(s_compute1_local_config_dma_regs_rsp.r.data),
    .s_compute1_local_config_dma_regs_rresp(s_compute1_local_config_dma_regs_rsp.r.resp),
    .s_compute1_local_config_dma_regs_rlast(s_compute1_local_config_dma_regs_rsp.r.last),
    .s_compute1_local_config_dma_regs_rvalid(s_compute1_local_config_dma_regs_rsp.r_valid),
    .s_compute1_local_config_dma_regs_rready(s_compute1_local_config_dma_regs_req.r_ready),
    .s_compute1_local_data_sram_awid(s_compute1_local_data_sram_req.aw.id),
    .s_compute1_local_data_sram_awaddr(s_compute1_local_data_sram_req.aw.addr),
    .s_compute1_local_data_sram_awlen(s_compute1_local_data_sram_req.aw.len),
    .s_compute1_local_data_sram_awsize(s_compute1_local_data_sram_req.aw.size),
    .s_compute1_local_data_sram_awburst(s_compute1_local_data_sram_req.aw.burst),
    .s_compute1_local_data_sram_awlock(s_compute1_local_data_sram_req.aw.lock),
    .s_compute1_local_data_sram_awcache(s_compute1_local_data_sram_req.aw.cache),
    .s_compute1_local_data_sram_awprot(s_compute1_local_data_sram_req.aw.prot),
    .s_compute1_local_data_sram_awqos(s_compute1_local_data_sram_req.aw.qos),
    .s_compute1_local_data_sram_awregion(s_compute1_local_data_sram_req.aw.region),
    .s_compute1_local_data_sram_awvalid(s_compute1_local_data_sram_req.aw_valid),
    .s_compute1_local_data_sram_awready(s_compute1_local_data_sram_rsp.aw_ready),
    .s_compute1_local_data_sram_wdata(s_compute1_local_data_sram_req.w.data),
    .s_compute1_local_data_sram_wstrb(s_compute1_local_data_sram_req.w.strb),
    .s_compute1_local_data_sram_wlast(s_compute1_local_data_sram_req.w.last),
    .s_compute1_local_data_sram_wvalid(s_compute1_local_data_sram_req.w_valid),
    .s_compute1_local_data_sram_wready(s_compute1_local_data_sram_rsp.w_ready),
    .s_compute1_local_data_sram_bid(s_compute1_local_data_sram_rsp.b.id),
    .s_compute1_local_data_sram_bresp(s_compute1_local_data_sram_rsp.b.resp),
    .s_compute1_local_data_sram_bvalid(s_compute1_local_data_sram_rsp.b_valid),
    .s_compute1_local_data_sram_bready(s_compute1_local_data_sram_req.b_ready),
    .s_compute1_local_data_sram_arid(s_compute1_local_data_sram_req.ar.id),
    .s_compute1_local_data_sram_araddr(s_compute1_local_data_sram_req.ar.addr),
    .s_compute1_local_data_sram_arlen(s_compute1_local_data_sram_req.ar.len),
    .s_compute1_local_data_sram_arsize(s_compute1_local_data_sram_req.ar.size),
    .s_compute1_local_data_sram_arburst(s_compute1_local_data_sram_req.ar.burst),
    .s_compute1_local_data_sram_arlock(s_compute1_local_data_sram_req.ar.lock),
    .s_compute1_local_data_sram_arcache(s_compute1_local_data_sram_req.ar.cache),
    .s_compute1_local_data_sram_arprot(s_compute1_local_data_sram_req.ar.prot),
    .s_compute1_local_data_sram_arqos(s_compute1_local_data_sram_req.ar.qos),
    .s_compute1_local_data_sram_arregion(s_compute1_local_data_sram_req.ar.region),
    .s_compute1_local_data_sram_arvalid(s_compute1_local_data_sram_req.ar_valid),
    .s_compute1_local_data_sram_arready(s_compute1_local_data_sram_rsp.ar_ready),
    .s_compute1_local_data_sram_rid(s_compute1_local_data_sram_rsp.r.id),
    .s_compute1_local_data_sram_rdata(s_compute1_local_data_sram_rsp.r.data),
    .s_compute1_local_data_sram_rresp(s_compute1_local_data_sram_rsp.r.resp),
    .s_compute1_local_data_sram_rlast(s_compute1_local_data_sram_rsp.r.last),
    .s_compute1_local_data_sram_rvalid(s_compute1_local_data_sram_rsp.r_valid),
    .s_compute1_local_data_sram_rready(s_compute1_local_data_sram_req.r_ready),
    .s_ethernet0_local_config_controller_regs_awid(s_ethernet0_local_config_controller_regs_req.aw.id),
    .s_ethernet0_local_config_controller_regs_awaddr(s_ethernet0_local_config_controller_regs_req.aw.addr),
    .s_ethernet0_local_config_controller_regs_awlen(s_ethernet0_local_config_controller_regs_req.aw.len),
    .s_ethernet0_local_config_controller_regs_awsize(s_ethernet0_local_config_controller_regs_req.aw.size),
    .s_ethernet0_local_config_controller_regs_awburst(s_ethernet0_local_config_controller_regs_req.aw.burst),
    .s_ethernet0_local_config_controller_regs_awlock(s_ethernet0_local_config_controller_regs_req.aw.lock),
    .s_ethernet0_local_config_controller_regs_awcache(s_ethernet0_local_config_controller_regs_req.aw.cache),
    .s_ethernet0_local_config_controller_regs_awprot(s_ethernet0_local_config_controller_regs_req.aw.prot),
    .s_ethernet0_local_config_controller_regs_awqos(s_ethernet0_local_config_controller_regs_req.aw.qos),
    .s_ethernet0_local_config_controller_regs_awregion(s_ethernet0_local_config_controller_regs_req.aw.region),
    .s_ethernet0_local_config_controller_regs_awvalid(s_ethernet0_local_config_controller_regs_req.aw_valid),
    .s_ethernet0_local_config_controller_regs_awready(s_ethernet0_local_config_controller_regs_rsp.aw_ready),
    .s_ethernet0_local_config_controller_regs_wdata(s_ethernet0_local_config_controller_regs_req.w.data),
    .s_ethernet0_local_config_controller_regs_wstrb(s_ethernet0_local_config_controller_regs_req.w.strb),
    .s_ethernet0_local_config_controller_regs_wlast(s_ethernet0_local_config_controller_regs_req.w.last),
    .s_ethernet0_local_config_controller_regs_wvalid(s_ethernet0_local_config_controller_regs_req.w_valid),
    .s_ethernet0_local_config_controller_regs_wready(s_ethernet0_local_config_controller_regs_rsp.w_ready),
    .s_ethernet0_local_config_controller_regs_bid(s_ethernet0_local_config_controller_regs_rsp.b.id),
    .s_ethernet0_local_config_controller_regs_bresp(s_ethernet0_local_config_controller_regs_rsp.b.resp),
    .s_ethernet0_local_config_controller_regs_bvalid(s_ethernet0_local_config_controller_regs_rsp.b_valid),
    .s_ethernet0_local_config_controller_regs_bready(s_ethernet0_local_config_controller_regs_req.b_ready),
    .s_ethernet0_local_config_controller_regs_arid(s_ethernet0_local_config_controller_regs_req.ar.id),
    .s_ethernet0_local_config_controller_regs_araddr(s_ethernet0_local_config_controller_regs_req.ar.addr),
    .s_ethernet0_local_config_controller_regs_arlen(s_ethernet0_local_config_controller_regs_req.ar.len),
    .s_ethernet0_local_config_controller_regs_arsize(s_ethernet0_local_config_controller_regs_req.ar.size),
    .s_ethernet0_local_config_controller_regs_arburst(s_ethernet0_local_config_controller_regs_req.ar.burst),
    .s_ethernet0_local_config_controller_regs_arlock(s_ethernet0_local_config_controller_regs_req.ar.lock),
    .s_ethernet0_local_config_controller_regs_arcache(s_ethernet0_local_config_controller_regs_req.ar.cache),
    .s_ethernet0_local_config_controller_regs_arprot(s_ethernet0_local_config_controller_regs_req.ar.prot),
    .s_ethernet0_local_config_controller_regs_arqos(s_ethernet0_local_config_controller_regs_req.ar.qos),
    .s_ethernet0_local_config_controller_regs_arregion(s_ethernet0_local_config_controller_regs_req.ar.region),
    .s_ethernet0_local_config_controller_regs_arvalid(s_ethernet0_local_config_controller_regs_req.ar_valid),
    .s_ethernet0_local_config_controller_regs_arready(s_ethernet0_local_config_controller_regs_rsp.ar_ready),
    .s_ethernet0_local_config_controller_regs_rid(s_ethernet0_local_config_controller_regs_rsp.r.id),
    .s_ethernet0_local_config_controller_regs_rdata(s_ethernet0_local_config_controller_regs_rsp.r.data),
    .s_ethernet0_local_config_controller_regs_rresp(s_ethernet0_local_config_controller_regs_rsp.r.resp),
    .s_ethernet0_local_config_controller_regs_rlast(s_ethernet0_local_config_controller_regs_rsp.r.last),
    .s_ethernet0_local_config_controller_regs_rvalid(s_ethernet0_local_config_controller_regs_rsp.r_valid),
    .s_ethernet0_local_config_controller_regs_rready(s_ethernet0_local_config_controller_regs_req.r_ready),
    .s_ethernet0_local_data_sram_awid(s_ethernet0_local_data_sram_req.aw.id),
    .s_ethernet0_local_data_sram_awaddr(s_ethernet0_local_data_sram_req.aw.addr),
    .s_ethernet0_local_data_sram_awlen(s_ethernet0_local_data_sram_req.aw.len),
    .s_ethernet0_local_data_sram_awsize(s_ethernet0_local_data_sram_req.aw.size),
    .s_ethernet0_local_data_sram_awburst(s_ethernet0_local_data_sram_req.aw.burst),
    .s_ethernet0_local_data_sram_awlock(s_ethernet0_local_data_sram_req.aw.lock),
    .s_ethernet0_local_data_sram_awcache(s_ethernet0_local_data_sram_req.aw.cache),
    .s_ethernet0_local_data_sram_awprot(s_ethernet0_local_data_sram_req.aw.prot),
    .s_ethernet0_local_data_sram_awqos(s_ethernet0_local_data_sram_req.aw.qos),
    .s_ethernet0_local_data_sram_awregion(s_ethernet0_local_data_sram_req.aw.region),
    .s_ethernet0_local_data_sram_awvalid(s_ethernet0_local_data_sram_req.aw_valid),
    .s_ethernet0_local_data_sram_awready(s_ethernet0_local_data_sram_rsp.aw_ready),
    .s_ethernet0_local_data_sram_wdata(s_ethernet0_local_data_sram_req.w.data),
    .s_ethernet0_local_data_sram_wstrb(s_ethernet0_local_data_sram_req.w.strb),
    .s_ethernet0_local_data_sram_wlast(s_ethernet0_local_data_sram_req.w.last),
    .s_ethernet0_local_data_sram_wvalid(s_ethernet0_local_data_sram_req.w_valid),
    .s_ethernet0_local_data_sram_wready(s_ethernet0_local_data_sram_rsp.w_ready),
    .s_ethernet0_local_data_sram_bid(s_ethernet0_local_data_sram_rsp.b.id),
    .s_ethernet0_local_data_sram_bresp(s_ethernet0_local_data_sram_rsp.b.resp),
    .s_ethernet0_local_data_sram_bvalid(s_ethernet0_local_data_sram_rsp.b_valid),
    .s_ethernet0_local_data_sram_bready(s_ethernet0_local_data_sram_req.b_ready),
    .s_ethernet0_local_data_sram_arid(s_ethernet0_local_data_sram_req.ar.id),
    .s_ethernet0_local_data_sram_araddr(s_ethernet0_local_data_sram_req.ar.addr),
    .s_ethernet0_local_data_sram_arlen(s_ethernet0_local_data_sram_req.ar.len),
    .s_ethernet0_local_data_sram_arsize(s_ethernet0_local_data_sram_req.ar.size),
    .s_ethernet0_local_data_sram_arburst(s_ethernet0_local_data_sram_req.ar.burst),
    .s_ethernet0_local_data_sram_arlock(s_ethernet0_local_data_sram_req.ar.lock),
    .s_ethernet0_local_data_sram_arcache(s_ethernet0_local_data_sram_req.ar.cache),
    .s_ethernet0_local_data_sram_arprot(s_ethernet0_local_data_sram_req.ar.prot),
    .s_ethernet0_local_data_sram_arqos(s_ethernet0_local_data_sram_req.ar.qos),
    .s_ethernet0_local_data_sram_arregion(s_ethernet0_local_data_sram_req.ar.region),
    .s_ethernet0_local_data_sram_arvalid(s_ethernet0_local_data_sram_req.ar_valid),
    .s_ethernet0_local_data_sram_arready(s_ethernet0_local_data_sram_rsp.ar_ready),
    .s_ethernet0_local_data_sram_rid(s_ethernet0_local_data_sram_rsp.r.id),
    .s_ethernet0_local_data_sram_rdata(s_ethernet0_local_data_sram_rsp.r.data),
    .s_ethernet0_local_data_sram_rresp(s_ethernet0_local_data_sram_rsp.r.resp),
    .s_ethernet0_local_data_sram_rlast(s_ethernet0_local_data_sram_rsp.r.last),
    .s_ethernet0_local_data_sram_rvalid(s_ethernet0_local_data_sram_rsp.r_valid),
    .s_ethernet0_local_data_sram_rready(s_ethernet0_local_data_sram_req.r_ready),
    .s_memory0_local_config_controller_regs_awid(s_memory0_local_config_controller_regs_req.aw.id),
    .s_memory0_local_config_controller_regs_awaddr(s_memory0_local_config_controller_regs_req.aw.addr),
    .s_memory0_local_config_controller_regs_awlen(s_memory0_local_config_controller_regs_req.aw.len),
    .s_memory0_local_config_controller_regs_awsize(s_memory0_local_config_controller_regs_req.aw.size),
    .s_memory0_local_config_controller_regs_awburst(s_memory0_local_config_controller_regs_req.aw.burst),
    .s_memory0_local_config_controller_regs_awlock(s_memory0_local_config_controller_regs_req.aw.lock),
    .s_memory0_local_config_controller_regs_awcache(s_memory0_local_config_controller_regs_req.aw.cache),
    .s_memory0_local_config_controller_regs_awprot(s_memory0_local_config_controller_regs_req.aw.prot),
    .s_memory0_local_config_controller_regs_awqos(s_memory0_local_config_controller_regs_req.aw.qos),
    .s_memory0_local_config_controller_regs_awregion(s_memory0_local_config_controller_regs_req.aw.region),
    .s_memory0_local_config_controller_regs_awvalid(s_memory0_local_config_controller_regs_req.aw_valid),
    .s_memory0_local_config_controller_regs_awready(s_memory0_local_config_controller_regs_rsp.aw_ready),
    .s_memory0_local_config_controller_regs_wdata(s_memory0_local_config_controller_regs_req.w.data),
    .s_memory0_local_config_controller_regs_wstrb(s_memory0_local_config_controller_regs_req.w.strb),
    .s_memory0_local_config_controller_regs_wlast(s_memory0_local_config_controller_regs_req.w.last),
    .s_memory0_local_config_controller_regs_wvalid(s_memory0_local_config_controller_regs_req.w_valid),
    .s_memory0_local_config_controller_regs_wready(s_memory0_local_config_controller_regs_rsp.w_ready),
    .s_memory0_local_config_controller_regs_bid(s_memory0_local_config_controller_regs_rsp.b.id),
    .s_memory0_local_config_controller_regs_bresp(s_memory0_local_config_controller_regs_rsp.b.resp),
    .s_memory0_local_config_controller_regs_bvalid(s_memory0_local_config_controller_regs_rsp.b_valid),
    .s_memory0_local_config_controller_regs_bready(s_memory0_local_config_controller_regs_req.b_ready),
    .s_memory0_local_config_controller_regs_arid(s_memory0_local_config_controller_regs_req.ar.id),
    .s_memory0_local_config_controller_regs_araddr(s_memory0_local_config_controller_regs_req.ar.addr),
    .s_memory0_local_config_controller_regs_arlen(s_memory0_local_config_controller_regs_req.ar.len),
    .s_memory0_local_config_controller_regs_arsize(s_memory0_local_config_controller_regs_req.ar.size),
    .s_memory0_local_config_controller_regs_arburst(s_memory0_local_config_controller_regs_req.ar.burst),
    .s_memory0_local_config_controller_regs_arlock(s_memory0_local_config_controller_regs_req.ar.lock),
    .s_memory0_local_config_controller_regs_arcache(s_memory0_local_config_controller_regs_req.ar.cache),
    .s_memory0_local_config_controller_regs_arprot(s_memory0_local_config_controller_regs_req.ar.prot),
    .s_memory0_local_config_controller_regs_arqos(s_memory0_local_config_controller_regs_req.ar.qos),
    .s_memory0_local_config_controller_regs_arregion(s_memory0_local_config_controller_regs_req.ar.region),
    .s_memory0_local_config_controller_regs_arvalid(s_memory0_local_config_controller_regs_req.ar_valid),
    .s_memory0_local_config_controller_regs_arready(s_memory0_local_config_controller_regs_rsp.ar_ready),
    .s_memory0_local_config_controller_regs_rid(s_memory0_local_config_controller_regs_rsp.r.id),
    .s_memory0_local_config_controller_regs_rdata(s_memory0_local_config_controller_regs_rsp.r.data),
    .s_memory0_local_config_controller_regs_rresp(s_memory0_local_config_controller_regs_rsp.r.resp),
    .s_memory0_local_config_controller_regs_rlast(s_memory0_local_config_controller_regs_rsp.r.last),
    .s_memory0_local_config_controller_regs_rvalid(s_memory0_local_config_controller_regs_rsp.r_valid),
    .s_memory0_local_config_controller_regs_rready(s_memory0_local_config_controller_regs_req.r_ready),
    .s_memory0_local_data_target_crossbar_awid(s_memory0_local_data_target_crossbar_req.aw.id),
    .s_memory0_local_data_target_crossbar_awaddr(s_memory0_local_data_target_crossbar_req.aw.addr),
    .s_memory0_local_data_target_crossbar_awlen(s_memory0_local_data_target_crossbar_req.aw.len),
    .s_memory0_local_data_target_crossbar_awsize(s_memory0_local_data_target_crossbar_req.aw.size),
    .s_memory0_local_data_target_crossbar_awburst(s_memory0_local_data_target_crossbar_req.aw.burst),
    .s_memory0_local_data_target_crossbar_awlock(s_memory0_local_data_target_crossbar_req.aw.lock),
    .s_memory0_local_data_target_crossbar_awcache(s_memory0_local_data_target_crossbar_req.aw.cache),
    .s_memory0_local_data_target_crossbar_awprot(s_memory0_local_data_target_crossbar_req.aw.prot),
    .s_memory0_local_data_target_crossbar_awqos(s_memory0_local_data_target_crossbar_req.aw.qos),
    .s_memory0_local_data_target_crossbar_awregion(s_memory0_local_data_target_crossbar_req.aw.region),
    .s_memory0_local_data_target_crossbar_awvalid(s_memory0_local_data_target_crossbar_req.aw_valid),
    .s_memory0_local_data_target_crossbar_awready(s_memory0_local_data_target_crossbar_rsp.aw_ready),
    .s_memory0_local_data_target_crossbar_wdata(s_memory0_local_data_target_crossbar_req.w.data),
    .s_memory0_local_data_target_crossbar_wstrb(s_memory0_local_data_target_crossbar_req.w.strb),
    .s_memory0_local_data_target_crossbar_wlast(s_memory0_local_data_target_crossbar_req.w.last),
    .s_memory0_local_data_target_crossbar_wvalid(s_memory0_local_data_target_crossbar_req.w_valid),
    .s_memory0_local_data_target_crossbar_wready(s_memory0_local_data_target_crossbar_rsp.w_ready),
    .s_memory0_local_data_target_crossbar_bid(s_memory0_local_data_target_crossbar_rsp.b.id),
    .s_memory0_local_data_target_crossbar_bresp(s_memory0_local_data_target_crossbar_rsp.b.resp),
    .s_memory0_local_data_target_crossbar_bvalid(s_memory0_local_data_target_crossbar_rsp.b_valid),
    .s_memory0_local_data_target_crossbar_bready(s_memory0_local_data_target_crossbar_req.b_ready),
    .s_memory0_local_data_target_crossbar_arid(s_memory0_local_data_target_crossbar_req.ar.id),
    .s_memory0_local_data_target_crossbar_araddr(s_memory0_local_data_target_crossbar_req.ar.addr),
    .s_memory0_local_data_target_crossbar_arlen(s_memory0_local_data_target_crossbar_req.ar.len),
    .s_memory0_local_data_target_crossbar_arsize(s_memory0_local_data_target_crossbar_req.ar.size),
    .s_memory0_local_data_target_crossbar_arburst(s_memory0_local_data_target_crossbar_req.ar.burst),
    .s_memory0_local_data_target_crossbar_arlock(s_memory0_local_data_target_crossbar_req.ar.lock),
    .s_memory0_local_data_target_crossbar_arcache(s_memory0_local_data_target_crossbar_req.ar.cache),
    .s_memory0_local_data_target_crossbar_arprot(s_memory0_local_data_target_crossbar_req.ar.prot),
    .s_memory0_local_data_target_crossbar_arqos(s_memory0_local_data_target_crossbar_req.ar.qos),
    .s_memory0_local_data_target_crossbar_arregion(s_memory0_local_data_target_crossbar_req.ar.region),
    .s_memory0_local_data_target_crossbar_arvalid(s_memory0_local_data_target_crossbar_req.ar_valid),
    .s_memory0_local_data_target_crossbar_arready(s_memory0_local_data_target_crossbar_rsp.ar_ready),
    .s_memory0_local_data_target_crossbar_rid(s_memory0_local_data_target_crossbar_rsp.r.id),
    .s_memory0_local_data_target_crossbar_rdata(s_memory0_local_data_target_crossbar_rsp.r.data),
    .s_memory0_local_data_target_crossbar_rresp(s_memory0_local_data_target_crossbar_rsp.r.resp),
    .s_memory0_local_data_target_crossbar_rlast(s_memory0_local_data_target_crossbar_rsp.r.last),
    .s_memory0_local_data_target_crossbar_rvalid(s_memory0_local_data_target_crossbar_rsp.r_valid),
    .s_memory0_local_data_target_crossbar_rready(s_memory0_local_data_target_crossbar_req.r_ready),
    .s_pcie0_local_config_controller_regs_awid(s_pcie0_local_config_controller_regs_req.aw.id),
    .s_pcie0_local_config_controller_regs_awaddr(s_pcie0_local_config_controller_regs_req.aw.addr),
    .s_pcie0_local_config_controller_regs_awlen(s_pcie0_local_config_controller_regs_req.aw.len),
    .s_pcie0_local_config_controller_regs_awsize(s_pcie0_local_config_controller_regs_req.aw.size),
    .s_pcie0_local_config_controller_regs_awburst(s_pcie0_local_config_controller_regs_req.aw.burst),
    .s_pcie0_local_config_controller_regs_awlock(s_pcie0_local_config_controller_regs_req.aw.lock),
    .s_pcie0_local_config_controller_regs_awcache(s_pcie0_local_config_controller_regs_req.aw.cache),
    .s_pcie0_local_config_controller_regs_awprot(s_pcie0_local_config_controller_regs_req.aw.prot),
    .s_pcie0_local_config_controller_regs_awqos(s_pcie0_local_config_controller_regs_req.aw.qos),
    .s_pcie0_local_config_controller_regs_awregion(s_pcie0_local_config_controller_regs_req.aw.region),
    .s_pcie0_local_config_controller_regs_awvalid(s_pcie0_local_config_controller_regs_req.aw_valid),
    .s_pcie0_local_config_controller_regs_awready(s_pcie0_local_config_controller_regs_rsp.aw_ready),
    .s_pcie0_local_config_controller_regs_wdata(s_pcie0_local_config_controller_regs_req.w.data),
    .s_pcie0_local_config_controller_regs_wstrb(s_pcie0_local_config_controller_regs_req.w.strb),
    .s_pcie0_local_config_controller_regs_wlast(s_pcie0_local_config_controller_regs_req.w.last),
    .s_pcie0_local_config_controller_regs_wvalid(s_pcie0_local_config_controller_regs_req.w_valid),
    .s_pcie0_local_config_controller_regs_wready(s_pcie0_local_config_controller_regs_rsp.w_ready),
    .s_pcie0_local_config_controller_regs_bid(s_pcie0_local_config_controller_regs_rsp.b.id),
    .s_pcie0_local_config_controller_regs_bresp(s_pcie0_local_config_controller_regs_rsp.b.resp),
    .s_pcie0_local_config_controller_regs_bvalid(s_pcie0_local_config_controller_regs_rsp.b_valid),
    .s_pcie0_local_config_controller_regs_bready(s_pcie0_local_config_controller_regs_req.b_ready),
    .s_pcie0_local_config_controller_regs_arid(s_pcie0_local_config_controller_regs_req.ar.id),
    .s_pcie0_local_config_controller_regs_araddr(s_pcie0_local_config_controller_regs_req.ar.addr),
    .s_pcie0_local_config_controller_regs_arlen(s_pcie0_local_config_controller_regs_req.ar.len),
    .s_pcie0_local_config_controller_regs_arsize(s_pcie0_local_config_controller_regs_req.ar.size),
    .s_pcie0_local_config_controller_regs_arburst(s_pcie0_local_config_controller_regs_req.ar.burst),
    .s_pcie0_local_config_controller_regs_arlock(s_pcie0_local_config_controller_regs_req.ar.lock),
    .s_pcie0_local_config_controller_regs_arcache(s_pcie0_local_config_controller_regs_req.ar.cache),
    .s_pcie0_local_config_controller_regs_arprot(s_pcie0_local_config_controller_regs_req.ar.prot),
    .s_pcie0_local_config_controller_regs_arqos(s_pcie0_local_config_controller_regs_req.ar.qos),
    .s_pcie0_local_config_controller_regs_arregion(s_pcie0_local_config_controller_regs_req.ar.region),
    .s_pcie0_local_config_controller_regs_arvalid(s_pcie0_local_config_controller_regs_req.ar_valid),
    .s_pcie0_local_config_controller_regs_arready(s_pcie0_local_config_controller_regs_rsp.ar_ready),
    .s_pcie0_local_config_controller_regs_rid(s_pcie0_local_config_controller_regs_rsp.r.id),
    .s_pcie0_local_config_controller_regs_rdata(s_pcie0_local_config_controller_regs_rsp.r.data),
    .s_pcie0_local_config_controller_regs_rresp(s_pcie0_local_config_controller_regs_rsp.r.resp),
    .s_pcie0_local_config_controller_regs_rlast(s_pcie0_local_config_controller_regs_rsp.r.last),
    .s_pcie0_local_config_controller_regs_rvalid(s_pcie0_local_config_controller_regs_rsp.r_valid),
    .s_pcie0_local_config_controller_regs_rready(s_pcie0_local_config_controller_regs_req.r_ready),
    .s_pcie0_local_data_sram_awid(s_pcie0_local_data_sram_req.aw.id),
    .s_pcie0_local_data_sram_awaddr(s_pcie0_local_data_sram_req.aw.addr),
    .s_pcie0_local_data_sram_awlen(s_pcie0_local_data_sram_req.aw.len),
    .s_pcie0_local_data_sram_awsize(s_pcie0_local_data_sram_req.aw.size),
    .s_pcie0_local_data_sram_awburst(s_pcie0_local_data_sram_req.aw.burst),
    .s_pcie0_local_data_sram_awlock(s_pcie0_local_data_sram_req.aw.lock),
    .s_pcie0_local_data_sram_awcache(s_pcie0_local_data_sram_req.aw.cache),
    .s_pcie0_local_data_sram_awprot(s_pcie0_local_data_sram_req.aw.prot),
    .s_pcie0_local_data_sram_awqos(s_pcie0_local_data_sram_req.aw.qos),
    .s_pcie0_local_data_sram_awregion(s_pcie0_local_data_sram_req.aw.region),
    .s_pcie0_local_data_sram_awvalid(s_pcie0_local_data_sram_req.aw_valid),
    .s_pcie0_local_data_sram_awready(s_pcie0_local_data_sram_rsp.aw_ready),
    .s_pcie0_local_data_sram_wdata(s_pcie0_local_data_sram_req.w.data),
    .s_pcie0_local_data_sram_wstrb(s_pcie0_local_data_sram_req.w.strb),
    .s_pcie0_local_data_sram_wlast(s_pcie0_local_data_sram_req.w.last),
    .s_pcie0_local_data_sram_wvalid(s_pcie0_local_data_sram_req.w_valid),
    .s_pcie0_local_data_sram_wready(s_pcie0_local_data_sram_rsp.w_ready),
    .s_pcie0_local_data_sram_bid(s_pcie0_local_data_sram_rsp.b.id),
    .s_pcie0_local_data_sram_bresp(s_pcie0_local_data_sram_rsp.b.resp),
    .s_pcie0_local_data_sram_bvalid(s_pcie0_local_data_sram_rsp.b_valid),
    .s_pcie0_local_data_sram_bready(s_pcie0_local_data_sram_req.b_ready),
    .s_pcie0_local_data_sram_arid(s_pcie0_local_data_sram_req.ar.id),
    .s_pcie0_local_data_sram_araddr(s_pcie0_local_data_sram_req.ar.addr),
    .s_pcie0_local_data_sram_arlen(s_pcie0_local_data_sram_req.ar.len),
    .s_pcie0_local_data_sram_arsize(s_pcie0_local_data_sram_req.ar.size),
    .s_pcie0_local_data_sram_arburst(s_pcie0_local_data_sram_req.ar.burst),
    .s_pcie0_local_data_sram_arlock(s_pcie0_local_data_sram_req.ar.lock),
    .s_pcie0_local_data_sram_arcache(s_pcie0_local_data_sram_req.ar.cache),
    .s_pcie0_local_data_sram_arprot(s_pcie0_local_data_sram_req.ar.prot),
    .s_pcie0_local_data_sram_arqos(s_pcie0_local_data_sram_req.ar.qos),
    .s_pcie0_local_data_sram_arregion(s_pcie0_local_data_sram_req.ar.region),
    .s_pcie0_local_data_sram_arvalid(s_pcie0_local_data_sram_req.ar_valid),
    .s_pcie0_local_data_sram_arready(s_pcie0_local_data_sram_rsp.ar_ready),
    .s_pcie0_local_data_sram_rid(s_pcie0_local_data_sram_rsp.r.id),
    .s_pcie0_local_data_sram_rdata(s_pcie0_local_data_sram_rsp.r.data),
    .s_pcie0_local_data_sram_rresp(s_pcie0_local_data_sram_rsp.r.resp),
    .s_pcie0_local_data_sram_rlast(s_pcie0_local_data_sram_rsp.r.last),
    .s_pcie0_local_data_sram_rvalid(s_pcie0_local_data_sram_rsp.r_valid),
    .s_pcie0_local_data_sram_rready(s_pcie0_local_data_sram_req.r_ready)
  );
  initial if (DmaTestMode && (!DmaEnable || !ProbeEnable))
    $fatal(1, "DMA CPU0 AXI BFM mode requires active DMA and probe");
  logic [7:0][7:0] reset_regs;
  logic [1:0] cpu_reset_n;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t cfgprobe_req;
  assign cfgprobe_req.aw.id = cfgprobe_awid;
  assign cfgprobe_req.aw.addr = cfgprobe_awaddr;
  assign cfgprobe_req.aw.len = cfgprobe_awlen;
  assign cfgprobe_req.aw.size = cfgprobe_awsize;
  assign cfgprobe_req.aw.burst = cfgprobe_awburst;
  assign cfgprobe_req.aw.lock = cfgprobe_awlock;
  assign cfgprobe_req.aw.cache = cfgprobe_awcache;
  assign cfgprobe_req.aw.prot = cfgprobe_awprot;
  assign cfgprobe_req.aw.qos = cfgprobe_awqos;
  assign cfgprobe_req.aw.region = cfgprobe_awregion;
  assign cfgprobe_req.aw_valid = cfgprobe_awvalid;
  assign cfgprobe_awready = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.aw_ready : '0;
  assign cfgprobe_req.w.data = cfgprobe_wdata;
  assign cfgprobe_req.w.strb = cfgprobe_wstrb;
  assign cfgprobe_req.w.last = cfgprobe_wlast;
  assign cfgprobe_req.w_valid = cfgprobe_wvalid;
  assign cfgprobe_wready = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.w_ready : '0;
  assign cfgprobe_bid = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.b.id : '0;
  assign cfgprobe_bresp = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.b.resp : '0;
  assign cfgprobe_bvalid = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.b_valid : '0;
  assign cfgprobe_req.b_ready = cfgprobe_bready;
  assign cfgprobe_req.ar.id = cfgprobe_arid;
  assign cfgprobe_req.ar.addr = cfgprobe_araddr;
  assign cfgprobe_req.ar.len = cfgprobe_arlen;
  assign cfgprobe_req.ar.size = cfgprobe_arsize;
  assign cfgprobe_req.ar.burst = cfgprobe_arburst;
  assign cfgprobe_req.ar.lock = cfgprobe_arlock;
  assign cfgprobe_req.ar.cache = cfgprobe_arcache;
  assign cfgprobe_req.ar.prot = cfgprobe_arprot;
  assign cfgprobe_req.ar.qos = cfgprobe_arqos;
  assign cfgprobe_req.ar.region = cfgprobe_arregion;
  assign cfgprobe_req.ar_valid = cfgprobe_arvalid;
  assign cfgprobe_arready = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.ar_ready : '0;
  assign cfgprobe_rid = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.r.id : '0;
  assign cfgprobe_rdata = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.r.data : '0;
  assign cfgprobe_rresp = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.r.resp : '0;
  assign cfgprobe_rlast = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.r.last : '0;
  assign cfgprobe_rvalid = ddr_init_mode_i ? m_compute0_local_config_cpu_rsp.r_valid : '0;
  assign cfgprobe_req.r_ready = cfgprobe_rready;
  assign cfgprobe_req.aw.atop = '0;
  assign cfgprobe_req.aw.user = '0;
  assign cfgprobe_req.w.user = '0;
  assign cfgprobe_req.ar.user = '0;
  lite_req_t cpu_0_req;
  lite_resp_t cpu_0_rsp;
  assign cpu_reset_n[0] = (rst_ni && !ddr_init_mode_i) && !DmaTestMode;
  assign released_o[0] = cpu_reset_n[0];
  logic cpu_0_trap;
  picorv32_cpu_adapter u_cpu_compute0 (
    .clk(clk_i),
    .rst(!cpu_reset_n[0]),
    .trap(cpu_0_trap),
    .awvalid(cpu_0_req.aw_valid),
    .awready(cpu_0_rsp.aw_ready),
    .awaddr(cpu_0_req.aw.addr),
    .awprot(cpu_0_req.aw.prot),
    .wvalid(cpu_0_req.w_valid),
    .wready(cpu_0_rsp.w_ready),
    .wdata(cpu_0_req.w.data),
    .wstrb(cpu_0_req.w.strb),
    .bvalid(cpu_0_rsp.b_valid),
    .bready(cpu_0_req.b_ready),
    .arvalid(cpu_0_req.ar_valid),
    .arready(cpu_0_rsp.ar_ready),
    .araddr(cpu_0_req.ar.addr),
    .arprot(cpu_0_req.ar.prot),
    .rvalid(cpu_0_rsp.r_valid),
    .rready(cpu_0_req.r_ready),
    .rdata(cpu_0_rsp.r.data)
  );
  always @(posedge clk_i) if (cpu_reset_n[0] && cpu_0_trap) $fatal(1, "CPU0 trap");
  assign fetch_valid_o[0] = cpu_0_req.ar_valid && cpu_0_rsp.ar_ready && cpu_0_req.ar.prot[2];
  assign fetch_addr_o[0*32 +: 32] = cpu_0_req.ar.addr;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t probe_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t cpu_data_0_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t cpu_data_0_rsp;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t cpu_config_0_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_rsp_t cpu_config_0_rsp;
  assign m_compute0_local_data_cpu_req = DmaTestMode ? probe_req : cpu_data_0_req;
  assign cpu_data_0_rsp = DmaTestMode ? '0 : m_compute0_local_data_cpu_rsp;
  assign m_compute0_local_config_cpu_req = DmaTestMode ? cfgprobe_req : ddr_init_mode_i ? cfgprobe_req : cpu_config_0_req;
  assign cpu_config_0_rsp = DmaTestMode || ddr_init_mode_i ? '0 : m_compute0_local_config_cpu_rsp;
  cpu_noc_adapter #(
    .data_req_t(floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t),
    .data_rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t),
    .cfg_req_t(floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t),
    .cfg_rsp_t(floo_xezim_compute0_local_config_noc_pkg::axi_in_rsp_t),
    .ConfigBase(32'h40000000),
    .ConfigEnd(32'h40060000)
  ) u_edge_compute0 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .cpu_req_i(cpu_0_req),
    .cpu_rsp_o(cpu_0_rsp),
    .data_req_o(cpu_data_0_req),
    .data_rsp_i(cpu_data_0_rsp),
    .cfg_req_o(cpu_config_0_req),
    .cfg_rsp_i(cpu_config_0_rsp)
  );
  always @(posedge clk_i) if (cpu_reset_n[0] && ((cpu_0_rsp.r_valid && cpu_0_req.r_ready && cpu_0_rsp.r.resp != 0) || (cpu_0_rsp.b_valid && cpu_0_req.b_ready && cpu_0_rsp.b.resp != 0))) $fatal(1, "CPU bus error compute0");
  logic [63:0] dma_0_apb_addr, dma_0_apb_data;
  logic dma_0_apb_write, dma_0_apb_select, dma_0_apb_enable;
  logic dma_0_apb_ready, dma_0_apb_error;
  logic [63:0] dma_0_apb_rdata;
  assign probe_req.aw.id = probe_awid;
  assign probe_req.aw.addr = probe_awaddr;
  assign probe_req.aw.len = probe_awlen;
  assign probe_req.aw.size = probe_awsize;
  assign probe_req.aw.burst = probe_awburst;
  assign probe_req.aw.lock = probe_awlock;
  assign probe_req.aw.cache = probe_awcache;
  assign probe_req.aw.prot = probe_awprot;
  assign probe_req.aw.qos = probe_awqos;
  assign probe_req.aw.region = probe_awregion;
  assign probe_req.aw_valid = probe_awvalid;
  assign probe_awready = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.aw_ready : '0;
  assign probe_req.w.data = probe_wdata;
  assign probe_req.w.strb = probe_wstrb;
  assign probe_req.w.last = probe_wlast;
  assign probe_req.w_valid = probe_wvalid;
  assign probe_wready = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.w_ready : '0;
  assign probe_bid = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.b.id : '0;
  assign probe_bresp = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.b.resp : '0;
  assign probe_bvalid = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.b_valid : '0;
  assign probe_req.b_ready = probe_bready;
  assign probe_req.ar.id = probe_arid;
  assign probe_req.ar.addr = probe_araddr;
  assign probe_req.ar.len = probe_arlen;
  assign probe_req.ar.size = probe_arsize;
  assign probe_req.ar.burst = probe_arburst;
  assign probe_req.ar.lock = probe_arlock;
  assign probe_req.ar.cache = probe_arcache;
  assign probe_req.ar.prot = probe_arprot;
  assign probe_req.ar.qos = probe_arqos;
  assign probe_req.ar.region = probe_arregion;
  assign probe_req.ar_valid = probe_arvalid;
  assign probe_arready = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.ar_ready : '0;
  assign probe_rid = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.r.id : '0;
  assign probe_rdata = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.r.data : '0;
  assign probe_rresp = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.r.resp : '0;
  assign probe_rlast = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.r.last : '0;
  assign probe_rvalid = ddr_negative_mode_i ? m_compute0_local_data_dma_rsp.r_valid : '0;
  assign probe_req.r_ready = probe_rready;
  assign probe_req.aw.atop = '0;
  assign probe_req.aw.user = '0;
  assign probe_req.w.user = '0;
  assign probe_req.ar.user = '0;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t dma_0_hw_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t dma_0_hw_rsp;
  assign m_compute0_local_data_dma_req = ddr_negative_mode_i ? probe_req : dma_0_hw_req;
  assign dma_0_hw_rsp = ddr_negative_mode_i ? '0 : m_compute0_local_data_dma_rsp;
  always @(posedge clk_i) if (ddr_negative_mode_i && (dma_0_hw_req.aw_valid || dma_0_hw_req.w_valid || dma_0_hw_req.ar_valid)) $fatal(1, "DDR probe takeover during active iDMA request");
  if (DmaEnable) begin: gen_dma_compute0
  soc_idma_engine #(
    .NumAxInFlight(2),
    .BufferDepth(3),
    .DescriptorPrefetch(0)
  ) u_dma_compute0 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .apb_addr_i(dma_0_apb_addr),
    .apb_data_i(dma_0_apb_data),
    .apb_write_i(dma_0_apb_write),
    .apb_select_i(dma_0_apb_select),
    .apb_enable_i(dma_0_apb_enable),
    .apb_ready_o(dma_0_apb_ready),
    .apb_rdata_o(dma_0_apb_rdata),
    .apb_error_o(dma_0_apb_error),
    .irq_o(dma_irq_o[0]),
    .dma_awid(dma_0_hw_req.aw.id),
    .dma_awaddr(dma_0_hw_req.aw.addr),
    .dma_awlen(dma_0_hw_req.aw.len),
    .dma_awsize(dma_0_hw_req.aw.size),
    .dma_awburst(dma_0_hw_req.aw.burst),
    .dma_awlock(dma_0_hw_req.aw.lock),
    .dma_awcache(dma_0_hw_req.aw.cache),
    .dma_awprot(dma_0_hw_req.aw.prot),
    .dma_awqos(dma_0_hw_req.aw.qos),
    .dma_awregion(dma_0_hw_req.aw.region),
    .dma_awvalid(dma_0_hw_req.aw_valid),
    .dma_awready(dma_0_hw_rsp.aw_ready),
    .dma_wdata(dma_0_hw_req.w.data),
    .dma_wstrb(dma_0_hw_req.w.strb),
    .dma_wlast(dma_0_hw_req.w.last),
    .dma_wvalid(dma_0_hw_req.w_valid),
    .dma_wready(dma_0_hw_rsp.w_ready),
    .dma_bid(dma_0_hw_rsp.b.id),
    .dma_bresp(dma_0_hw_rsp.b.resp),
    .dma_bvalid(dma_0_hw_rsp.b_valid),
    .dma_bready(dma_0_hw_req.b_ready),
    .dma_arid(dma_0_hw_req.ar.id),
    .dma_araddr(dma_0_hw_req.ar.addr),
    .dma_arlen(dma_0_hw_req.ar.len),
    .dma_arsize(dma_0_hw_req.ar.size),
    .dma_arburst(dma_0_hw_req.ar.burst),
    .dma_arlock(dma_0_hw_req.ar.lock),
    .dma_arcache(dma_0_hw_req.ar.cache),
    .dma_arprot(dma_0_hw_req.ar.prot),
    .dma_arqos(dma_0_hw_req.ar.qos),
    .dma_arregion(dma_0_hw_req.ar.region),
    .dma_arvalid(dma_0_hw_req.ar_valid),
    .dma_arready(dma_0_hw_rsp.ar_ready),
    .dma_rid(dma_0_hw_rsp.r.id),
    .dma_rdata(dma_0_hw_rsp.r.data),
    .dma_rresp(dma_0_hw_rsp.r.resp),
    .dma_rlast(dma_0_hw_rsp.r.last),
    .dma_rvalid(dma_0_hw_rsp.r_valid),
    .dma_rready(dma_0_hw_req.r_ready)
  );
    assign dma_0_hw_req.aw.atop = '0;
    assign dma_0_hw_req.aw.user = '0;
    assign dma_0_hw_req.w.user = '0;
    assign dma_0_hw_req.ar.user = '0;
  end else begin: gen_dma_disabled_compute0
    assign dma_0_hw_req = '0;
    assign dma_irq_o[0] = 1'b0;
  end
  lite_req_t cpu_1_req;
  lite_resp_t cpu_1_rsp;
  assign cpu_reset_n[1] = (rst_ni && reset_regs[0][0] && !hold_mask_i[1] && !ddr_init_mode_i) && !DmaTestMode;
  assign released_o[1] = cpu_reset_n[1];
  logic [31:0] c1_ia, c1_da, c1_wd, c1_ir, c1_dr;
  logic [3:0] c1_sel;
  logic c1_ic, c1_dc, c1_we, c1_iack, c1_dack;
  lite_req_t [1:0] c1_req;
  lite_resp_t [1:0] c1_rsp;
  serv_cpu_adapter #(
    .RESET_PC(32'h11000000)
  ) u_cpu_compute1 (
    .clk(clk_i),
    .rst(!cpu_reset_n[1]),
    .ibus_addr(c1_ia),
    .ibus_cyc(c1_ic),
    .ibus_rdata(c1_ir),
    .ibus_ack(c1_iack),
    .dbus_addr(c1_da),
    .dbus_data(c1_wd),
    .dbus_select(c1_sel),
    .dbus_write(c1_we),
    .dbus_cyc(c1_dc),
    .dbus_rdata(c1_dr),
    .dbus_ack(c1_dack)
  );
  serv_axi_lite_adapter u_wb_compute1_0 (
    .clk_i(clk_i),
    .rst_ni(cpu_reset_n[1]),
    .cyc_i(c1_ic),
    .we_i(1'b0),
    .addr_i(c1_ia),
    .wdata_i(32'b0),
    .strb_i(4'hf),
    .ack_o(c1_iack),
    .rdata_o(c1_ir),
    .req_o(c1_req[0]),
    .rsp_i(c1_rsp[0])
  );
  serv_axi_lite_adapter u_wb_compute1_1 (
    .clk_i(clk_i),
    .rst_ni(cpu_reset_n[1]),
    .cyc_i(c1_dc),
    .we_i(c1_we),
    .addr_i(c1_da),
    .wdata_i(c1_wd),
    .strb_i(c1_sel),
    .ack_o(c1_dack),
    .rdata_o(c1_dr),
    .req_o(c1_req[1]),
    .rsp_i(c1_rsp[1])
  );
  axi_lite_mux #(
    .aw_chan_t(lite_aw_chan_t),
    .w_chan_t(lite_w_chan_t),
    .b_chan_t(lite_b_chan_t),
    .ar_chan_t(lite_ar_chan_t),
    .r_chan_t(lite_r_chan_t),
    .axi_req_t(lite_req_t),
    .axi_resp_t(lite_resp_t),
    .NoSlvPorts(2),
    .MaxTrans(1)
  ) u_id_mux_compute1 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .slv_reqs_i(c1_req),
    .slv_resps_o(c1_rsp),
    .mst_req_o(cpu_1_req),
    .mst_resp_i(cpu_1_rsp)
  );
  assign fetch_valid_o[1] = c1_ic && c1_iack;
  assign fetch_addr_o[1*32 +: 32] = c1_ia;
  cpu_noc_adapter #(
    .data_req_t(floo_xezim_compute1_local_data_noc_pkg::axi_in_req_t),
    .data_rsp_t(floo_xezim_compute1_local_data_noc_pkg::axi_in_rsp_t),
    .cfg_req_t(floo_xezim_compute1_local_config_noc_pkg::axi_in_req_t),
    .cfg_rsp_t(floo_xezim_compute1_local_config_noc_pkg::axi_in_rsp_t),
    .ConfigBase(32'h40000000),
    .ConfigEnd(32'h40060000)
  ) u_edge_compute1 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .cpu_req_i(cpu_1_req),
    .cpu_rsp_o(cpu_1_rsp),
    .data_req_o(m_compute1_local_data_cpu_req),
    .data_rsp_i(m_compute1_local_data_cpu_rsp),
    .cfg_req_o(m_compute1_local_config_cpu_req),
    .cfg_rsp_i(m_compute1_local_config_cpu_rsp)
  );
  always @(posedge clk_i) if (cpu_reset_n[1] && ((cpu_1_rsp.r_valid && cpu_1_req.r_ready && cpu_1_rsp.r.resp != 0) || (cpu_1_rsp.b_valid && cpu_1_req.b_ready && cpu_1_rsp.b.resp != 0))) $fatal(1, "CPU bus error compute1");
  logic [63:0] dma_1_apb_addr, dma_1_apb_data;
  logic dma_1_apb_write, dma_1_apb_select, dma_1_apb_enable;
  logic dma_1_apb_ready, dma_1_apb_error;
  logic [63:0] dma_1_apb_rdata;
  if (DmaEnable) begin: gen_dma_compute1
  soc_idma_engine #(
    .NumAxInFlight(2),
    .BufferDepth(3),
    .DescriptorPrefetch(0)
  ) u_dma_compute1 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .apb_addr_i(dma_1_apb_addr),
    .apb_data_i(dma_1_apb_data),
    .apb_write_i(dma_1_apb_write),
    .apb_select_i(dma_1_apb_select),
    .apb_enable_i(dma_1_apb_enable),
    .apb_ready_o(dma_1_apb_ready),
    .apb_rdata_o(dma_1_apb_rdata),
    .apb_error_o(dma_1_apb_error),
    .irq_o(dma_irq_o[1]),
    .dma_awid(m_compute1_local_data_dma_req.aw.id),
    .dma_awaddr(m_compute1_local_data_dma_req.aw.addr),
    .dma_awlen(m_compute1_local_data_dma_req.aw.len),
    .dma_awsize(m_compute1_local_data_dma_req.aw.size),
    .dma_awburst(m_compute1_local_data_dma_req.aw.burst),
    .dma_awlock(m_compute1_local_data_dma_req.aw.lock),
    .dma_awcache(m_compute1_local_data_dma_req.aw.cache),
    .dma_awprot(m_compute1_local_data_dma_req.aw.prot),
    .dma_awqos(m_compute1_local_data_dma_req.aw.qos),
    .dma_awregion(m_compute1_local_data_dma_req.aw.region),
    .dma_awvalid(m_compute1_local_data_dma_req.aw_valid),
    .dma_awready(m_compute1_local_data_dma_rsp.aw_ready),
    .dma_wdata(m_compute1_local_data_dma_req.w.data),
    .dma_wstrb(m_compute1_local_data_dma_req.w.strb),
    .dma_wlast(m_compute1_local_data_dma_req.w.last),
    .dma_wvalid(m_compute1_local_data_dma_req.w_valid),
    .dma_wready(m_compute1_local_data_dma_rsp.w_ready),
    .dma_bid(m_compute1_local_data_dma_rsp.b.id),
    .dma_bresp(m_compute1_local_data_dma_rsp.b.resp),
    .dma_bvalid(m_compute1_local_data_dma_rsp.b_valid),
    .dma_bready(m_compute1_local_data_dma_req.b_ready),
    .dma_arid(m_compute1_local_data_dma_req.ar.id),
    .dma_araddr(m_compute1_local_data_dma_req.ar.addr),
    .dma_arlen(m_compute1_local_data_dma_req.ar.len),
    .dma_arsize(m_compute1_local_data_dma_req.ar.size),
    .dma_arburst(m_compute1_local_data_dma_req.ar.burst),
    .dma_arlock(m_compute1_local_data_dma_req.ar.lock),
    .dma_arcache(m_compute1_local_data_dma_req.ar.cache),
    .dma_arprot(m_compute1_local_data_dma_req.ar.prot),
    .dma_arqos(m_compute1_local_data_dma_req.ar.qos),
    .dma_arregion(m_compute1_local_data_dma_req.ar.region),
    .dma_arvalid(m_compute1_local_data_dma_req.ar_valid),
    .dma_arready(m_compute1_local_data_dma_rsp.ar_ready),
    .dma_rid(m_compute1_local_data_dma_rsp.r.id),
    .dma_rdata(m_compute1_local_data_dma_rsp.r.data),
    .dma_rresp(m_compute1_local_data_dma_rsp.r.resp),
    .dma_rlast(m_compute1_local_data_dma_rsp.r.last),
    .dma_rvalid(m_compute1_local_data_dma_rsp.r_valid),
    .dma_rready(m_compute1_local_data_dma_req.r_ready)
  );
    assign m_compute1_local_data_dma_req.aw.atop = '0;
    assign m_compute1_local_data_dma_req.aw.user = '0;
    assign m_compute1_local_data_dma_req.w.user = '0;
    assign m_compute1_local_data_dma_req.ar.user = '0;
  end else begin: gen_dma_disabled_compute1
    assign m_compute1_local_data_dma_req = '0;
    assign dma_irq_o[1] = 1'b0;
  end
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
  assign pcie_req.aw.id = m_axi_awid;
  assign pcie_req.aw.addr = m_axi_awaddr;
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
  assign pcie_req.ar.addr = m_axi_araddr;
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
  assign pcie_req.aw_valid = m_axi_awvalid;
  assign pcie_req.w_valid = m_axi_wvalid;
  assign pcie_req.ar_valid = m_axi_arvalid;
  assign pcie_req.b_ready = m_axi_bready;
  assign pcie_req.r_ready = m_axi_rready;
  assign m_axi_awready = pcie_rsp.aw_ready;
  assign m_axi_wready = pcie_rsp.w_ready;
  assign m_axi_arready = pcie_rsp.ar_ready;
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
    .clk(clk_i),
    .rst(~rst_ni),
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

  assign m_pcie0_local_data_host_req = pcie_req;
  assign pcie_rsp = m_pcie0_local_data_host_rsp;

  logic pcie_sram_valid, pcie_sram_write;
  logic [63:0] pcie_sram_addr, pcie_sram_data;
  logic [7:0] pcie_sram_strb;
  logic ethq_cfg_valid, ethq_cfg_write, ethq_cfg_ready, ethq_cfg_error;
  logic [7:0] ethq_cfg_addr;
  logic [31:0] ethq_cfg_wdata, ethq_cfg_rdata;
  logic [3:0] ethq_cfg_wstrb;
  ethernet0_axi_mvp #(
    .RX_RING_BASE(64'h0000000013001000),
    .RX_RING_BYTES(64'h200),
    .TX_RING_BASE(64'h0000000013001400),
    .TX_RING_BYTES(64'h200),
    .RX_CQ_BASE(64'h0000000013001200),
    .TX_CQ_BASE(64'h0000000013001600),
    .CQ_WINDOW_BYTES(64'h200),
    .BUFFER_BASE(64'h0000000013002000),
    .BUFFER_BYTES(64'h2000),
    .ALT_BUFFER_BASE(64'h0000000140000000),
    .ALT_BUFFER_BYTES(64'h10000)
  ) u_ethernet_mvp (
    .logic_clk(clk_i),
    .logic_rst(~rst_ni),
    .gmii_rx_clk(gmii_rx_clk),
    .gmii_rx_rst(gmii_rx_rst),
    .gmii_tx_clk(gmii_tx_clk),
    .gmii_tx_rst(gmii_tx_rst),
    .gmii_rxd(gmii_rxd),
    .gmii_rx_dv(gmii_rx_dv),
    .gmii_rx_er(gmii_rx_er),
    .gmii_txd(gmii_txd),
    .gmii_tx_en(gmii_tx_en),
    .gmii_tx_er(gmii_tx_er),
    .irq_o(eth_irq_o),
    .frame_drop_o(eth_drop_o),
    .rx_error_bad_fcs_o(eth_bad_fcs_o),
    .tx_failed_o(eth_tx_failed_o),
    .cfg_valid(ethq_cfg_valid),
    .cfg_write(ethq_cfg_write),
    .cfg_addr(ethq_cfg_addr),
    .cfg_wdata(ethq_cfg_wdata),
    .cfg_wstrb(ethq_cfg_wstrb),
    .cfg_ready(ethq_cfg_ready),
    .cfg_rdata(ethq_cfg_rdata),
    .cfg_error(ethq_cfg_error),
    .axi_awid(m_ethernet0_local_data_packet_dma_req.aw.id),
    .axi_awaddr(m_ethernet0_local_data_packet_dma_req.aw.addr),
    .axi_awlen(m_ethernet0_local_data_packet_dma_req.aw.len),
    .axi_awsize(m_ethernet0_local_data_packet_dma_req.aw.size),
    .axi_awburst(m_ethernet0_local_data_packet_dma_req.aw.burst),
    .axi_awlock(m_ethernet0_local_data_packet_dma_req.aw.lock),
    .axi_awcache(m_ethernet0_local_data_packet_dma_req.aw.cache),
    .axi_awprot(m_ethernet0_local_data_packet_dma_req.aw.prot),
    .axi_awvalid(m_ethernet0_local_data_packet_dma_req.aw_valid),
    .axi_awready(m_ethernet0_local_data_packet_dma_rsp.aw_ready),
    .axi_wdata(m_ethernet0_local_data_packet_dma_req.w.data),
    .axi_wstrb(m_ethernet0_local_data_packet_dma_req.w.strb),
    .axi_wlast(m_ethernet0_local_data_packet_dma_req.w.last),
    .axi_wvalid(m_ethernet0_local_data_packet_dma_req.w_valid),
    .axi_wready(m_ethernet0_local_data_packet_dma_rsp.w_ready),
    .axi_bid(m_ethernet0_local_data_packet_dma_rsp.b.id),
    .axi_bresp(m_ethernet0_local_data_packet_dma_rsp.b.resp),
    .axi_bvalid(m_ethernet0_local_data_packet_dma_rsp.b_valid),
    .axi_bready(m_ethernet0_local_data_packet_dma_req.b_ready),
    .axi_arid(m_ethernet0_local_data_packet_dma_req.ar.id),
    .axi_araddr(m_ethernet0_local_data_packet_dma_req.ar.addr),
    .axi_arlen(m_ethernet0_local_data_packet_dma_req.ar.len),
    .axi_arsize(m_ethernet0_local_data_packet_dma_req.ar.size),
    .axi_arburst(m_ethernet0_local_data_packet_dma_req.ar.burst),
    .axi_arlock(m_ethernet0_local_data_packet_dma_req.ar.lock),
    .axi_arcache(m_ethernet0_local_data_packet_dma_req.ar.cache),
    .axi_arprot(m_ethernet0_local_data_packet_dma_req.ar.prot),
    .axi_arvalid(m_ethernet0_local_data_packet_dma_req.ar_valid),
    .axi_arready(m_ethernet0_local_data_packet_dma_rsp.ar_ready),
    .axi_rid(m_ethernet0_local_data_packet_dma_rsp.r.id),
    .axi_rdata(m_ethernet0_local_data_packet_dma_rsp.r.data),
    .axi_rresp(m_ethernet0_local_data_packet_dma_rsp.r.resp),
    .axi_rlast(m_ethernet0_local_data_packet_dma_rsp.r.last),
    .axi_rvalid(m_ethernet0_local_data_packet_dma_rsp.r_valid),
    .axi_rready(m_ethernet0_local_data_packet_dma_req.r_ready)
  );
  assign m_ethernet0_local_data_packet_dma_req.aw.qos = '0;
  assign m_ethernet0_local_data_packet_dma_req.aw.region = '0;
  assign m_ethernet0_local_data_packet_dma_req.aw.user = '0;
  assign m_ethernet0_local_data_packet_dma_req.ar.qos = '0;
  assign m_ethernet0_local_data_packet_dma_req.ar.region = '0;
  assign m_ethernet0_local_data_packet_dma_req.ar.user = '0;
  assign m_ethernet0_local_data_packet_dma_req.aw.atop = '0;
  assign m_ethernet0_local_data_packet_dma_req.w.user = '0;
  assign m_pcie0_local_config_management_req = '0;
  assign m_ethernet0_local_config_management_req = '0;
  logic ddr_init_done, ddr_init_error;
  if (DmaEnable) begin: gen_dma_csr_compute0
  soc_dma_regs #(
    .axi_req_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t),
    .axi_rsp_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t),
    .lite_req_t(lite_req_t),
    .lite_rsp_t(lite_resp_t),
    .AxiIdWidth(1)
  ) u_dma_csr_compute0 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .cfg_req_i(s_compute0_local_config_dma_regs_req),
    .cfg_rsp_o(s_compute0_local_config_dma_regs_rsp),
    .apb_addr_o(dma_0_apb_addr),
    .apb_data_o(dma_0_apb_data),
    .apb_write_o(dma_0_apb_write),
    .apb_select_o(dma_0_apb_select),
    .apb_enable_o(dma_0_apb_enable),
    .apb_ready_i(dma_0_apb_ready),
    .apb_error_i(dma_0_apb_error),
    .irq_raw_i(dma_irq_o[0]),
    .irq_pending_o(dma_irq_pending_o[0])
  );
  end else begin: gen_dma_csr_disabled_compute0
  axi_err_slv #(
    .AxiIdWidth(1),
    .axi_req_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t),
    .axi_resp_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t),
    .ATOPs(0)
  ) u_unused_s_compute0_local_config_dma_regs (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .slv_req_i(s_compute0_local_config_dma_regs_req),
    .slv_resp_o(s_compute0_local_config_dma_regs_rsp)
  );
    assign dma_irq_pending_o[0] = 1'b0;
  end
  lite_req_t reset_req;
  lite_resp_t reset_rsp;
  axi_to_axi_lite #(
    .AxiAddrWidth(32),
    .AxiDataWidth(32),
    .AxiIdWidth(1),
    .AxiUserWidth(1),
    .AxiMaxWriteTxns(2),
    .AxiMaxReadTxns(2),
    .full_req_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t),
    .full_resp_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t),
    .lite_req_t(lite_req_t),
    .lite_resp_t(lite_resp_t)
  ) u_reset_convert (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .slv_req_i(s_compute0_local_config_reset_ctrl_req),
    .slv_resp_o(s_compute0_local_config_reset_ctrl_rsp),
    .mst_req_o(reset_req),
    .mst_resp_i(reset_rsp)
  );
  axi_lite_regs #(
    .RegNumBytes(8),
    .AxiAddrWidth(32),
    .AxiDataWidth(32),
    .req_lite_t(lite_req_t),
    .resp_lite_t(lite_resp_t)
  ) u_reset_regs (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .axi_req_i(reset_req),
    .axi_resp_o(reset_rsp),
    .reg_d_i('0),
    .reg_load_i('0),
    .reg_q_o(reset_regs),
    .wr_active_o(),
    .rd_active_o()
  );
  logic boot_flash_valid, boot_flash_write;
  logic [63:0] boot_flash_addr, boot_flash_data;
  logic [7:0] boot_flash_strb;
  axi_sram_target #(
    .req_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(5),
    .Base(64'h0000000020000000),
    .Bytes(65536),
    .ReadOnly(1),
    .InitFile("gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/rtl/flash.hex")
  ) u_s_compute0_local_data_boot_flash (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(s_compute0_local_data_boot_flash_req),
    .rsp_o(s_compute0_local_data_boot_flash_rsp),
    .mon_valid_o(boot_flash_valid),
    .mon_write_o(boot_flash_write),
    .mon_addr_o(boot_flash_addr),
    .mon_data_o(boot_flash_data),
    .mon_strb_o(boot_flash_strb)
  );
  logic boot_rom_valid, boot_rom_write;
  logic [63:0] boot_rom_addr, boot_rom_data;
  logic [7:0] boot_rom_strb;
  axi_sram_target #(
    .req_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(5),
    .Base(64'h0000000000000000),
    .Bytes(4096),
    .ReadOnly(1),
    .InitFile("gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/rtl/bootrom.hex")
  ) u_s_compute0_local_data_boot_rom (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(s_compute0_local_data_boot_rom_req),
    .rsp_o(s_compute0_local_data_boot_rom_rsp),
    .mon_valid_o(boot_rom_valid),
    .mon_write_o(boot_rom_write),
    .mon_addr_o(boot_rom_addr),
    .mon_data_o(boot_rom_data),
    .mon_strb_o(boot_rom_strb)
  );
  axi_sram_target #(
    .req_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(5),
    .Base(64'h0000000010000000),
    .Bytes(16384),
    .ReadOnly(0),
    .InitFile("")
  ) u_s_compute0_local_data_sram (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(s_compute0_local_data_sram_req),
    .rsp_o(s_compute0_local_data_sram_rsp),
    .mon_valid_o(sram_valid_o[0*1 +: 1]),
    .mon_write_o(sram_write_o[0*1 +: 1]),
    .mon_addr_o(sram_addr_o[0*64 +: 64]),
    .mon_data_o(sram_data_o[0*64 +: 64]),
    .mon_strb_o(sram_strb_o[0*8 +: 8])
  );
  if (DmaEnable) begin: gen_dma_csr_compute1
  soc_dma_regs #(
    .axi_req_t(floo_xezim_compute1_local_config_noc_pkg::axi_out_req_t),
    .axi_rsp_t(floo_xezim_compute1_local_config_noc_pkg::axi_out_rsp_t),
    .lite_req_t(lite_req_t),
    .lite_rsp_t(lite_resp_t),
    .AxiIdWidth(1)
  ) u_dma_csr_compute1 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .cfg_req_i(s_compute1_local_config_dma_regs_req),
    .cfg_rsp_o(s_compute1_local_config_dma_regs_rsp),
    .apb_addr_o(dma_1_apb_addr),
    .apb_data_o(dma_1_apb_data),
    .apb_write_o(dma_1_apb_write),
    .apb_select_o(dma_1_apb_select),
    .apb_enable_o(dma_1_apb_enable),
    .apb_ready_i(dma_1_apb_ready),
    .apb_error_i(dma_1_apb_error),
    .irq_raw_i(dma_irq_o[1]),
    .irq_pending_o(dma_irq_pending_o[1])
  );
  end else begin: gen_dma_csr_disabled_compute1
  axi_err_slv #(
    .AxiIdWidth(1),
    .axi_req_t(floo_xezim_compute1_local_config_noc_pkg::axi_out_req_t),
    .axi_resp_t(floo_xezim_compute1_local_config_noc_pkg::axi_out_rsp_t),
    .ATOPs(0)
  ) u_unused_s_compute1_local_config_dma_regs (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .slv_req_i(s_compute1_local_config_dma_regs_req),
    .slv_resp_o(s_compute1_local_config_dma_regs_rsp)
  );
    assign dma_irq_pending_o[1] = 1'b0;
  end
  axi_sram_target #(
    .req_t(floo_xezim_compute1_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_compute1_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(5),
    .Base(64'h0000000011000000),
    .Bytes(16384),
    .ReadOnly(0),
    .InitFile("")
  ) u_s_compute1_local_data_sram (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(s_compute1_local_data_sram_req),
    .rsp_o(s_compute1_local_data_sram_rsp),
    .mon_valid_o(sram_valid_o[1*1 +: 1]),
    .mon_write_o(sram_write_o[1*1 +: 1]),
    .mon_addr_o(sram_addr_o[1*64 +: 64]),
    .mon_data_o(sram_data_o[1*64 +: 64]),
    .mon_strb_o(sram_strb_o[1*8 +: 8])
  );
  ethernet_queue_axi_regs #(
    .axi_req_t(floo_xezim_ethernet0_local_config_noc_pkg::axi_out_req_t),
    .axi_rsp_t(floo_xezim_ethernet0_local_config_noc_pkg::axi_out_rsp_t),
    .lite_req_t(lite_req_t),
    .lite_rsp_t(lite_resp_t),
    .AxiIdWidth(1),
    .CsrBase(32'h40050000)
  ) u_ethernet_queue_regs (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .cfg_req_i(s_ethernet0_local_config_controller_regs_req),
    .cfg_rsp_o(s_ethernet0_local_config_controller_regs_rsp),
    .queue_valid_o(ethq_cfg_valid),
    .queue_write_o(ethq_cfg_write),
    .queue_addr_o(ethq_cfg_addr),
    .queue_wdata_o(ethq_cfg_wdata),
    .queue_wstrb_o(ethq_cfg_wstrb),
    .queue_ready_i(ethq_cfg_ready),
    .queue_rdata_i(ethq_cfg_rdata),
    .queue_error_i(ethq_cfg_error)
  );
  axi_sram_target #(
    .req_t(floo_xezim_ethernet0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_ethernet0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(5),
    .Base(64'h0000000013000000),
    .Bytes(16384),
    .ReadOnly(0),
    .InitFile("")
  ) u_s_ethernet0_local_data_sram (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(s_ethernet0_local_data_sram_req),
    .rsp_o(s_ethernet0_local_data_sram_rsp),
    .mon_valid_o(),
    .mon_write_o(),
    .mon_addr_o(),
    .mon_data_o(),
    .mon_strb_o()
  );
  floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t memory_0_req;
  floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t memory_0_rsp;
  axi_sram_target #(
    .req_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(4),
    .Base(64'h0000000100000000),
    .Bytes(65536)
  ) u_memory_model_0 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(memory_0_req),
    .rsp_o(memory_0_rsp),
    .mon_valid_o(),
    .mon_write_o(),
    .mon_addr_o(),
    .mon_data_o(),
    .mon_strb_o()
  );
  assign memory_0_req.aw.atop = '0;
  floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t memory_1_req;
  floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t memory_1_rsp;
  ddr_litedram_fullchip_target #(
    .data_req_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t),
    .data_rsp_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t),
    .cfg_req_t(floo_xezim_memory0_local_config_noc_pkg::axi_out_req_t),
    .cfg_rsp_t(floo_xezim_memory0_local_config_noc_pkg::axi_out_rsp_t),
    .WB_BASE(32'h00000000),
    .WB_ADR_BITS(30)
  ) u_ddr_real (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .data_req_i(memory_1_req),
    .data_rsp_o(memory_1_rsp),
    .cfg_req_i(s_memory0_local_config_controller_regs_req),
    .cfg_rsp_o(s_memory0_local_config_controller_regs_rsp),
    .ddr_init_done_o(ddr_init_done),
    .ddr_init_error_o(ddr_init_error)
  );
  assign memory_1_req.aw.atop = '0;
  axi_crossbar #(
    .S_COUNT(1),
    .M_COUNT(2),
    .DATA_WIDTH(64),
    .ADDR_WIDTH(64),
    .S_ID_WIDTH(4),
    .M_ID_WIDTH(4),
    .M_BASE_ADDR({64'h0000000140000000, 64'h0000000100000000}),
    .M_ADDR_WIDTH({32'd30, 32'd30})
  ) u_memory_crossbar (
    .clk(clk_i),
    .rst(!rst_ni),
    .s_axi_awid(s_memory0_local_data_target_crossbar_req.aw.id),
    .s_axi_awaddr(s_memory0_local_data_target_crossbar_req.aw.addr),
    .s_axi_awlen(s_memory0_local_data_target_crossbar_req.aw.len),
    .s_axi_awsize(s_memory0_local_data_target_crossbar_req.aw.size),
    .s_axi_awburst(s_memory0_local_data_target_crossbar_req.aw.burst),
    .s_axi_awlock(s_memory0_local_data_target_crossbar_req.aw.lock),
    .s_axi_awcache(s_memory0_local_data_target_crossbar_req.aw.cache),
    .s_axi_awprot(s_memory0_local_data_target_crossbar_req.aw.prot),
    .s_axi_awqos(s_memory0_local_data_target_crossbar_req.aw.qos),
    .s_axi_awuser(s_memory0_local_data_target_crossbar_req.aw.user),
    .s_axi_awvalid(s_memory0_local_data_target_crossbar_req.aw_valid),
    .s_axi_awready(s_memory0_local_data_target_crossbar_rsp.aw_ready),
    .s_axi_wdata(s_memory0_local_data_target_crossbar_req.w.data),
    .s_axi_wstrb(s_memory0_local_data_target_crossbar_req.w.strb),
    .s_axi_wlast(s_memory0_local_data_target_crossbar_req.w.last),
    .s_axi_wuser(s_memory0_local_data_target_crossbar_req.w.user),
    .s_axi_wvalid(s_memory0_local_data_target_crossbar_req.w_valid),
    .s_axi_wready(s_memory0_local_data_target_crossbar_rsp.w_ready),
    .s_axi_bid(s_memory0_local_data_target_crossbar_rsp.b.id),
    .s_axi_bresp(s_memory0_local_data_target_crossbar_rsp.b.resp),
    .s_axi_buser(s_memory0_local_data_target_crossbar_rsp.b.user),
    .s_axi_bvalid(s_memory0_local_data_target_crossbar_rsp.b_valid),
    .s_axi_bready(s_memory0_local_data_target_crossbar_req.b_ready),
    .s_axi_arid(s_memory0_local_data_target_crossbar_req.ar.id),
    .s_axi_araddr(s_memory0_local_data_target_crossbar_req.ar.addr),
    .s_axi_arlen(s_memory0_local_data_target_crossbar_req.ar.len),
    .s_axi_arsize(s_memory0_local_data_target_crossbar_req.ar.size),
    .s_axi_arburst(s_memory0_local_data_target_crossbar_req.ar.burst),
    .s_axi_arlock(s_memory0_local_data_target_crossbar_req.ar.lock),
    .s_axi_arcache(s_memory0_local_data_target_crossbar_req.ar.cache),
    .s_axi_arprot(s_memory0_local_data_target_crossbar_req.ar.prot),
    .s_axi_arqos(s_memory0_local_data_target_crossbar_req.ar.qos),
    .s_axi_aruser(s_memory0_local_data_target_crossbar_req.ar.user),
    .s_axi_arvalid(s_memory0_local_data_target_crossbar_req.ar_valid),
    .s_axi_arready(s_memory0_local_data_target_crossbar_rsp.ar_ready),
    .s_axi_rid(s_memory0_local_data_target_crossbar_rsp.r.id),
    .s_axi_rdata(s_memory0_local_data_target_crossbar_rsp.r.data),
    .s_axi_rresp(s_memory0_local_data_target_crossbar_rsp.r.resp),
    .s_axi_rlast(s_memory0_local_data_target_crossbar_rsp.r.last),
    .s_axi_ruser(s_memory0_local_data_target_crossbar_rsp.r.user),
    .s_axi_rvalid(s_memory0_local_data_target_crossbar_rsp.r_valid),
    .s_axi_rready(s_memory0_local_data_target_crossbar_req.r_ready),
    .m_axi_awid({memory_1_req.aw.id, memory_0_req.aw.id}),
    .m_axi_awaddr({memory_1_req.aw.addr, memory_0_req.aw.addr}),
    .m_axi_awlen({memory_1_req.aw.len, memory_0_req.aw.len}),
    .m_axi_awsize({memory_1_req.aw.size, memory_0_req.aw.size}),
    .m_axi_awburst({memory_1_req.aw.burst, memory_0_req.aw.burst}),
    .m_axi_awlock({memory_1_req.aw.lock, memory_0_req.aw.lock}),
    .m_axi_awcache({memory_1_req.aw.cache, memory_0_req.aw.cache}),
    .m_axi_awprot({memory_1_req.aw.prot, memory_0_req.aw.prot}),
    .m_axi_awqos({memory_1_req.aw.qos, memory_0_req.aw.qos}),
    .m_axi_awregion({memory_1_req.aw.region, memory_0_req.aw.region}),
    .m_axi_awuser({memory_1_req.aw.user, memory_0_req.aw.user}),
    .m_axi_awvalid({memory_1_req.aw_valid, memory_0_req.aw_valid}),
    .m_axi_awready({memory_1_rsp.aw_ready, memory_0_rsp.aw_ready}),
    .m_axi_wdata({memory_1_req.w.data, memory_0_req.w.data}),
    .m_axi_wstrb({memory_1_req.w.strb, memory_0_req.w.strb}),
    .m_axi_wlast({memory_1_req.w.last, memory_0_req.w.last}),
    .m_axi_wuser({memory_1_req.w.user, memory_0_req.w.user}),
    .m_axi_wvalid({memory_1_req.w_valid, memory_0_req.w_valid}),
    .m_axi_wready({memory_1_rsp.w_ready, memory_0_rsp.w_ready}),
    .m_axi_bid({memory_1_rsp.b.id, memory_0_rsp.b.id}),
    .m_axi_bresp({memory_1_rsp.b.resp, memory_0_rsp.b.resp}),
    .m_axi_buser({memory_1_rsp.b.user, memory_0_rsp.b.user}),
    .m_axi_bvalid({memory_1_rsp.b_valid, memory_0_rsp.b_valid}),
    .m_axi_bready({memory_1_req.b_ready, memory_0_req.b_ready}),
    .m_axi_arid({memory_1_req.ar.id, memory_0_req.ar.id}),
    .m_axi_araddr({memory_1_req.ar.addr, memory_0_req.ar.addr}),
    .m_axi_arlen({memory_1_req.ar.len, memory_0_req.ar.len}),
    .m_axi_arsize({memory_1_req.ar.size, memory_0_req.ar.size}),
    .m_axi_arburst({memory_1_req.ar.burst, memory_0_req.ar.burst}),
    .m_axi_arlock({memory_1_req.ar.lock, memory_0_req.ar.lock}),
    .m_axi_arcache({memory_1_req.ar.cache, memory_0_req.ar.cache}),
    .m_axi_arprot({memory_1_req.ar.prot, memory_0_req.ar.prot}),
    .m_axi_arqos({memory_1_req.ar.qos, memory_0_req.ar.qos}),
    .m_axi_arregion({memory_1_req.ar.region, memory_0_req.ar.region}),
    .m_axi_aruser({memory_1_req.ar.user, memory_0_req.ar.user}),
    .m_axi_arvalid({memory_1_req.ar_valid, memory_0_req.ar_valid}),
    .m_axi_arready({memory_1_rsp.ar_ready, memory_0_rsp.ar_ready}),
    .m_axi_rid({memory_1_rsp.r.id, memory_0_rsp.r.id}),
    .m_axi_rdata({memory_1_rsp.r.data, memory_0_rsp.r.data}),
    .m_axi_rresp({memory_1_rsp.r.resp, memory_0_rsp.r.resp}),
    .m_axi_rlast({memory_1_rsp.r.last, memory_0_rsp.r.last}),
    .m_axi_ruser({memory_1_rsp.r.user, memory_0_rsp.r.user}),
    .m_axi_rvalid({memory_1_rsp.r_valid, memory_0_rsp.r_valid}),
    .m_axi_rready({memory_1_req.r_ready, memory_0_req.r_ready})
  );
  axi_err_slv #(
    .AxiIdWidth(1),
    .axi_req_t(floo_xezim_pcie0_local_config_noc_pkg::axi_out_req_t),
    .axi_resp_t(floo_xezim_pcie0_local_config_noc_pkg::axi_out_rsp_t),
    .ATOPs(0)
  ) u_reserved_s_pcie0_local_config_controller_regs (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .slv_req_i(s_pcie0_local_config_controller_regs_req),
    .slv_resp_o(s_pcie0_local_config_controller_regs_rsp)
  );
  axi_sram_target #(
    .req_t(floo_xezim_pcie0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_pcie0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(5),
    .Base(64'h0000000012000000),
    .Bytes(16384),
    .ReadOnly(0),
    .InitFile("")
  ) u_s_pcie0_local_data_sram (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(s_pcie0_local_data_sram_req),
    .rsp_o(s_pcie0_local_data_sram_rsp),
    .mon_valid_o(pcie_sram_valid),
    .mon_write_o(pcie_sram_write),
    .mon_addr_o(pcie_sram_addr),
    .mon_data_o(pcie_sram_data),
    .mon_strb_o(pcie_sram_strb)
  );
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin pcie_sram_write_count <= '0; pcie_sram_read_count <= '0;
      pcie_sram_last_write_addr <= '0; pcie_sram_last_read_addr <= '0; end
    else if (pcie_sram_valid) begin
      if (pcie_sram_write) begin pcie_sram_write_count <= pcie_sram_write_count + 1;
        pcie_sram_last_write_addr <= pcie_sram_addr; end
      else begin pcie_sram_read_count <= pcie_sram_read_count + 1;
        pcie_sram_last_read_addr <= pcie_sram_addr; end
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) begin rom_reads_o <= '0; flash_reads_o <= '0; end
    else begin
      if (boot_rom_valid && !boot_rom_write) rom_reads_o <= rom_reads_o + 1;
      if (boot_flash_valid && !boot_flash_write) flash_reads_o <= flash_reads_o + 1;
    end
endmodule
