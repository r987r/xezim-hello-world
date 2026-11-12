`timescale 1ns/1ps
// Thin DV fixture. The same upstream iDMA RTL is instantiated by the
// configuration-derived full-chip assembly; never duplicate the engine.
module dma_tb (

  input logic clk_i, rst_ni,
  input logic [63:0] apb_addr_i, apb_data_i,
  input logic apb_write_i, apb_select_i, apb_enable_i,
  output logic apb_ready_o,
  output logic [63:0] apb_rdata_o,
  output logic apb_error_o, irq_o,
  output logic [3:0] dma_awid,
  output logic [63:0] dma_awaddr,
  output logic [7:0] dma_awlen,
  output logic [2:0] dma_awsize,
  output logic [1:0] dma_awburst,
  output logic dma_awlock,
  output logic [3:0] dma_awcache,
  output logic [2:0] dma_awprot,
  output logic [3:0] dma_awqos,
  output logic [3:0] dma_awregion,
  output logic dma_awvalid,
  input logic dma_awready,
  output logic [63:0] dma_wdata,
  output logic [7:0] dma_wstrb,
  output logic dma_wlast,
  output logic dma_wvalid,
  input logic dma_wready,
  input logic [3:0] dma_bid,
  input logic [1:0] dma_bresp,
  input logic dma_bvalid,
  output logic dma_bready,
  output logic [3:0] dma_arid,
  output logic [63:0] dma_araddr,
  output logic [7:0] dma_arlen,
  output logic [2:0] dma_arsize,
  output logic [1:0] dma_arburst,
  output logic dma_arlock,
  output logic [3:0] dma_arcache,
  output logic [2:0] dma_arprot,
  output logic [3:0] dma_arqos,
  output logic [3:0] dma_arregion,
  output logic dma_arvalid,
  input logic dma_arready,
  input logic [3:0] dma_rid,
  input logic [63:0] dma_rdata,
  input logic [1:0] dma_rresp,
  input logic dma_rlast,
  input logic dma_rvalid,
  output logic dma_rready

);
  soc_idma_engine u_dma (.*);
endmodule
