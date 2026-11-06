// Focused REAL PeakRDL register RTL, not a behavioral register model.
// AXI-Lite accesses use register-local byte addresses. The full chip's
// existing AXI-to-Lite bridge and Config NoC are separately tested by
// chip-peakrdl-reset against this very same generated module.
module reset_axi_tb (
  input logic clk, rst_n,
  input logic s_axil_awvalid,
  output logic s_axil_awready,
  input logic [11:0] s_axil_awaddr,
  input logic [2:0] s_axil_awprot,
  input logic s_axil_wvalid,
  output logic s_axil_wready,
  input logic [31:0] s_axil_wdata,
  input logic [3:0] s_axil_wstrb,
  input logic s_axil_bready,
  output logic s_axil_bvalid,
  output logic [1:0] s_axil_bresp,
  input logic s_axil_arvalid,
  output logic s_axil_arready,
  input logic [11:0] s_axil_araddr,
  input logic [2:0] s_axil_arprot,
  input logic s_axil_rready,
  output logic s_axil_rvalid,
  output logic [31:0] s_axil_rdata,
  output logic [1:0] s_axil_rresp,
  output logic release_o,
  output logic [31:0] secondary_ack_o
);
  soc_boot_reset_ctrl_regblock_pkg::boot_reset_ctrl__out_t hwif_out;
  soc_boot_reset_ctrl_regblock u_regblock (
    .clk(clk), .rst_n(rst_n),
    .s_axil_awvalid, .s_axil_awready, .s_axil_awaddr, .s_axil_awprot,
    .s_axil_wvalid, .s_axil_wready, .s_axil_wdata, .s_axil_wstrb,
    .s_axil_bready, .s_axil_bvalid, .s_axil_bresp,
    .s_axil_arvalid, .s_axil_arready, .s_axil_araddr, .s_axil_arprot,
    .s_axil_rready, .s_axil_rvalid, .s_axil_rdata, .s_axil_rresp,
    .hwif_out
  );
  assign release_o = hwif_out.cpu_release.secondary_release.value;
  assign secondary_ack_o = hwif_out.secondary_ack[0].ack.value;
endmodule
