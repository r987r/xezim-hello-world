// Reusable pinned PULP iDMA RTL engine (64-bit APB command, 64-bit AXI4).
// Upstream RTL owns descriptor fetching, read/write backend, AXI mux.
// All connections to the generated SoC originate in full_chip_gen.py.
// This module is reused verbatim by isolated DV and the full chip.
`include "apb/typedef.svh"
`include "axi/typedef.svh"
`include "idma/typedef.svh"
module soc_idma_engine #(
  parameter int unsigned NumAxInFlight = 4,
  parameter int unsigned BufferDepth = 3,
  parameter int unsigned DescriptorPrefetch = 4
) (
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
  typedef logic [63:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [2:0] id3_t;
  typedef logic [3:0] id4_t;
  typedef logic [0:0] user_t;
  typedef logic [31:0] len_t;
  `APB_TYPEDEF_ALL(apb, addr_t, data_t, strb_t)
  `AXI_TYPEDEF_ALL(axi3, addr_t, id3_t, data_t, strb_t, user_t)
  `AXI_TYPEDEF_ALL(axi4, addr_t, id4_t, data_t, strb_t, user_t)
  `IDMA_TYPEDEF_FULL_REQ_T(idma_req_t, id3_t, addr_t, len_t)
  `IDMA_TYPEDEF_FULL_RSP_T(idma_rsp_t, addr_t)

  typedef struct packed { axi3_ar_chan_t ar_chan; } axi_read_meta_channel_t;
  typedef struct packed { axi_read_meta_channel_t axi; } read_meta_channel_t;
  typedef struct packed { axi3_aw_chan_t aw_chan; } axi_write_meta_channel_t;
  typedef struct packed { axi_write_meta_channel_t axi; } write_meta_channel_t;

  // Standalone RTL retains upstream 4/3/4; full-chip opts in to safe limits.
  initial begin
    // Upstream idma_backend_rw_axi uses this value as the
    // cc_stream_fifo_optimal_wrap depth and rejects depth one in RTL.
    if (NumAxInFlight < 2 || BufferDepth == 0 || DescriptorPrefetch > 16)
      $fatal(1, "Invalid iDMA concurrency parameters");
  end
  axi3_req_t descriptor_req, read_req, write_req, backend_req;
  axi3_resp_t descriptor_rsp, read_rsp, write_rsp, backend_rsp;
  axi4_req_t dma_req;
  axi4_resp_t dma_rsp;
  apb_req_t apb_req;
  apb_resp_t apb_rsp;
  idma_req_t transfer_req;
  idma_rsp_t transfer_rsp;
  idma_pkg::idma_busy_t backend_busy;
  logic transfer_valid, transfer_ready, completion_valid, completion_ready;

  // 64-bit APB submission interface of upstream idma_desc64.
  assign apb_req.paddr   = apb_addr_i;
  assign apb_req.pprot   = '0;
  assign apb_req.psel    = apb_select_i;
  assign apb_req.penable = apb_enable_i;
  assign apb_req.pwrite  = apb_write_i;
  assign apb_req.pwdata  = apb_data_i;
  assign apb_req.pstrb   = '1;
  assign apb_ready_o     = apb_rsp.pready;
  assign apb_rdata_o     = apb_rsp.prdata;
  assign apb_error_o     = apb_rsp.pslverr;

  idma_desc64_top #(
    .AddrWidth(64), .DataWidth(64), .AxiIdWidth(3),
    .idma_req_t(idma_req_t), .idma_rsp_t(idma_rsp_t),
    .axi_req_t(axi3_req_t), .axi_rsp_t(axi3_resp_t),
    .axi_ar_chan_t(axi3_ar_chan_t), .axi_r_chan_t(axi3_r_chan_t),
    .apb_req_t(apb_req_t), .apb_rsp_t(apb_resp_t),
    .InputFifoDepth(8), .PendingFifoDepth(8),
    .BackendDepth(NumAxInFlight + BufferDepth), .NSpeculation(DescriptorPrefetch)
  ) u_frontend (
    .clk_i, .rst_ni,
    .master_req_o(descriptor_req), .master_rsp_i(descriptor_rsp),
    .axi_ar_id_i(3'd7), .axi_aw_id_i(3'd7),
    .slave_req_i(apb_req), .slave_rsp_o(apb_rsp),
    .idma_req_o(transfer_req), .idma_req_valid_o(transfer_valid),
    .idma_req_ready_i(transfer_ready),
    .idma_rsp_i(transfer_rsp), .idma_rsp_valid_i(completion_valid),
    .idma_rsp_ready_o(completion_ready),
    .idma_busy_i(|backend_busy), .irq_o
  );

  idma_backend_rw_axi #(
    .DataWidth(64), .AddrWidth(64), .AxiIdWidth(3),
    .UserWidth(1), .TFLenWidth(32),
    .BufferDepth(BufferDepth), .NumAxInFlight(NumAxInFlight),
    .RAWCouplingAvail(1'b1), .HardwareLegalizer(1'b1),
    .RejectZeroTransfers(1'b1),
    .ErrorCap(idma_pkg::NO_ERROR_HANDLING),
    .idma_req_t(idma_req_t), .idma_rsp_t(idma_rsp_t),
    .idma_eh_req_t(idma_pkg::idma_eh_req_t),
    .idma_busy_t(idma_pkg::idma_busy_t),
    .axi_req_t(axi3_req_t), .axi_rsp_t(axi3_resp_t),
    .read_meta_channel_t(read_meta_channel_t),
    .write_meta_channel_t(write_meta_channel_t)
  ) u_backend (
    .clk_i, .rst_ni,
    .idma_req_i(transfer_req), .req_valid_i(transfer_valid),
    .req_ready_o(transfer_ready),
    .idma_rsp_o(transfer_rsp), .rsp_valid_o(completion_valid),
    .rsp_ready_i(completion_ready),
    .idma_eh_req_i('0), .eh_req_valid_i(1'b1), .eh_req_ready_o(),
    .axi_read_req_o(read_req), .axi_read_rsp_i(read_rsp),
    .axi_write_req_o(write_req), .axi_write_rsp_i(write_rsp),
    .busy_o(backend_busy)
  );

  // Reuse upstream PULP read/write join and ID-preserving arbitration.
  axi_rw_join #(
    .axi_req_t(axi3_req_t), .axi_resp_t(axi3_resp_t)
  ) u_join (
    .clk_i, .rst_ni,
    .slv_read_req_i(read_req), .slv_read_resp_o(read_rsp),
    .slv_write_req_i(write_req), .slv_write_resp_o(write_rsp),
    .mst_req_o(backend_req), .mst_resp_i(backend_rsp)
  );
  axi_mux #(
    .SlvAxiIDWidth(3),
    .slv_aw_chan_t(axi3_aw_chan_t), .mst_aw_chan_t(axi4_aw_chan_t),
    .w_chan_t(axi3_w_chan_t),
    .slv_b_chan_t(axi3_b_chan_t), .mst_b_chan_t(axi4_b_chan_t),
    .slv_ar_chan_t(axi3_ar_chan_t), .mst_ar_chan_t(axi4_ar_chan_t),
    .slv_r_chan_t(axi3_r_chan_t), .mst_r_chan_t(axi4_r_chan_t),
    .slv_req_t(axi3_req_t), .slv_resp_t(axi3_resp_t),
    .mst_req_t(axi4_req_t), .mst_resp_t(axi4_resp_t),
    .NoSlvPorts(2), .MaxWTrans(NumAxInFlight)
  ) u_mux (
    .clk_i, .rst_ni,
    .slv_reqs_i({backend_req, descriptor_req}),
    .slv_resps_o({backend_rsp, descriptor_rsp}),
    .mst_req_o(dma_req), .mst_resp_i(dma_rsp)
  );

  assign dma_awid = dma_req.aw.id;
  assign dma_awaddr = dma_req.aw.addr;
  assign dma_awlen = dma_req.aw.len;
  assign dma_awsize = dma_req.aw.size;
  assign dma_awburst = dma_req.aw.burst;
  assign dma_awlock = dma_req.aw.lock;
  assign dma_awcache = dma_req.aw.cache;
  assign dma_awprot = dma_req.aw.prot;
  assign dma_awqos = dma_req.aw.qos;
  assign dma_awregion = dma_req.aw.region;
  assign dma_awvalid = dma_req.aw_valid;
  assign dma_rsp.aw_ready = dma_awready;
  assign dma_wdata = dma_req.w.data;
  assign dma_wstrb = dma_req.w.strb;
  assign dma_wlast = dma_req.w.last;
  assign dma_wvalid = dma_req.w_valid;
  assign dma_rsp.w_ready = dma_wready;
  assign dma_rsp.b.id = dma_bid;
  assign dma_rsp.b.resp = dma_bresp;
  assign dma_rsp.b_valid = dma_bvalid;
  assign dma_bready = dma_req.b_ready;
  assign dma_arid = dma_req.ar.id;
  assign dma_araddr = dma_req.ar.addr;
  assign dma_arlen = dma_req.ar.len;
  assign dma_arsize = dma_req.ar.size;
  assign dma_arburst = dma_req.ar.burst;
  assign dma_arlock = dma_req.ar.lock;
  assign dma_arcache = dma_req.ar.cache;
  assign dma_arprot = dma_req.ar.prot;
  assign dma_arqos = dma_req.ar.qos;
  assign dma_arregion = dma_req.ar.region;
  assign dma_arvalid = dma_req.ar_valid;
  assign dma_rsp.ar_ready = dma_arready;
  assign dma_rsp.r.id = dma_rid;
  assign dma_rsp.r.data = dma_rdata;
  assign dma_rsp.r.resp = dma_rresp;
  assign dma_rsp.r.last = dma_rlast;
  assign dma_rsp.r_valid = dma_rvalid;
  assign dma_rready = dma_req.r_ready;
  // No AXI USER sideband is used at this 64-bit fabric endpoint.
  assign dma_rsp.b.user = '0;
  assign dma_rsp.r.user = '0;
  initial begin
    if ($bits(dma_req.aw.id) != 4 || $bits(descriptor_req.ar.id) != 3)
      $fatal(1, "DMA mux AXI ID-width mismatch");
  end
endmodule
