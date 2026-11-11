`timescale 1ns/1ps
module tb_bar0_noc_translate;
  logic request_valid_i=0, bar0_committed_i=0,bar_mem_ready_i=0;
  logic [31:0] pci_address_i=0,host_bar0_bus_base_i=32'h80001000;
  logic [31:0] bar0_aperture_i=32'h1000,bar0_local_target_i=32'h12000000;
  wire request_in_window_o,blocked_o;
  wire [31:0] noc_address_o;
  pcie_bar0_noc_translate dut (.*);
  task automatic check(input logic accepted,input logic [31:0] target);
    #1;
    if (request_in_window_o !== accepted ||
        noc_address_o !== target ||
        blocked_o !== (request_valid_i && !accepted))
      $fatal(1,"PCI address=%h got accepted=%b target=%h blocked=%b expected=%b/%h",
             pci_address_i,request_in_window_o,noc_address_o,blocked_o,
             accepted,target);
  endtask
  initial begin
    request_valid_i=1;pci_address_i=32'h80001020;
    check(0,0);
    bar0_committed_i=1;
    check(0,0);
    bar_mem_ready_i=1;
    check(1,32'h12000020);
    pci_address_i=32'h80001fff;
    check(1,32'h12000fff);
    pci_address_i=32'h80002000;
    check(0,0);
    pci_address_i=32'h80000fff;
    check(0,0);
    request_valid_i=0;
    check(0,0);
    request_valid_i=1;
    bar0_aperture_i=32'h00100000;
    host_bar0_bus_base_i=32'hc0000000;
    pci_address_i=32'hc00fffe0;
    check(1,32'h120fffe0);
    bar_mem_ready_i=0;
    check(0,0);
    $display("PASS: BAR0 bus/local-NoC offset mapping, boundaries and readiness gating");
    $finish;
  end
endmodule
