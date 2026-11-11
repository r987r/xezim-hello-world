`timescale 1ns/1ps
module tb_endpoint_prelink_ctrl;
  logic clk_i=0, rst_ni=0, cfg_wr_i=0;
  logic [3:0] cfg_addr_i=0,cfg_wstrb_i=4'hf;
  logic [31:0] cfg_wdata_i=0;
  wire [31:0] cfg_rdata_o,bar0_aperture_o,bar0_local_target_o,bar0_size_mask_o;
  wire cfg_error_o,bar_config_committed_o,ltssm_enable_o,bar_mem_ready_o;
  logic phy_ready_i=0,noc_ready_i=0,link_up_i=0,host_mem_enable_i=0;
  always #5 clk_i=~clk_i;
  pcie_endpoint_prelink_ctrl dut (.*);
  task automatic write_reg(input logic [3:0] addr,input logic [31:0] data);
    @(negedge clk_i);
    cfg_addr_i=addr; cfg_wdata_i=data; cfg_wr_i=1;
    @(negedge clk_i);
    cfg_wr_i=0;
  endtask
  task automatic reset_dut;
    @(negedge clk_i);
    rst_ni=0;cfg_wr_i=0;phy_ready_i=0;noc_ready_i=0;
    link_up_i=0;host_mem_enable_i=0;
    repeat(2) @(negedge clk_i);
    rst_ni=1;
    @(negedge clk_i);
  endtask
  initial begin
    reset_dut();
    phy_ready_i=1; link_up_i=1; noc_ready_i=1; host_mem_enable_i=1;
    #1;
    if(ltssm_enable_o || bar_mem_ready_o) $fatal(1,"link enabled without BAR");
    write_reg(4'h8,32'h2);
    if(!cfg_error_o || ltssm_enable_o) $fatal(1,"start without commit accepted");
    reset_dut();
    write_reg(4'h0,32'h00001000);
    write_reg(4'h4,32'h12000000);
    write_reg(4'h8,32'h1);
    if(!bar_config_committed_o || bar0_size_mask_o!=32'hfffff000)
      $fatal(1,"valid 4KiB BAR mask/commit failure");
    write_reg(4'h0,32'h2000);
    if(!cfg_error_o || bar0_aperture_o!=32'h1000)
      $fatal(1,"post-commit mutation accepted");
    write_reg(4'h8,32'h2);
    if(ltssm_enable_o) $fatal(1,"LTSSM before PHY ready");
    phy_ready_i=1;
    #1;
    if(!ltssm_enable_o || bar_mem_ready_o)
      $fatal(1,"LTSSM gate requires PHY but BAR memory must wait for other conditions");
    link_up_i=1;
    #1;
    if(bar_mem_ready_o) $fatal(1,"BAR memory before NoC ready");
    noc_ready_i=1;
    #1;
    if(bar_mem_ready_o) $fatal(1,"BAR memory before host memory enable");
    host_mem_enable_i=1;
    #1;
    if(!bar_mem_ready_o) $fatal(1,"BAR access not ready after all gates");
    link_up_i=0;
    #1;
    if(bar_mem_ready_o) $fatal(1,"link down failed to revoke BAR memory");
    reset_dut();
    write_reg(4'h0,32'h3000);
    write_reg(4'h4,32'h12000000);
    write_reg(4'h8,32'h1);
    if(bar_config_committed_o || !cfg_error_o)
      $fatal(1,"non-power-of-two aperture accepted");
    reset_dut();
    write_reg(4'h0,32'h2000);
    write_reg(4'h4,32'h12001000);
    write_reg(4'h8,32'h1);
    if(bar_config_committed_o || !cfg_error_o)
      $fatal(1,"misaligned target accepted");
    reset_dut();
    write_reg(4'h0,32'h100000);
    write_reg(4'h4,32'h12000000);
    write_reg(4'h8,32'h1);
    if(!bar_config_committed_o || bar0_size_mask_o!=32'hfff00000)
      $fatal(1,"valid 1MiB BAR rejected");
    $display("PASS: device BAR size/target configured before LTSSM; freeze, size, NoC and link gates verified");
    $finish;
  end
endmodule
