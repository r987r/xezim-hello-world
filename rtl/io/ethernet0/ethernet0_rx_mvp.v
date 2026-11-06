// Minimal Ethernet0 RX RTL slice: *real* GMII FCS/CDC -> complete-frame
// header metadata -> one descriptor ring -> AXI packet DMA -> B-gated
// 32-byte queue completion. TX is intentionally not implemented here.
// Three upstream AXI initiators are exposed separately; the full-chip
// integrator MUST connect them via the pinned AXI mux and generated Data NoC.
// Do not call this one-target structural slice the full Ethernet0 subsystem.
`timescale 1ns/1ps
`default_nettype none
module ethernet0_rx_mvp #(
    parameter [63:0] RING_BASE=64'h100,
    parameter [63:0] RING_BYTES=64'h1000,
    parameter [63:0] BUFFER_BASE=64'h2000,
    parameter [63:0] BUFFER_BYTES=64'h8000,
    parameter [63:0] ALT_BUFFER_BASE=0,
    parameter [63:0] ALT_BUFFER_BYTES=0,
    parameter [63:0] CQ_REGION_BASE=64'h500,
    parameter [63:0] CQ_REGION_BYTES=64'h200,
    parameter integer AXI_ID_WIDTH=4,
    parameter integer TX_ENABLE=0
)(
    input wire logic_clk, logic_rst,
    input wire gmii_rx_clk, gmii_rx_rst, gmii_tx_clk, gmii_tx_rst,
    input wire [7:0] gmii_rxd,
    input wire gmii_rx_dv, gmii_rx_er,
    input wire [63:0] tx_axis_tdata,
    input wire [7:0] tx_axis_tkeep,
    input wire tx_axis_tvalid,
    output wire tx_axis_tready,
    input wire tx_axis_tlast,tx_axis_tuser,
    output wire [7:0] gmii_txd,
    output wire gmii_tx_en,gmii_tx_er,tx_error_underflow,
    output wire tx_desc_valid_o,
    input wire tx_desc_ready_i,tx_cpl_written_i,
    output wire [63:0] tx_desc_addr_o,tx_cq_slot_addr_o,
    input wire cfg_valid, cfg_write,
    input wire [7:0] cfg_addr,
    input wire [31:0] cfg_wdata,
    input wire [3:0] cfg_wstrb,
    output wire cfg_ready,
    output wire [31:0] cfg_rdata,
    output wire cfg_error,
    output wire irq_o,
    output wire frame_drop_o, cq_failed_o,
    output wire rx_error_bad_fcs_o,
    output wire [AXI_ID_WIDTH-1:0] rd_arid,
    output wire [63:0] rd_araddr,
    output wire [7:0] rd_arlen,
    output wire [2:0] rd_arsize,
    output wire [1:0] rd_arburst,
    output wire rd_arlock,
    output wire [3:0] rd_arcache,
    output wire [2:0] rd_arprot,
    output wire rd_arvalid,
    input wire rd_arready,
    input wire [AXI_ID_WIDTH-1:0] rd_rid,
    input wire [63:0] rd_rdata,
    input wire [1:0] rd_rresp,
    input wire rd_rlast,
    input wire rd_rvalid,
    output wire rd_rready,
    output wire [AXI_ID_WIDTH-1:0] wr_awid,
    output wire [63:0] wr_awaddr,
    output wire [7:0] wr_awlen,
    output wire [2:0] wr_awsize,
    output wire [1:0] wr_awburst,
    output wire wr_awlock,
    output wire [3:0] wr_awcache,
    output wire [2:0] wr_awprot,
    output wire wr_awvalid,
    input wire wr_awready,
    output wire [63:0] wr_wdata,
    output wire [7:0] wr_wstrb,
    output wire wr_wlast,
    output wire wr_wvalid,
    input wire wr_wready,
    input wire [AXI_ID_WIDTH-1:0] wr_bid,
    input wire [1:0] wr_bresp,
    input wire wr_bvalid,
    output wire wr_bready,
    output wire [AXI_ID_WIDTH-1:0] cq_awid,
    output wire [63:0] cq_awaddr,
    output wire [7:0] cq_awlen,
    output wire [2:0] cq_awsize,
    output wire [1:0] cq_awburst,
    output wire cq_awlock,
    output wire [3:0] cq_awcache,
    output wire [2:0] cq_awprot,
    output wire cq_awvalid,
    input wire cq_awready,
    output wire [63:0] cq_wdata,
    output wire [7:0] cq_wstrb,
    output wire cq_wlast,
    output wire cq_wvalid,
    input wire cq_wready,
    input wire [AXI_ID_WIDTH-1:0] cq_bid,
    input wire [1:0] cq_bresp,
    input wire cq_bvalid,
    output wire cq_bready
);
    wire meta_valid,meta_ready,meta_is_udp;
    wire [15:0] meta_length,meta_ethertype,meta_udp_port;
    wire [63:0] axis_data;
    wire [7:0] axis_keep;
    wire axis_valid,axis_ready,axis_last,axis_user;
    wire frontend_drop,frontend_overflow,rx_bad_frame,rx_fifo_overflow;
    wire rx_fifo_bad,rx_fifo_good;
    wire engine_drop;
    wire [63:0] rx_cq_slot,tx_cq_slot,tx_desc_addr;
    wire tx_desc_valid;
    wire result_valid,result_ok;
    wire [3:0] result_error;
    wire [15:0] result_length;
    wire [31:0] result_cookie;
    wire [7:0] result_policy,result_tag;
    wire cq_done_valid,cq_written;
    wire [3:0] cq_error;
    wire [7:0] cq_tag;

    ethernet0_rx_gmii_stager #(.TX_ENABLE(TX_ENABLE)) u_gmii_stage (
      .logic_clk,.logic_rst,.gmii_rx_clk,.gmii_rx_rst,
      .gmii_tx_clk,.gmii_tx_rst,.gmii_rxd,.gmii_rx_dv,.gmii_rx_er,
      .tx_axis_tdata,.tx_axis_tkeep,.tx_axis_tvalid,
      .tx_axis_tready,.tx_axis_tlast,.tx_axis_tuser,
      .gmii_txd,.gmii_tx_en,.gmii_tx_er,.tx_error_underflow,
      .meta_valid,.meta_ready,.meta_length,.meta_ethertype,
      .meta_is_udp,.meta_udp_dst_port(meta_udp_port),
      .rx_axis_tdata(axis_data),.rx_axis_tkeep(axis_keep),
      .rx_axis_tvalid(axis_valid),.rx_axis_tready(axis_ready),
      .rx_axis_tlast(axis_last),.rx_axis_tuser(axis_user),
      .rx_error_bad_fcs(rx_error_bad_fcs_o),
      .rx_error_bad_frame(rx_bad_frame),
      .rx_fifo_overflow,.rx_fifo_bad_frame(rx_fifo_bad),
      .rx_fifo_good_frame(rx_fifo_good),
      .dropped_frame_pulse(frontend_drop),
      .stage_fifo_overflow(frontend_overflow)
    );

    ethernet_rx_queue_engine #(
      .RING_BASE(RING_BASE),.RING_BYTES(RING_BYTES),
      .BUFFER_BASE(BUFFER_BASE),.BUFFER_BYTES(BUFFER_BYTES),
      .ALT_BUFFER_BASE(ALT_BUFFER_BASE),.ALT_BUFFER_BYTES(ALT_BUFFER_BYTES),
      .AXI_ID_WIDTH(AXI_ID_WIDTH)
    ) u_rx_queue (
      .clk(logic_clk),.rst(logic_rst),
      .cfg_valid,.cfg_write,.cfg_addr,.cfg_wdata,.cfg_wstrb,
      .cfg_ready,.cfg_rdata,.cfg_error,
      .tx_desc_ready_i,.tx_cpl_written_i,
      .tx_desc_valid_o(tx_desc_valid),.tx_desc_addr_o(tx_desc_addr),
      .rx_cq_slot_addr_o(rx_cq_slot),.tx_cq_slot_addr_o(tx_cq_slot),
      .frame_valid(meta_valid),.frame_ready(meta_ready),
      .frame_length(meta_length),.frame_ethertype(meta_ethertype),
      .frame_is_udp(meta_is_udp),.frame_udp_dst_port(meta_udp_port),
      .rx_axis_tdata(axis_data),.rx_axis_tkeep(axis_keep),
      .rx_axis_tvalid(axis_valid),.rx_axis_tready(axis_ready),
      .rx_axis_tlast(axis_last),.rx_axis_tuser(axis_user),
      .write_result_valid(result_valid),.write_result_ok(result_ok),
      .write_result_error(result_error),.write_result_length(result_length),
      .write_result_cookie(result_cookie),.write_result_policy(result_policy),
      .write_result_tag(result_tag),.frame_drop_pulse(engine_drop),
      .cpl_written_i(cq_written),.irq(irq_o),
    .rd_arid(rd_arid),
    .rd_araddr(rd_araddr),
    .rd_arlen(rd_arlen),
    .rd_arsize(rd_arsize),
    .rd_arburst(rd_arburst),
    .rd_arlock(rd_arlock),
    .rd_arcache(rd_arcache),
    .rd_arprot(rd_arprot),
    .rd_arvalid(rd_arvalid),
    .rd_arready(rd_arready),
    .rd_rid(rd_rid),
    .rd_rdata(rd_rdata),
    .rd_rresp(rd_rresp),
    .rd_rlast(rd_rlast),
    .rd_rvalid(rd_rvalid),
    .rd_rready(rd_rready),
    .wr_awid(wr_awid),
    .wr_awaddr(wr_awaddr),
    .wr_awlen(wr_awlen),
    .wr_awsize(wr_awsize),
    .wr_awburst(wr_awburst),
    .wr_awlock(wr_awlock),
    .wr_awcache(wr_awcache),
    .wr_awprot(wr_awprot),
    .wr_awvalid(wr_awvalid),
    .wr_awready(wr_awready),
    .wr_wdata(wr_wdata),
    .wr_wstrb(wr_wstrb),
    .wr_wlast(wr_wlast),
    .wr_wvalid(wr_wvalid),
    .wr_wready(wr_wready),
    .wr_bid(wr_bid),
    .wr_bresp(wr_bresp),
    .wr_bvalid(wr_bvalid),
    .wr_bready(wr_bready)
    );

    ethernet_cq_axi_writer #(
      .REGION_BASE(CQ_REGION_BASE),.REGION_BYTES(CQ_REGION_BYTES),
      .AXI_ID_WIDTH(AXI_ID_WIDTH)
    ) u_rx_cq (
      .clk(logic_clk),.rst(logic_rst),
      .req_valid(result_valid),.req_ready(),
      .req_addr(rx_cq_slot),.req_cookie(result_cookie),
      .req_length({16'd0,result_length}),
      .req_status(result_ok?32'd0:{28'd0,result_error}),
      .req_policy({24'd0,result_policy}),
      .req_queue(32'd0),.req_tag(result_tag),
      .cpl_done_valid(cq_done_valid),.cpl_written(cq_written),
      .cpl_error(cq_error),.cpl_tag(cq_tag),
    .m_axi_awid(cq_awid),
    .m_axi_awaddr(cq_awaddr),
    .m_axi_awlen(cq_awlen),
    .m_axi_awsize(cq_awsize),
    .m_axi_awburst(cq_awburst),
    .m_axi_awlock(cq_awlock),
    .m_axi_awcache(cq_awcache),
    .m_axi_awprot(cq_awprot),
    .m_axi_awvalid(cq_awvalid),
    .m_axi_awready(cq_awready),
    .m_axi_wdata(cq_wdata),
    .m_axi_wstrb(cq_wstrb),
    .m_axi_wlast(cq_wlast),
    .m_axi_wvalid(cq_wvalid),
    .m_axi_wready(cq_wready),
    .m_axi_bid(cq_bid),
    .m_axi_bresp(cq_bresp),
    .m_axi_bvalid(cq_bvalid),
    .m_axi_bready(cq_bready)
    );
    assign cq_failed_o = cq_done_valid && !cq_written;
    assign tx_desc_valid_o = tx_desc_valid;
    assign tx_desc_addr_o = tx_desc_addr;
    assign tx_cq_slot_addr_o = tx_cq_slot;
    assign frame_drop_o = frontend_drop || engine_drop;
    initial begin
      if(RING_BYTES<32 || BUFFER_BYTES<64 || CQ_REGION_BYTES<512 ||
         RING_BASE[4:0] || CQ_REGION_BASE[4:0]) 
        $fatal(1,"invalid Ethernet0 RX MVP memory contract");
    end
endmodule
`default_nettype wire
