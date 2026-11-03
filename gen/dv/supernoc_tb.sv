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
  assign compute0_local_config__cpu_req = '0;
  assign compute0_local_data__cpu_req = '0;
  assign compute0_local_data__dma_req = '0;
  assign compute1_local_config__cpu_req = '0;
  assign compute1_local_data__cpu_req = '0;
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
  // Only structural connectivity established. Traffic will be
  // enabled by upstream PULP AXI agents in this SAME TB.
endmodule
