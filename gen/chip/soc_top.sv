// Generated chip boot + DMA configuration: see gen/chip/manifest.json.
module soc_top #(parameter bit ProbeEnable = 0, DmaEnable = 0, DmaTestMode = 0) (input logic clk_i, rst_ni,
  input logic [1:0] hold_mask_i,
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
  input logic cfgprobe_rready
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
    .s_memory0_local_data_target_crossbar_rready(s_memory0_local_data_target_crossbar_req.r_ready)
  );
  initial if (DmaTestMode && (!DmaEnable || !ProbeEnable))
    $fatal(1, "DMA host mode requires active DMA and host probe");
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
  assign cfgprobe_awready = m_compute0_local_config_cpu_rsp.aw_ready;
  assign cfgprobe_req.w.data = cfgprobe_wdata;
  assign cfgprobe_req.w.strb = cfgprobe_wstrb;
  assign cfgprobe_req.w.last = cfgprobe_wlast;
  assign cfgprobe_req.w_valid = cfgprobe_wvalid;
  assign cfgprobe_wready = m_compute0_local_config_cpu_rsp.w_ready;
  assign cfgprobe_bid = m_compute0_local_config_cpu_rsp.b.id;
  assign cfgprobe_bresp = m_compute0_local_config_cpu_rsp.b.resp;
  assign cfgprobe_bvalid = m_compute0_local_config_cpu_rsp.b_valid;
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
  assign cfgprobe_arready = m_compute0_local_config_cpu_rsp.ar_ready;
  assign cfgprobe_rid = m_compute0_local_config_cpu_rsp.r.id;
  assign cfgprobe_rdata = m_compute0_local_config_cpu_rsp.r.data;
  assign cfgprobe_rresp = m_compute0_local_config_cpu_rsp.r.resp;
  assign cfgprobe_rlast = m_compute0_local_config_cpu_rsp.r.last;
  assign cfgprobe_rvalid = m_compute0_local_config_cpu_rsp.r_valid;
  assign cfgprobe_req.r_ready = cfgprobe_rready;
  assign cfgprobe_req.aw.atop = '0;
  assign cfgprobe_req.aw.user = '0;
  assign cfgprobe_req.w.user = '0;
  assign cfgprobe_req.ar.user = '0;
  lite_req_t cpu_0_req;
  lite_resp_t cpu_0_rsp;
  assign cpu_reset_n[0] = (rst_ni) && !DmaTestMode;
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
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t cpu_data_0_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t cpu_data_0_rsp;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t cpu_config_0_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_rsp_t cpu_config_0_rsp;
  assign m_compute0_local_data_cpu_req = DmaTestMode ? probe_req : cpu_data_0_req;
  assign cpu_data_0_rsp = DmaTestMode ? '0 : m_compute0_local_data_cpu_rsp;
  assign m_compute0_local_config_cpu_req = DmaTestMode ? cfgprobe_req : cpu_config_0_req;
  assign cpu_config_0_rsp = DmaTestMode ? '0 : m_compute0_local_config_cpu_rsp;
  cpu_noc_adapter #(
    .data_req_t(floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t),
    .data_rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t),
    .cfg_req_t(floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t),
    .cfg_rsp_t(floo_xezim_compute0_local_config_noc_pkg::axi_in_rsp_t),
    .ConfigBase(32'h40000000),
    .ConfigEnd(32'h40031000)
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
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t probe_req;
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
  assign probe_awready = DmaTestMode ? m_compute0_local_data_cpu_rsp.aw_ready : m_compute0_local_data_dma_rsp.aw_ready;
  assign probe_req.w.data = probe_wdata;
  assign probe_req.w.strb = probe_wstrb;
  assign probe_req.w.last = probe_wlast;
  assign probe_req.w_valid = probe_wvalid;
  assign probe_wready = DmaTestMode ? m_compute0_local_data_cpu_rsp.w_ready : m_compute0_local_data_dma_rsp.w_ready;
  assign probe_bid = DmaTestMode ? m_compute0_local_data_cpu_rsp.b.id : m_compute0_local_data_dma_rsp.b.id;
  assign probe_bresp = DmaTestMode ? m_compute0_local_data_cpu_rsp.b.resp : m_compute0_local_data_dma_rsp.b.resp;
  assign probe_bvalid = DmaTestMode ? m_compute0_local_data_cpu_rsp.b_valid : m_compute0_local_data_dma_rsp.b_valid;
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
  assign probe_arready = DmaTestMode ? m_compute0_local_data_cpu_rsp.ar_ready : m_compute0_local_data_dma_rsp.ar_ready;
  assign probe_rid = DmaTestMode ? m_compute0_local_data_cpu_rsp.r.id : m_compute0_local_data_dma_rsp.r.id;
  assign probe_rdata = DmaTestMode ? m_compute0_local_data_cpu_rsp.r.data : m_compute0_local_data_dma_rsp.r.data;
  assign probe_rresp = DmaTestMode ? m_compute0_local_data_cpu_rsp.r.resp : m_compute0_local_data_dma_rsp.r.resp;
  assign probe_rlast = DmaTestMode ? m_compute0_local_data_cpu_rsp.r.last : m_compute0_local_data_dma_rsp.r.last;
  assign probe_rvalid = DmaTestMode ? m_compute0_local_data_cpu_rsp.r_valid : m_compute0_local_data_dma_rsp.r_valid;
  assign probe_req.r_ready = probe_rready;
  assign probe_req.aw.atop = '0;
  assign probe_req.aw.user = '0;
  assign probe_req.w.user = '0;
  assign probe_req.ar.user = '0;
  if (DmaEnable) begin: gen_dma_compute0
  soc_idma_engine u_dma_compute0 (
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
    .dma_awid(m_compute0_local_data_dma_req.aw.id),
    .dma_awaddr(m_compute0_local_data_dma_req.aw.addr),
    .dma_awlen(m_compute0_local_data_dma_req.aw.len),
    .dma_awsize(m_compute0_local_data_dma_req.aw.size),
    .dma_awburst(m_compute0_local_data_dma_req.aw.burst),
    .dma_awlock(m_compute0_local_data_dma_req.aw.lock),
    .dma_awcache(m_compute0_local_data_dma_req.aw.cache),
    .dma_awprot(m_compute0_local_data_dma_req.aw.prot),
    .dma_awqos(m_compute0_local_data_dma_req.aw.qos),
    .dma_awregion(m_compute0_local_data_dma_req.aw.region),
    .dma_awvalid(m_compute0_local_data_dma_req.aw_valid),
    .dma_awready(m_compute0_local_data_dma_rsp.aw_ready),
    .dma_wdata(m_compute0_local_data_dma_req.w.data),
    .dma_wstrb(m_compute0_local_data_dma_req.w.strb),
    .dma_wlast(m_compute0_local_data_dma_req.w.last),
    .dma_wvalid(m_compute0_local_data_dma_req.w_valid),
    .dma_wready(m_compute0_local_data_dma_rsp.w_ready),
    .dma_bid(m_compute0_local_data_dma_rsp.b.id),
    .dma_bresp(m_compute0_local_data_dma_rsp.b.resp),
    .dma_bvalid(m_compute0_local_data_dma_rsp.b_valid),
    .dma_bready(m_compute0_local_data_dma_req.b_ready),
    .dma_arid(m_compute0_local_data_dma_req.ar.id),
    .dma_araddr(m_compute0_local_data_dma_req.ar.addr),
    .dma_arlen(m_compute0_local_data_dma_req.ar.len),
    .dma_arsize(m_compute0_local_data_dma_req.ar.size),
    .dma_arburst(m_compute0_local_data_dma_req.ar.burst),
    .dma_arlock(m_compute0_local_data_dma_req.ar.lock),
    .dma_arcache(m_compute0_local_data_dma_req.ar.cache),
    .dma_arprot(m_compute0_local_data_dma_req.ar.prot),
    .dma_arqos(m_compute0_local_data_dma_req.ar.qos),
    .dma_arregion(m_compute0_local_data_dma_req.ar.region),
    .dma_arvalid(m_compute0_local_data_dma_req.ar_valid),
    .dma_arready(m_compute0_local_data_dma_rsp.ar_ready),
    .dma_rid(m_compute0_local_data_dma_rsp.r.id),
    .dma_rdata(m_compute0_local_data_dma_rsp.r.data),
    .dma_rresp(m_compute0_local_data_dma_rsp.r.resp),
    .dma_rlast(m_compute0_local_data_dma_rsp.r.last),
    .dma_rvalid(m_compute0_local_data_dma_rsp.r_valid),
    .dma_rready(m_compute0_local_data_dma_req.r_ready)
  );
    assign m_compute0_local_data_dma_req.aw.atop = '0;
    assign m_compute0_local_data_dma_req.aw.user = '0;
    assign m_compute0_local_data_dma_req.w.user = '0;
    assign m_compute0_local_data_dma_req.ar.user = '0;
  end else begin: gen_dma_disabled_compute0
    assign m_compute0_local_data_dma_req = ProbeEnable ? probe_req : '0;
    assign dma_irq_o[0] = 1'b0;
  end
  lite_req_t cpu_1_req;
  lite_resp_t cpu_1_rsp;
  assign cpu_reset_n[1] = (rst_ni && reset_regs[0][0] && !hold_mask_i[1]) && !DmaTestMode;
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
    .ConfigEnd(32'h40031000)
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
  soc_idma_engine u_dma_compute1 (
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
    .InitFile("gen/chip/flash.hex")
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
    .InitFile("gen/chip/bootrom.hex")
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
  axi_err_slv #(
    .AxiIdWidth(1),
    .axi_req_t(floo_xezim_memory0_local_config_noc_pkg::axi_out_req_t),
    .axi_resp_t(floo_xezim_memory0_local_config_noc_pkg::axi_out_rsp_t),
    .ATOPs(0)
  ) u_unused_s_memory0_local_config_controller_regs (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .slv_req_i(s_memory0_local_config_controller_regs_req),
    .slv_resp_o(s_memory0_local_config_controller_regs_rsp)
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
  axi_sram_target #(
    .req_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t),
    .rsp_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t),
    .IdWidth(4),
    .Base(64'h0000000140000000),
    .Bytes(65536)
  ) u_memory_model_1 (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .req_i(memory_1_req),
    .rsp_o(memory_1_rsp),
    .mon_valid_o(),
    .mon_write_o(),
    .mon_addr_o(),
    .mon_data_o(),
    .mon_strb_o()
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
  always_ff @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) begin rom_reads_o <= '0; flash_reads_o <= '0; end
    else begin
      if (boot_rom_valid && !boot_rom_write) rom_reads_o <= rom_reads_o + 1;
      if (boot_flash_valid && !boot_flash_write) flash_reads_o <= flash_reads_o + 1;
    end
endmodule
