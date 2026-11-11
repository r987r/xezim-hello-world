`timescale 1ns/1ps
module tb_pcie_pipe_x1_adapter;
  logic reset_n, ep_txdata_valid, ep_txelecidle, host_txelecidle;
  logic host_sample_valid;
  logic [31:0] ep_txdata, host_txdata;
  logic [3:0] ep_txdatak, host_txdatak;
  wire [31:0] ep_rxdata, host_rxdata;
  wire [3:0] ep_rxdatak, host_rxdatak;
  wire ep_rxdata_valid, ep_rxelecidle, host_rxelecidle;

  pcie_pipe_x1_adapter dut (.*);

  initial begin
    reset_n = 0; ep_txdata_valid = 1; ep_txelecidle = 0;
    host_txelecidle = 0; host_sample_valid = 1;
    ep_txdata = 32'h11223344; ep_txdatak = 4'b0101;
    host_txdata = 32'ha5c3e719; host_txdatak = 4'b1010;
    #1;
    if (ep_rxdata_valid !== 1'b0 || host_rxelecidle !== 1'b1)
      $fatal(1, "reset must suppress link traffic");
    reset_n = 1;
    #1;
    if (ep_rxdata !== host_txdata || ep_rxdatak !== host_txdatak ||
        host_rxdata !== ep_txdata || host_rxdatak !== ep_txdatak ||
        ep_rxdata_valid !== 1'b1 || ep_rxelecidle !== 1'b0 ||
        host_rxelecidle !== 1'b0)
      $fatal(1, "x1 32-bit PIPE data/K mapping failed");
    host_txelecidle = 1;
    #1;
    if (ep_rxdata_valid !== 0 || ep_rxelecidle !== 1)
      $fatal(1, "host electrical idle not honored");
    host_txelecidle = 0; host_sample_valid = 0;
    #1;
    if (ep_rxdata_valid !== 0) $fatal(1, "unqualified host sample accepted");
    host_sample_valid = 1; ep_txdata_valid = 0;
    #1;
    if (host_rxelecidle !== 1) $fatal(1, "endpoint TX invalid not idle");
    $display("PASS: Gen1 x1 32-bit/K physical data-boundary directions and idle gating");
    $finish;
  end
endmodule
