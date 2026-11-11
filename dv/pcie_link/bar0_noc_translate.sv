// PCIe BAR0 address-window translation seam into the selected SoC Data NoC.
// NO AXI acceptance, completion or memory-model behavior is synthesized here.
// This is solely a validated combinational address/authorization contract.
`timescale 1ns/1ps
module pcie_bar0_noc_translate (
  input  logic        request_valid_i,
  input  logic [31:0] pci_address_i,
  input  logic [31:0] host_bar0_bus_base_i,
  input  logic [31:0] bar0_aperture_i,
  input  logic [31:0] bar0_local_target_i,
  input  logic        bar0_committed_i,
  input  logic        bar_mem_ready_i,
  output logic        request_in_window_o,
  output logic [31:0] noc_address_o,
  output logic        blocked_o
);
  logic [32:0] range_end;
  logic [32:0] translation;
  logic size_valid;
  always_comb begin
    range_end = {1'b0,host_bar0_bus_base_i} + {1'b0,bar0_aperture_i};
    translation = {1'b0,bar0_local_target_i} +
                  ({1'b0,pci_address_i} - {1'b0,host_bar0_bus_base_i});
    size_valid = bar0_aperture_i >= 32'h1000 &&
                 (bar0_aperture_i & (bar0_aperture_i - 32'd1)) == 0;
    request_in_window_o = request_valid_i && bar0_committed_i &&
        bar_mem_ready_i && size_valid &&
        ({1'b0,pci_address_i} >= {1'b0,host_bar0_bus_base_i}) &&
        ({1'b0,pci_address_i} < range_end) &&
        (translation[32] == 1'b0);
    noc_address_o = request_in_window_o ? translation[31:0] : 32'd0;
    // A blocked request is NOT an AXI beat or a PCIe completion.
    blocked_o = request_valid_i && !request_in_window_o;
  end
endmodule
