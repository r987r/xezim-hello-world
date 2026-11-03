`timescale 1ns/1ps
// Generated executable composition of the actual eight FlooNoCs.
// NO pass-through simulation model substitutes for a router.
module supernoc_tb;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  initial begin repeat (8) @(posedge clk); rst_n=1; end
  initial begin #100000; $fatal(1,"super-NoC traffic timeout"); end
  floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t compute0_local_config__cpu_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_rsp_t compute0_local_config__cpu_rsp;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_req_t compute0_local_config__global_in_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_in_rsp_t compute0_local_config__global_in_rsp;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t compute0_local_config__dma_regs_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t compute0_local_config__dma_regs_rsp;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t compute0_local_config__reset_ctrl_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t compute0_local_config__reset_ctrl_rsp;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t compute0_local_config__global_out_req;
  floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t compute0_local_config__global_out_rsp;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t compute0_local_data__cpu_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t compute0_local_data__cpu_rsp;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t compute0_local_data__dma_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t compute0_local_data__dma_rsp;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_req_t compute0_local_data__global_in_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_in_rsp_t compute0_local_data__global_in_rsp;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t compute0_local_data__sram_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t compute0_local_data__sram_rsp;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t compute0_local_data__global_out_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t compute0_local_data__global_out_rsp;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t compute0_local_data__boot_rom_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t compute0_local_data__boot_rom_rsp;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t compute0_local_data__boot_flash_req;
  floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t compute0_local_data__boot_flash_rsp;
  floo_xezim_compute1_local_config_noc_pkg::axi_in_req_t compute1_local_config__cpu_req;
  floo_xezim_compute1_local_config_noc_pkg::axi_in_rsp_t compute1_local_config__cpu_rsp;
  floo_xezim_compute1_local_config_noc_pkg::axi_in_req_t compute1_local_config__global_in_req;
  floo_xezim_compute1_local_config_noc_pkg::axi_in_rsp_t compute1_local_config__global_in_rsp;
  floo_xezim_compute1_local_config_noc_pkg::axi_out_req_t compute1_local_config__dma_regs_req;
  floo_xezim_compute1_local_config_noc_pkg::axi_out_rsp_t compute1_local_config__dma_regs_rsp;
  floo_xezim_compute1_local_config_noc_pkg::axi_out_req_t compute1_local_config__global_out_req;
  floo_xezim_compute1_local_config_noc_pkg::axi_out_rsp_t compute1_local_config__global_out_rsp;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_req_t compute1_local_data__cpu_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_rsp_t compute1_local_data__cpu_rsp;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_req_t compute1_local_data__dma_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_rsp_t compute1_local_data__dma_rsp;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_req_t compute1_local_data__global_in_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_in_rsp_t compute1_local_data__global_in_rsp;
  floo_xezim_compute1_local_data_noc_pkg::axi_out_req_t compute1_local_data__sram_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_out_rsp_t compute1_local_data__sram_rsp;
  floo_xezim_compute1_local_data_noc_pkg::axi_out_req_t compute1_local_data__global_out_req;
  floo_xezim_compute1_local_data_noc_pkg::axi_out_rsp_t compute1_local_data__global_out_rsp;
  floo_xezim_global_config_noc_pkg::axi_in_req_t global_config__compute0_req;
  floo_xezim_global_config_noc_pkg::axi_in_rsp_t global_config__compute0_rsp;
  floo_xezim_global_config_noc_pkg::axi_in_req_t global_config__compute1_req;
  floo_xezim_global_config_noc_pkg::axi_in_rsp_t global_config__compute1_rsp;
  floo_xezim_global_config_noc_pkg::axi_out_req_t global_config__compute0_regs_req;
  floo_xezim_global_config_noc_pkg::axi_out_rsp_t global_config__compute0_regs_rsp;
  floo_xezim_global_config_noc_pkg::axi_out_req_t global_config__compute1_regs_req;
  floo_xezim_global_config_noc_pkg::axi_out_rsp_t global_config__compute1_regs_rsp;
  floo_xezim_global_config_noc_pkg::axi_out_req_t global_config__memory0_regs_req;
  floo_xezim_global_config_noc_pkg::axi_out_rsp_t global_config__memory0_regs_rsp;
  floo_xezim_global_data_noc_pkg::axi_in_req_t global_data__compute0_req;
  floo_xezim_global_data_noc_pkg::axi_in_rsp_t global_data__compute0_rsp;
  floo_xezim_global_data_noc_pkg::axi_in_req_t global_data__compute1_req;
  floo_xezim_global_data_noc_pkg::axi_in_rsp_t global_data__compute1_rsp;
  floo_xezim_global_data_noc_pkg::axi_out_req_t global_data__compute0_sram_req;
  floo_xezim_global_data_noc_pkg::axi_out_rsp_t global_data__compute0_sram_rsp;
  floo_xezim_global_data_noc_pkg::axi_out_req_t global_data__compute1_sram_req;
  floo_xezim_global_data_noc_pkg::axi_out_rsp_t global_data__compute1_sram_rsp;
  floo_xezim_global_data_noc_pkg::axi_out_req_t global_data__memory_ingress0_req;
  floo_xezim_global_data_noc_pkg::axi_out_rsp_t global_data__memory_ingress0_rsp;
  floo_xezim_global_data_noc_pkg::axi_out_req_t global_data__memory_ingress1_req;
  floo_xezim_global_data_noc_pkg::axi_out_rsp_t global_data__memory_ingress1_rsp;
  floo_xezim_memory0_local_config_noc_pkg::axi_in_req_t memory0_local_config__global_in_req;
  floo_xezim_memory0_local_config_noc_pkg::axi_in_rsp_t memory0_local_config__global_in_rsp;
  floo_xezim_memory0_local_config_noc_pkg::axi_out_req_t memory0_local_config__controller_regs_req;
  floo_xezim_memory0_local_config_noc_pkg::axi_out_rsp_t memory0_local_config__controller_regs_rsp;
  floo_xezim_memory0_local_data_noc_pkg::axi_in_req_t memory0_local_data__memory_ingress0_req;
  floo_xezim_memory0_local_data_noc_pkg::axi_in_rsp_t memory0_local_data__memory_ingress0_rsp;
  floo_xezim_memory0_local_data_noc_pkg::axi_in_req_t memory0_local_data__memory_ingress1_req;
  floo_xezim_memory0_local_data_noc_pkg::axi_in_rsp_t memory0_local_data__memory_ingress1_rsp;
  floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t memory0_local_data__target_crossbar_req;
  floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t memory0_local_data__target_crossbar_rsp;
  assign global_data__compute0_req = compute0_local_data__global_out_req;
  assign compute0_local_data__global_out_rsp = global_data__compute0_rsp;
  assign compute0_local_data__global_in_req = global_data__compute0_sram_req;
  assign global_data__compute0_sram_rsp = compute0_local_data__global_in_rsp;
  assign global_config__compute0_req = compute0_local_config__global_out_req;
  assign compute0_local_config__global_out_rsp = global_config__compute0_rsp;
  assign compute0_local_config__global_in_req = global_config__compute0_regs_req;
  assign global_config__compute0_regs_rsp = compute0_local_config__global_in_rsp;
  assign global_data__compute1_req = compute1_local_data__global_out_req;
  assign compute1_local_data__global_out_rsp = global_data__compute1_rsp;
  assign compute1_local_data__global_in_req = global_data__compute1_sram_req;
  assign global_data__compute1_sram_rsp = compute1_local_data__global_in_rsp;
  assign global_config__compute1_req = compute1_local_config__global_out_req;
  assign compute1_local_config__global_out_rsp = global_config__compute1_rsp;
  assign compute1_local_config__global_in_req = global_config__compute1_regs_req;
  assign global_config__compute1_regs_rsp = compute1_local_config__global_in_rsp;
  assign memory0_local_config__global_in_req = global_config__memory0_regs_req;
  assign global_config__memory0_regs_rsp = memory0_local_config__global_in_rsp;
  assign memory0_local_data__memory_ingress0_req = global_data__memory_ingress0_req;
  assign global_data__memory_ingress0_rsp = memory0_local_data__memory_ingress0_rsp;
  assign memory0_local_data__memory_ingress1_req = global_data__memory_ingress1_req;
  assign global_data__memory_ingress1_rsp = memory0_local_data__memory_ingress1_rsp;
  AXI_BUS_DV #(.AXI_ADDR_WIDTH(64), .AXI_DATA_WIDTH(64), .AXI_ID_WIDTH(4), .AXI_USER_WIDTH(1)) bus_compute0_local_data__cpu(clk);
  `AXI_ASSIGN_TO_REQ(compute0_local_data__cpu_req, bus_compute0_local_data__cpu)
  `AXI_ASSIGN_FROM_RESP(bus_compute0_local_data__cpu, compute0_local_data__cpu_rsp)
  typedef axi_test::axi_driver #(.AW(64), .DW(64), .IW(4), .UW(1), .TA(2ns), .TT(8ns)) driver_compute0_local_data__cpu_t;
  driver_compute0_local_data__cpu_t driver_compute0_local_data__cpu;
  AXI_BUS_DV #(.AXI_ADDR_WIDTH(64), .AXI_DATA_WIDTH(64), .AXI_ID_WIDTH(4), .AXI_USER_WIDTH(1)) bus_compute1_local_data__cpu(clk);
  `AXI_ASSIGN_TO_REQ(compute1_local_data__cpu_req, bus_compute1_local_data__cpu)
  `AXI_ASSIGN_FROM_RESP(bus_compute1_local_data__cpu, compute1_local_data__cpu_rsp)
  typedef axi_test::axi_driver #(.AW(64), .DW(64), .IW(4), .UW(1), .TA(2ns), .TT(8ns)) driver_compute1_local_data__cpu_t;
  driver_compute1_local_data__cpu_t driver_compute1_local_data__cpu;
  AXI_BUS_DV #(.AXI_ADDR_WIDTH(32), .AXI_DATA_WIDTH(32), .AXI_ID_WIDTH(1), .AXI_USER_WIDTH(1)) bus_compute0_local_config__cpu(clk);
  `AXI_ASSIGN_TO_REQ(compute0_local_config__cpu_req, bus_compute0_local_config__cpu)
  `AXI_ASSIGN_FROM_RESP(bus_compute0_local_config__cpu, compute0_local_config__cpu_rsp)
  typedef axi_test::axi_driver #(.AW(32), .DW(32), .IW(1), .UW(1), .TA(2ns), .TT(8ns)) driver_compute0_local_config__cpu_t;
  driver_compute0_local_config__cpu_t driver_compute0_local_config__cpu;
  assign compute0_local_data__dma_req = '0;
  assign compute1_local_config__cpu_req = '0;
  assign compute1_local_data__dma_req = '0;
  axi_sim_mem #(.AddrWidth(32), .DataWidth(32), .IdWidth(1), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t)) memory_compute0_local_config__dma_regs (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(compute0_local_config__dma_regs_req), .axi_rsp_o(compute0_local_config__dma_regs_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(32), .DataWidth(32), .IdWidth(1), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_compute0_local_config_noc_pkg::axi_out_rsp_t)) memory_compute0_local_config__reset_ctrl (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(compute0_local_config__reset_ctrl_req), .axi_rsp_o(compute0_local_config__reset_ctrl_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(64), .DataWidth(64), .IdWidth(5), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t)) memory_compute0_local_data__sram (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(compute0_local_data__sram_req), .axi_rsp_o(compute0_local_data__sram_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(64), .DataWidth(64), .IdWidth(5), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t)) memory_compute0_local_data__boot_rom (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(compute0_local_data__boot_rom_req), .axi_rsp_o(compute0_local_data__boot_rom_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(64), .DataWidth(64), .IdWidth(5), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_compute0_local_data_noc_pkg::axi_out_rsp_t)) memory_compute0_local_data__boot_flash (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(compute0_local_data__boot_flash_req), .axi_rsp_o(compute0_local_data__boot_flash_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(32), .DataWidth(32), .IdWidth(1), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_compute1_local_config_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_compute1_local_config_noc_pkg::axi_out_rsp_t)) memory_compute1_local_config__dma_regs (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(compute1_local_config__dma_regs_req), .axi_rsp_o(compute1_local_config__dma_regs_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(64), .DataWidth(64), .IdWidth(5), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_compute1_local_data_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_compute1_local_data_noc_pkg::axi_out_rsp_t)) memory_compute1_local_data__sram (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(compute1_local_data__sram_req), .axi_rsp_o(compute1_local_data__sram_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(32), .DataWidth(32), .IdWidth(1), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_memory0_local_config_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_memory0_local_config_noc_pkg::axi_out_rsp_t)) memory_memory0_local_config__controller_regs (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(memory0_local_config__controller_regs_req), .axi_rsp_o(memory0_local_config__controller_regs_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  axi_sim_mem #(.AddrWidth(64), .DataWidth(64), .IdWidth(4), .UserWidth(1), .NumPorts(1), .UninitializedData("zeros"), .axi_req_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_req_t), .axi_rsp_t(floo_xezim_memory0_local_data_noc_pkg::axi_out_rsp_t)) memory_memory0_local_data__target_crossbar (
    .clk_i(clk), .rst_ni(rst_n),
    .axi_req_i(memory0_local_data__target_crossbar_req), .axi_rsp_o(memory0_local_data__target_crossbar_rsp),
    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),
    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),
    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),
    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());
  floo_xezim_compute0_local_config_noc u_compute0_local_config (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .cpu_axi_in_req_i(compute0_local_config__cpu_req),
    .cpu_axi_in_rsp_o(compute0_local_config__cpu_rsp),
    .global_in_axi_in_req_i(compute0_local_config__global_in_req),
    .global_in_axi_in_rsp_o(compute0_local_config__global_in_rsp),
    .dma_regs_axi_out_req_o(compute0_local_config__dma_regs_req),
    .dma_regs_axi_out_rsp_i(compute0_local_config__dma_regs_rsp),
    .reset_ctrl_axi_out_req_o(compute0_local_config__reset_ctrl_req),
    .reset_ctrl_axi_out_rsp_i(compute0_local_config__reset_ctrl_rsp),
    .global_out_axi_out_req_o(compute0_local_config__global_out_req),
    .global_out_axi_out_rsp_i(compute0_local_config__global_out_rsp));
  floo_xezim_compute0_local_data_noc u_compute0_local_data (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .cpu_axi_in_req_i(compute0_local_data__cpu_req),
    .cpu_axi_in_rsp_o(compute0_local_data__cpu_rsp),
    .dma_axi_in_req_i(compute0_local_data__dma_req),
    .dma_axi_in_rsp_o(compute0_local_data__dma_rsp),
    .global_in_axi_in_req_i(compute0_local_data__global_in_req),
    .global_in_axi_in_rsp_o(compute0_local_data__global_in_rsp),
    .sram_axi_out_req_o(compute0_local_data__sram_req),
    .sram_axi_out_rsp_i(compute0_local_data__sram_rsp),
    .global_out_axi_out_req_o(compute0_local_data__global_out_req),
    .global_out_axi_out_rsp_i(compute0_local_data__global_out_rsp),
    .boot_rom_axi_out_req_o(compute0_local_data__boot_rom_req),
    .boot_rom_axi_out_rsp_i(compute0_local_data__boot_rom_rsp),
    .boot_flash_axi_out_req_o(compute0_local_data__boot_flash_req),
    .boot_flash_axi_out_rsp_i(compute0_local_data__boot_flash_rsp));
  floo_xezim_compute1_local_config_noc u_compute1_local_config (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .cpu_axi_in_req_i(compute1_local_config__cpu_req),
    .cpu_axi_in_rsp_o(compute1_local_config__cpu_rsp),
    .global_in_axi_in_req_i(compute1_local_config__global_in_req),
    .global_in_axi_in_rsp_o(compute1_local_config__global_in_rsp),
    .dma_regs_axi_out_req_o(compute1_local_config__dma_regs_req),
    .dma_regs_axi_out_rsp_i(compute1_local_config__dma_regs_rsp),
    .global_out_axi_out_req_o(compute1_local_config__global_out_req),
    .global_out_axi_out_rsp_i(compute1_local_config__global_out_rsp));
  floo_xezim_compute1_local_data_noc u_compute1_local_data (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .cpu_axi_in_req_i(compute1_local_data__cpu_req),
    .cpu_axi_in_rsp_o(compute1_local_data__cpu_rsp),
    .dma_axi_in_req_i(compute1_local_data__dma_req),
    .dma_axi_in_rsp_o(compute1_local_data__dma_rsp),
    .global_in_axi_in_req_i(compute1_local_data__global_in_req),
    .global_in_axi_in_rsp_o(compute1_local_data__global_in_rsp),
    .sram_axi_out_req_o(compute1_local_data__sram_req),
    .sram_axi_out_rsp_i(compute1_local_data__sram_rsp),
    .global_out_axi_out_req_o(compute1_local_data__global_out_req),
    .global_out_axi_out_rsp_i(compute1_local_data__global_out_rsp));
  floo_xezim_global_config_noc u_global_config (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .compute0_axi_in_req_i(global_config__compute0_req),
    .compute0_axi_in_rsp_o(global_config__compute0_rsp),
    .compute1_axi_in_req_i(global_config__compute1_req),
    .compute1_axi_in_rsp_o(global_config__compute1_rsp),
    .compute0_regs_axi_out_req_o(global_config__compute0_regs_req),
    .compute0_regs_axi_out_rsp_i(global_config__compute0_regs_rsp),
    .compute1_regs_axi_out_req_o(global_config__compute1_regs_req),
    .compute1_regs_axi_out_rsp_i(global_config__compute1_regs_rsp),
    .memory0_regs_axi_out_req_o(global_config__memory0_regs_req),
    .memory0_regs_axi_out_rsp_i(global_config__memory0_regs_rsp));
  floo_xezim_global_data_noc u_global_data (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .compute0_axi_in_req_i(global_data__compute0_req),
    .compute0_axi_in_rsp_o(global_data__compute0_rsp),
    .compute1_axi_in_req_i(global_data__compute1_req),
    .compute1_axi_in_rsp_o(global_data__compute1_rsp),
    .compute0_sram_axi_out_req_o(global_data__compute0_sram_req),
    .compute0_sram_axi_out_rsp_i(global_data__compute0_sram_rsp),
    .compute1_sram_axi_out_req_o(global_data__compute1_sram_req),
    .compute1_sram_axi_out_rsp_i(global_data__compute1_sram_rsp),
    .memory_ingress0_axi_out_req_o(global_data__memory_ingress0_req),
    .memory_ingress0_axi_out_rsp_i(global_data__memory_ingress0_rsp),
    .memory_ingress1_axi_out_req_o(global_data__memory_ingress1_req),
    .memory_ingress1_axi_out_rsp_i(global_data__memory_ingress1_rsp));
  floo_xezim_memory0_local_config_noc u_memory0_local_config (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .global_in_axi_in_req_i(memory0_local_config__global_in_req),
    .global_in_axi_in_rsp_o(memory0_local_config__global_in_rsp),
    .controller_regs_axi_out_req_o(memory0_local_config__controller_regs_req),
    .controller_regs_axi_out_rsp_i(memory0_local_config__controller_regs_rsp));
  floo_xezim_memory0_local_data_noc u_memory0_local_data (
    .clk_i(clk),
    .rst_ni(rst_n),
    .test_enable_i(1'b0),
    .memory_ingress0_axi_in_req_i(memory0_local_data__memory_ingress0_req),
    .memory_ingress0_axi_in_rsp_o(memory0_local_data__memory_ingress0_rsp),
    .memory_ingress1_axi_in_req_i(memory0_local_data__memory_ingress1_req),
    .memory_ingress1_axi_in_rsp_o(memory0_local_data__memory_ingress1_rsp),
    .target_crossbar_axi_out_req_o(memory0_local_data__target_crossbar_req),
    .target_crossbar_axi_out_rsp_i(memory0_local_data__target_crossbar_rsp));
  task automatic write_compute0_local_data__cpu(input logic [63:0] addr, input logic [63:0] payload);
    driver_compute0_local_data__cpu_t::ax_beat_t awbeat = new;
    driver_compute0_local_data__cpu_t::w_beat_t wbeat = new;
    driver_compute0_local_data__cpu_t::b_beat_t bbeat;
    awbeat.ax_id = 1;
    awbeat.ax_addr = addr;
    awbeat.ax_len = 0;
    awbeat.ax_size = $clog2(64/8);
    awbeat.ax_burst = axi_pkg::BURST_INCR;
    wbeat.w_data = payload;
    wbeat.w_strb = '1;
    wbeat.w_last = 1;
    driver_compute0_local_data__cpu.send_aw(awbeat);
    driver_compute0_local_data__cpu.send_w(wbeat);
    driver_compute0_local_data__cpu.recv_b(bbeat);
    if (bbeat.b_resp !== axi_pkg::RESP_OKAY || bbeat.b_id !== 1)
      $fatal(1, "FAIL compute0_local_data__cpu write addr=%h B id=%h resp=%h", addr, bbeat.b_id, bbeat.b_resp);
  endtask
  task automatic read_compute0_local_data__cpu(input logic [63:0] addr, input logic [63:0] expected);
    driver_compute0_local_data__cpu_t::ax_beat_t ar = new;
    driver_compute0_local_data__cpu_t::r_beat_t rbeat;
    ar.ax_id = 1;
    ar.ax_addr = addr;
    ar.ax_len = 0;
    ar.ax_size = $clog2(64/8);
    ar.ax_burst = axi_pkg::BURST_INCR;
    driver_compute0_local_data__cpu.send_ar(ar);
    driver_compute0_local_data__cpu.recv_r(rbeat);
    if (rbeat.r_data !== expected || rbeat.r_resp !== axi_pkg::RESP_OKAY ||
        rbeat.r_id !== 1 || rbeat.r_last !== 1)
      $fatal(1, "FAIL compute0_local_data__cpu read addr=%h expected=%h got=%h", addr, expected, rbeat.r_data);
  endtask
  task automatic write_compute1_local_data__cpu(input logic [63:0] addr, input logic [63:0] payload);
    driver_compute1_local_data__cpu_t::ax_beat_t awbeat = new;
    driver_compute1_local_data__cpu_t::w_beat_t wbeat = new;
    driver_compute1_local_data__cpu_t::b_beat_t bbeat;
    awbeat.ax_id = 1;
    awbeat.ax_addr = addr;
    awbeat.ax_len = 0;
    awbeat.ax_size = $clog2(64/8);
    awbeat.ax_burst = axi_pkg::BURST_INCR;
    wbeat.w_data = payload;
    wbeat.w_strb = '1;
    wbeat.w_last = 1;
    driver_compute1_local_data__cpu.send_aw(awbeat);
    driver_compute1_local_data__cpu.send_w(wbeat);
    driver_compute1_local_data__cpu.recv_b(bbeat);
    if (bbeat.b_resp !== axi_pkg::RESP_OKAY || bbeat.b_id !== 1)
      $fatal(1, "FAIL compute1_local_data__cpu write addr=%h B id=%h resp=%h", addr, bbeat.b_id, bbeat.b_resp);
  endtask
  task automatic read_compute1_local_data__cpu(input logic [63:0] addr, input logic [63:0] expected);
    driver_compute1_local_data__cpu_t::ax_beat_t ar = new;
    driver_compute1_local_data__cpu_t::r_beat_t rbeat;
    ar.ax_id = 1;
    ar.ax_addr = addr;
    ar.ax_len = 0;
    ar.ax_size = $clog2(64/8);
    ar.ax_burst = axi_pkg::BURST_INCR;
    driver_compute1_local_data__cpu.send_ar(ar);
    driver_compute1_local_data__cpu.recv_r(rbeat);
    if (rbeat.r_data !== expected || rbeat.r_resp !== axi_pkg::RESP_OKAY ||
        rbeat.r_id !== 1 || rbeat.r_last !== 1)
      $fatal(1, "FAIL compute1_local_data__cpu read addr=%h expected=%h got=%h", addr, expected, rbeat.r_data);
  endtask
  task automatic write_compute0_local_config__cpu(input logic [31:0] addr, input logic [31:0] payload);
    driver_compute0_local_config__cpu_t::ax_beat_t awbeat = new;
    driver_compute0_local_config__cpu_t::w_beat_t wbeat = new;
    driver_compute0_local_config__cpu_t::b_beat_t bbeat;
    awbeat.ax_id = 1;
    awbeat.ax_addr = addr;
    awbeat.ax_len = 0;
    awbeat.ax_size = $clog2(32/8);
    awbeat.ax_burst = axi_pkg::BURST_INCR;
    wbeat.w_data = payload;
    wbeat.w_strb = '1;
    wbeat.w_last = 1;
    driver_compute0_local_config__cpu.send_aw(awbeat);
    driver_compute0_local_config__cpu.send_w(wbeat);
    driver_compute0_local_config__cpu.recv_b(bbeat);
    if (bbeat.b_resp !== axi_pkg::RESP_OKAY || bbeat.b_id !== 1)
      $fatal(1, "FAIL compute0_local_config__cpu write addr=%h B id=%h resp=%h", addr, bbeat.b_id, bbeat.b_resp);
  endtask
  task automatic read_compute0_local_config__cpu(input logic [31:0] addr, input logic [31:0] expected);
    driver_compute0_local_config__cpu_t::ax_beat_t ar = new;
    driver_compute0_local_config__cpu_t::r_beat_t rbeat;
    ar.ax_id = 1;
    ar.ax_addr = addr;
    ar.ax_len = 0;
    ar.ax_size = $clog2(32/8);
    ar.ax_burst = axi_pkg::BURST_INCR;
    driver_compute0_local_config__cpu.send_ar(ar);
    driver_compute0_local_config__cpu.recv_r(rbeat);
    if (rbeat.r_data !== expected || rbeat.r_resp !== axi_pkg::RESP_OKAY ||
        rbeat.r_id !== 1 || rbeat.r_last !== 1)
      $fatal(1, "FAIL compute0_local_config__cpu read addr=%h expected=%h got=%h", addr, expected, rbeat.r_data);
  endtask
  initial begin
    driver_compute0_local_data__cpu = new(bus_compute0_local_data__cpu);
    driver_compute0_local_data__cpu.reset_master();
    driver_compute1_local_data__cpu = new(bus_compute1_local_data__cpu);
    driver_compute1_local_data__cpu.reset_master();
    driver_compute0_local_config__cpu = new(bus_compute0_local_config__cpu);
    driver_compute0_local_config__cpu.reset_master();
    wait(rst_n); repeat(3) @(posedge clk);
    write_compute0_local_data__cpu('h10000000, 'h1122334455667788);
    read_compute0_local_data__cpu('h10000000, 'h1122334455667788);
    write_compute0_local_data__cpu('h11000000, 'h8877665544332211);
    read_compute0_local_data__cpu('h11000000, 'h8877665544332211);
    write_compute0_local_data__cpu('h100000000, 'h4242424212345678);
    read_compute0_local_data__cpu('h100000000, 'h4242424212345678);
    write_compute0_local_data__cpu('h140000000, 'hfeedfacefacefeed);
    read_compute0_local_data__cpu('h140000000, 'hfeedfacefacefeed);
    write_compute1_local_data__cpu('h10000008, 'h9876543210abcdef);
    read_compute1_local_data__cpu('h10000008, 'h9876543210abcdef);
    write_compute0_local_config__cpu('h40000000, 'h10203040);
    read_compute0_local_config__cpu('h40000000, 'h10203040);
    write_compute0_local_config__cpu('h40010000, 'h22334455);
    read_compute0_local_config__cpu('h40010000, 'h22334455);
    write_compute0_local_config__cpu('h40030000, 'haabbccdd);
    read_compute0_local_config__cpu('h40030000, 'haabbccdd);
    repeat(8) @(posedge clk);
    $display("PASS: SuperNoC real FlooNoC read/write paths: 8 networks instantiated");
    $finish;
  end
endmodule
