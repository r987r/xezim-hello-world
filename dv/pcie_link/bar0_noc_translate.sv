// PCIe BAR0 -> selected SoC Data NoC address/authorization boundary.
// Pure combinational contract: NEVER invent AXI acceptance or PCIe completions.
// A memory transaction MUST fit wholly within the committed host BAR window.
// Size is the full byte span (including disabled byte lanes, if applicable).
`timescale 1ns/1ps
module pcie_bar0_noc_translate (
  input  logic        request_valid_i,
  input  logic [31:0] pci_address_i,
  input  logic [31:0] request_bytes_i,
  input  logic [31:0] host_bar0_bus_base_i,
  input  logic [31:0] bar0_aperture_i,
  input  logic [31:0] bar0_local_target_i,
  input  logic        bar0_committed_i,
  input  logic        bar_mem_ready_i,
  output logic        request_in_window_o,
  output logic [31:0] noc_address_o,
  output logic        blocked_o
);
  logic [33:0] bar_end;
  logic [33:0] pci_end;
  logic [33:0] local_window_end;
  logic [33:0] local_start, local_end;
  logic [33:0] pci_offset;
  logic size_valid, aligned, window_valid;

  always_comb begin
    bar_end = {2'b00, host_bar0_bus_base_i} + {2'b00, bar0_aperture_i};
    pci_end = {2'b00, pci_address_i} + {2'b00, request_bytes_i};
    local_window_end = {2'b00, bar0_local_target_i} + {2'b00, bar0_aperture_i};
    pci_offset = (pci_address_i >= host_bar0_bus_base_i) ?
                 ({2'b00, pci_address_i} - {2'b00, host_bar0_bus_base_i}) : '0;
    local_start = {2'b00, bar0_local_target_i} + pci_offset;
    local_end = local_start + {2'b00, request_bytes_i};
    size_valid = bar0_aperture_i >= 32'h0000_1000 &&
                 bar0_aperture_i <= 32'h0010_0000 &&
                 (bar0_aperture_i & (bar0_aperture_i - 32'd1)) == 0;
    // BAR size alignment is required in BOTH PCIe and SoC address domains.
    aligned = ((host_bar0_bus_base_i & (bar0_aperture_i - 32'd1)) == 0) &&
              ((bar0_local_target_i & (bar0_aperture_i - 32'd1)) == 0);
    window_valid = size_valid && aligned &&
                   bar_end <= 34'h1_0000_0000 &&
                   local_window_end <= 34'h1_0000_0000;
    request_in_window_o = request_valid_i && bar0_committed_i &&
        bar_mem_ready_i && window_valid && request_bytes_i != 0 &&
        request_bytes_i <= bar0_aperture_i &&
        pci_address_i >= host_bar0_bus_base_i &&
        pci_end <= bar_end && local_end <= local_window_end &&
        local_end <= 34'h1_0000_0000;
    noc_address_o = request_in_window_o ? local_start[31:0] : 32'd0;
    // Rejected requests must receive a real error/completion downstream.
    // This module never fabricates an AXI beat or a PCIe completion.
    blocked_o = request_valid_i && !request_in_window_o;
  end
endmodule
