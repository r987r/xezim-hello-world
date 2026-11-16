`timescale 1ns/1ps
// Digital Gen1 x1 PIPE DATA/K wiring ONLY. No LTSSM, receiver detect,
// PHY status or clock-domain crossing is synthesized in this adapter.
// Both providers must use the same PIPE parallel clock (62.5 MHz for 32-bit
// Gen1). Replace the provider without editing the verification action runtime.
module pcie_pipe_x1_adapter (
  input  logic        reset_n,
  input  logic [31:0] ep_txdata,
  input  logic [ 3:0] ep_txdatak,
  input  logic        ep_txdata_valid,
  input  logic        ep_txelecidle,
  output logic [31:0] ep_rxdata,
  output logic [ 3:0] ep_rxdatak,
  output logic        ep_rxdata_valid,
  output logic        ep_rxelecidle,
  input  logic [31:0] host_txdata,
  input  logic [ 3:0] host_txdatak,
  input  logic        host_txelecidle,
  input  logic        host_sample_valid,
  output logic [31:0] host_rxdata,
  output logic [ 3:0] host_rxdatak,
  output logic        host_rxelecidle
);
  // PIPE data-valid is distinct from transmitter electrical idle.
  // Electrical idle is not a training shortcut. Real PHY-status response,
  // Detect/receiver presence and LTSSM state come from separate providers.
  assign ep_rxdata       = host_txdata;
  assign ep_rxdatak      = host_txdatak;
  assign ep_rxelecidle   = ~reset_n | host_txelecidle;
  assign ep_rxdata_valid = reset_n & host_sample_valid & ~host_txelecidle;
  assign host_rxdata     = ep_txdata;
  assign host_rxdatak    = ep_txdatak;
  assign host_rxelecidle = ~reset_n | ep_txelecidle;
endmodule
