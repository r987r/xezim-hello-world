// Complete-span BAR authorization; no synthetic AXI or PCIe completions.
`timescale 1ns/1ps
module tb_bar0_noc_translate;
  logic request_valid_i=0, bar0_committed_i=0, bar_mem_ready_i=0;
  logic [31:0] pci_address_i=0, request_bytes_i=32'd4;
  logic [31:0] host_bar0_bus_base_i=32'h80001000;
  logic [31:0] bar0_aperture_i=32'h00001000;
  logic [31:0] bar0_local_target_i=32'h12000000;
  wire request_in_window_o, blocked_o;
  wire [31:0] noc_address_o;
  pcie_bar0_noc_translate dut (.*);
  integer checks=0;
  task automatic check(input logic accepted,input logic [31:0] target);
    #1;
    checks=checks+1;
    if (request_in_window_o !== accepted ||
        noc_address_o !== target ||
        blocked_o !== (request_valid_i && !accepted))
      $fatal(1,"PCI addr=%h bytes=%h BAR=%h/%h local=%h got %b/%h blocked=%b expected=%b/%h",
             pci_address_i,request_bytes_i,host_bar0_bus_base_i,
             bar0_aperture_i,bar0_local_target_i,
             request_in_window_o,noc_address_o,blocked_o,accepted,target);
  endtask
  initial begin
    request_valid_i=1; pci_address_i=32'h80001020;
    check(0,0); // before commit
    bar0_committed_i=1;
    check(0,0); // before link/NoC/host-MSE readiness
    bar_mem_ready_i=1;
    check(1,32'h12000020);
    pci_address_i=32'h80001ffc;
    check(1,32'h12000ffc); // exact end of BAR
    request_bytes_i=32'd5;
    check(0,0); // start is in BAR, last byte is not
    request_bytes_i=32'd1;
    pci_address_i=32'h80001fff;
    check(1,32'h12000fff);
    request_bytes_i=32'd2;
    check(0,0); // last-byte cross-window
    request_bytes_i=32'd4;
    pci_address_i=32'h80002000;
    check(0,0); // start outside
    pci_address_i=32'h80000fff;
    check(0,0); // before BAR
    pci_address_i=32'h80001000;
    request_bytes_i=0;
    check(0,0); // zero-length
    request_bytes_i=32'h00001000;
    check(1,32'h12000000); // whole window
    request_bytes_i=32'h00001001;
    check(0,0); // larger than BAR
    request_valid_i=0;
    request_bytes_i=32'd4;
    check(0,0);
    request_valid_i=1;

    // Reprogram different legal aperture: check alignment and full span.
    bar0_aperture_i=32'h00100000;
    host_bar0_bus_base_i=32'hc0000000;
    pci_address_i=32'hc00fffe0;
    request_bytes_i=32'd32;
    check(1,32'h120fffe0);
    request_bytes_i=32'd33;
    check(0,0); // straddles aperture
    request_bytes_i=32'd32;
    bar_mem_ready_i=0;
    check(0,0);
    bar_mem_ready_i=1;
    host_bar0_bus_base_i=32'hc0001000;
    check(0,0); // host-assigned BAR must align to aperture
    host_bar0_bus_base_i=32'hc0000000;
    bar0_local_target_i=32'h12001000;
    check(0,0); // local target must also align
    bar0_local_target_i=32'h12000000;

    // Distinguish last byte of 32-bit address space from wrapped traffic.
    bar0_aperture_i=32'h00001000;
    host_bar0_bus_base_i=32'hfffff000;
    bar0_local_target_i=32'hfffff000;
    pci_address_i=32'hfffffffc;
    request_bytes_i=32'd4;
    check(1,32'hfffffffc); // end exclusive = 2^32 is legal
    request_bytes_i=32'd5;
    check(0,0); // crossing 32-bit limit rejected
    host_bar0_bus_base_i=32'hfffff800;
    pci_address_i=32'hfffff800;
    request_bytes_i=32'd4;
    check(0,0); // BAR alignment + potential address overflow
    host_bar0_bus_base_i=32'hfffff000;
    bar0_local_target_i=32'hfffff800;
    check(0,0); // local alignment + potential overflow
    bar0_local_target_i=32'hfffff000;

    bar0_aperture_i=32'h00001800;
    check(0,0); // non power-of-two
    bar0_aperture_i=32'h00000800;
    check(0,0); // smaller than 4 KiB
    bar0_aperture_i=32'h00200000;
    check(0,0); // larger than device SRAM window
    $display("PASS: BAR0 bus/local-NoC complete-span mapping, %0d directed boundary/readiness checks",checks);
    $finish;
  end
endmodule
