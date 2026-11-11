`timescale 1ns/1ps
module tb_pcie_bar0_host_cfg;
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  logic device_bar_committed_i=0;
  logic [31:0] device_bar_aperture_i=0;
  logic awvalid_i=0, awready_i=1, wvalid_i=0,wready_i=1;
  logic [8:0] awaddr_i=0, araddr_i=0;
  logic [31:0] wdata_i=0,rdata_from_rdl_i=32'habcd0000;
  logic [3:0] wstrb_i=4'hf;
  logic arvalid_i=0,arready_i=1;
  wire [31:0] rdata_to_host_o,host_bar0_bus_base_o;
  wire host_memory_enable_o,bar0_probe_o,cfg_violation_o;
  pcie_bar0_host_cfg dut (.*);
  task automatic reset_dut;
    @(negedge clk_i);rst_ni=0;
    awvalid_i=0;wvalid_i=0;arvalid_i=0;
    repeat(3) @(negedge clk_i);
    rst_ni=1;
    @(negedge clk_i);
  endtask
  task automatic aw(input logic [8:0] addr);
    @(negedge clk_i);awaddr_i=addr;awvalid_i=1;
    @(negedge clk_i);awvalid_i=0;
  endtask
  task automatic wd(input logic [31:0] value);
    @(negedge clk_i);wdata_i=value;wvalid_i=1;
    @(negedge clk_i);wvalid_i=0;
  endtask
  task automatic wr(input logic [8:0] addr,input logic [31:0] data);
    aw(addr);
    wd(data); // Intentionally asynchronous AXI-Lite address/data channels
    repeat(2) @(negedge clk_i);
  endtask
  task automatic rd(input logic [8:0] addr,input logic [31:0] expected);
    @(negedge clk_i);araddr_i=addr;arvalid_i=1;
    @(negedge clk_i);arvalid_i=0;
    #1;
    if(rdata_to_host_o !== expected)
      $fatal(1,"config read @%h got=%h expected=%h",addr,rdata_to_host_o,expected);
  endtask
  initial begin
    reset_dut();
    // A device cannot advertise a bus BAR before local pre-link commit.
    wr(9'h010,32'hffff_ffff);
    if(!cfg_violation_o || host_bar0_bus_base_o != 0)
      $fatal(1,"uncommitted BAR accepted host write");
    reset_dut();
    device_bar_aperture_i=32'h0000_1000;
    device_bar_committed_i=1;
    wr(9'h010,32'hffff_ffff);
    if(!bar0_probe_o) $fatal(1,"host BAR sizing probe not detected");
    rd(9'h010,32'hffff_f000);
    if(host_bar0_bus_base_o!=0) $fatal(1,"probe incorrectly assigned bus address");
    wr(9'h010,32'h8000_1234);
    if(bar0_probe_o || host_bar0_bus_base_o!=32'h8000_1000)
      $fatal(1,"BAR0 bus assignment/alignment incorrect");
    rd(9'h010,32'h8000_1000);
    rd(9'h008,32'habcd0000);
    wr(9'h004,32'h0000_0002);
    if(!host_memory_enable_o) $fatal(1,"MSE not captured from host");
    rd(9'h004,32'habcd0002);
    wr(9'h010,32'h9000_0000);
    if(!cfg_violation_o || host_bar0_bus_base_o!=32'h8000_1000)
      $fatal(1,"host changed BAR while MSE enabled");
    reset_dut();
    device_bar_aperture_i=32'h0010_0000;
    device_bar_committed_i=1;
    wr(9'h010,32'hffff_ffff);
    rd(9'h010,32'hfff0_0000);
    wr(9'h010,32'hc001_0000);
    rd(9'h010,32'hc000_0000);
    $display("PASS: real AXI-Lite host BAR0 size probe, address assignment, MSE, write ordering and safety");
    $finish;
  end
endmodule
