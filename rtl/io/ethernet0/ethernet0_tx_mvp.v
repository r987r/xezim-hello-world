// One TX queue: memory-resident 32-byte descriptor -> pinned AXI read DMA ->
// frame-complete TX AXIS -> actual GMII wire-end acknowledgment ->
// real B-gated 32-byte completion. Never complete at FIFO ingress alone.
// Pinned AXI DMA RTL performs all memory traffic; no private host model.
//
// Integration contract: the RX queue controller issues tx_desc_valid/address;
// the controller only increments TX CQ producer on tx_cpl_written, after
// real GMII packet termination and CQ AXI B. This module exports separate
// read/write AXI masters for the upstream arbitration/NoC integration.
// Descriptor word layout matches RX (length is word1[31:0], cookie high 32).
`timescale 1ns/1ps
`default_nettype none
module ethernet0_tx_mvp #(
    parameter [63:0] RING_BASE=64'h600,
    parameter [63:0] RING_BYTES=64'h200,
    parameter [63:0] BUFFER_BASE=64'h2000,
    parameter [63:0] BUFFER_BYTES=64'h8000,
    parameter [63:0] ALT_BUFFER_BASE=0,
    parameter [63:0] ALT_BUFFER_BYTES=0,
    parameter [63:0] CQ_REGION_BASE=64'h700,
    parameter [63:0] CQ_REGION_BYTES=64'h200,
    parameter integer AXI_ID_WIDTH=4
)(
    input wire clk,rst,gmii_tx_clk,gmii_tx_rst,
    input wire tx_desc_valid,
    output wire tx_desc_ready,
    input wire [63:0] tx_desc_addr,tx_cq_slot_addr,
    output wire tx_cpl_written,tx_failed_o,
    input wire gmii_tx_en,gmii_tx_er,tx_error_underflow,
    output wire [63:0] tx_axis_tdata,
    output wire [7:0] tx_axis_tkeep,
    output wire tx_axis_tvalid,
    input wire tx_axis_tready,
    output wire tx_axis_tlast,tx_axis_tuser,
    output wire [AXI_ID_WIDTH-1:0] desc_arid,
    output wire [63:0] desc_araddr,
    output wire [7:0] desc_arlen,
    output wire [2:0] desc_arsize,
    output wire [1:0] desc_arburst,
    output wire desc_arlock,
    output wire [3:0] desc_arcache,
    output wire [2:0] desc_arprot,
    output wire desc_arvalid,
    input wire desc_arready,
    input wire [AXI_ID_WIDTH-1:0] desc_rid,
    input wire [63:0] desc_rdata,
    input wire [1:0] desc_rresp,
    input wire desc_rlast,
    input wire desc_rvalid,
    output wire desc_rready,
    output wire [AXI_ID_WIDTH-1:0] data_arid,
    output wire [63:0] data_araddr,
    output wire [7:0] data_arlen,
    output wire [2:0] data_arsize,
    output wire [1:0] data_arburst,
    output wire data_arlock,
    output wire [3:0] data_arcache,
    output wire [2:0] data_arprot,
    output wire data_arvalid,
    input wire data_arready,
    input wire [AXI_ID_WIDTH-1:0] data_rid,
    input wire [63:0] data_rdata,
    input wire [1:0] data_rresp,
    input wire data_rlast,
    input wire data_rvalid,
    output wire data_rready,
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
    localparam [2:0] IDLE=0,WAIT_DESC=1,ISSUE=2,
        WAIT_DMA=3,WAIT_WIRE=4,CQ_REQUEST=5,CQ_WAIT=6,FAIL=7;
    reg [2:0] state=IDLE;
    wire fetch_req_ready,fetch_valid,fetch_ok;
    wire [3:0] fetch_error;
    wire [63:0] fetch_src;
    wire [31:0] fetch_len,fetch_cookie;
    wire [7:0] fetch_tag;
    reg [63:0] src_addr=0;
    reg [15:0] length=0;
    reg [31:0] cookie=0,status=0;
    reg gmii_done_seen=0,gmii_bad_seen=0;
    wire dma_ready,dma_status_valid,dma_ok;
    wire [3:0] dma_error;
    wire [7:0] dma_tag;
    wire cq_req_ready,cq_done_valid,cq_written;
    wire [3:0] cq_error;
    wire [7:0] cq_tag;
    reg tx_failed=0;
    assign tx_failed_o=tx_failed;
    assign tx_desc_ready=(state==IDLE) && fetch_req_ready;
    assign tx_cpl_written=(state==CQ_WAIT) && cq_written;

    ethernet_rx_desc_fetch #(
      .AXI_ADDR_WIDTH(64),.AXI_ID_WIDTH(AXI_ID_WIDTH),
      .RING_BASE(RING_BASE),.RING_BYTES(RING_BYTES),
      .BUFFER_BASE(BUFFER_BASE),.BUFFER_BYTES(BUFFER_BYTES),
      .ALT_BUFFER_BASE(ALT_BUFFER_BASE),.ALT_BUFFER_BYTES(ALT_BUFFER_BYTES)
    ) u_tx_desc (
      .clk,.rst,
      .req_valid(tx_desc_valid && state==IDLE),
      .req_ready(fetch_req_ready),
      .req_ring_addr(tx_desc_addr),.req_frame_len(16'd1),
      .req_tag(8'd0),.result_valid(fetch_valid),
      .result_ready(state==WAIT_DESC),
      .result_ok(fetch_ok),.result_error(fetch_error),
      .result_buffer_addr(fetch_src),.result_capacity(fetch_len),
      .result_cookie(fetch_cookie),.result_tag(fetch_tag),
      .m_axi_arid(desc_arid),
      .m_axi_araddr(desc_araddr),
      .m_axi_arlen(desc_arlen),
      .m_axi_arsize(desc_arsize),
      .m_axi_arburst(desc_arburst),
      .m_axi_arlock(desc_arlock),
      .m_axi_arcache(desc_arcache),
      .m_axi_arprot(desc_arprot),
      .m_axi_arvalid(desc_arvalid),
      .m_axi_arready(desc_arready),
      .m_axi_rid(desc_rid),
      .m_axi_rdata(desc_rdata),
      .m_axi_rresp(desc_rresp),
      .m_axi_rlast(desc_rlast),
      .m_axi_rvalid(desc_rvalid),
      .m_axi_rready(desc_rready)
    );
    ethernet_tx_dma #(
      .AXI_ADDR_WIDTH(64),.AXI_DATA_WIDTH(64),
      .AXI_ID_WIDTH(AXI_ID_WIDTH),.LEN_WIDTH(16),
      .REGION_BASE(BUFFER_BASE),.REGION_BYTES(BUFFER_BYTES),
      .ALT_REGION_BASE(ALT_BUFFER_BASE),.ALT_REGION_BYTES(ALT_BUFFER_BYTES)
    ) u_tx_dma (
      .clk,.rst,
      .desc_valid(state==ISSUE),.desc_ready(dma_ready),
      .desc_src_addr(src_addr),.desc_length(length),
      .desc_capacity(length),.desc_tag(8'd0),
      .status_valid(dma_status_valid),.status_ok(dma_ok),
      .status_error(dma_error),.status_tag(dma_tag),
      .m_axis_tdata(tx_axis_tdata),.m_axis_tkeep(tx_axis_tkeep),
      .m_axis_tvalid(tx_axis_tvalid),.m_axis_tready(tx_axis_tready),
      .m_axis_tlast(tx_axis_tlast),.m_axis_tuser(tx_axis_tuser),
      .m_axi_arid(data_arid),
      .m_axi_araddr(data_araddr),
      .m_axi_arlen(data_arlen),
      .m_axi_arsize(data_arsize),
      .m_axi_arburst(data_arburst),
      .m_axi_arlock(data_arlock),
      .m_axi_arcache(data_arcache),
      .m_axi_arprot(data_arprot),
      .m_axi_arvalid(data_arvalid),
      .m_axi_arready(data_arready),
      .m_axi_rid(data_rid),
      .m_axi_rdata(data_rdata),
      .m_axi_rresp(data_rresp),
      .m_axi_rlast(data_rlast),
      .m_axi_rvalid(data_rvalid),
      .m_axi_rready(data_rready)
    );
    ethernet_cq_axi_writer #(
      .REGION_BASE(CQ_REGION_BASE),.REGION_BYTES(CQ_REGION_BYTES),
      .AXI_ID_WIDTH(AXI_ID_WIDTH)
    ) u_tx_cq (
      .clk,.rst,.req_valid(state==CQ_REQUEST),.req_ready(cq_req_ready),
      .req_addr(tx_cq_slot_addr),.req_cookie(cookie),
      .req_length({16'd0,length}),.req_status(status),
      .req_policy(32'd0),.req_queue(32'd1),.req_tag(8'd0),
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

    // Strict two-domain event counter: the GMII transmitter owns wire-end;
    // the AXIS sink handshake merely indicates MAC FIFO admission.
    reg tx_en_prev=0,tx_wire_error=0,wire_done_toggle=0,wire_bad_toggle=0;
    always @(posedge gmii_tx_clk) begin
      if(gmii_tx_rst)begin
        tx_en_prev<=0;tx_wire_error<=0;
        wire_done_toggle<=0;wire_bad_toggle<=0;
      end else begin
        tx_en_prev<=gmii_tx_en;
        if(gmii_tx_en && (gmii_tx_er || tx_error_underflow))
          tx_wire_error<=1;
        if(tx_en_prev && !gmii_tx_en)begin
          wire_done_toggle<=~wire_done_toggle;
          if(tx_wire_error)wire_bad_toggle<=~wire_bad_toggle;
          tx_wire_error<=0;
        end
      end
    end
    reg [2:0] wire_done_sync=0,wire_bad_sync=0;
    wire wire_done_pulse=wire_done_sync[2]!=wire_done_sync[1];
    wire wire_bad_pulse=wire_bad_sync[2]!=wire_bad_sync[1];
    always @(posedge clk)begin
      if(rst)begin
        wire_done_sync<=0;wire_bad_sync<=0;
      end else begin
        wire_done_sync<={wire_done_sync[1:0],wire_done_toggle};
        wire_bad_sync<={wire_bad_sync[1:0],wire_bad_toggle};
      end
    end

    always @(posedge clk)begin
      if(rst)begin
        state<=IDLE;src_addr<=0;length<=0;cookie<=0;status<=0;
        gmii_done_seen<=0;gmii_bad_seen<=0;tx_failed<=0;
      end else begin
        if(wire_done_pulse)gmii_done_seen<=1;
        if(wire_bad_pulse)gmii_bad_seen<=1;
        case(state)
          IDLE: if(tx_desc_valid && tx_desc_ready)begin
            gmii_done_seen<=0;gmii_bad_seen<=0;tx_failed<=0;
            status<=0;state<=WAIT_DESC;
          end
          WAIT_DESC: if(fetch_valid)begin
            cookie<=fetch_cookie;
            if(fetch_ok)begin
              src_addr<=fetch_src;
              length<=fetch_len[15:0];
              state<=ISSUE;
            end else begin
              length<=0;status<={28'd0,fetch_error};
              state<=CQ_REQUEST;
            end
          end
          ISSUE: if(dma_ready)state<=WAIT_DMA;
          WAIT_DMA: if(dma_status_valid)begin
            if(!dma_ok || dma_tag!=0)begin
              status<={28'd0,(dma_tag!=0?4'h9:dma_error)};
              state<=CQ_REQUEST;
            end else state<=WAIT_WIRE;
          end
          WAIT_WIRE: if(gmii_done_seen || wire_done_pulse)begin
            status<=(gmii_bad_seen || wire_bad_pulse)?32'hb:32'd0;
            state<=CQ_REQUEST;
          end
          CQ_REQUEST: if(cq_req_ready)state<=CQ_WAIT;
          CQ_WAIT: if(cq_written)state<=IDLE;
                   else if(cq_done_valid && !cq_written)begin
                     tx_failed<=1;state<=FAIL;
                   end
          FAIL: state<=FAIL; // fail closed: never retire a missing CQ
          default:state<=FAIL;
        endcase
      end
    end
    initial begin
      if(RING_BYTES<32 || CQ_REGION_BYTES<512 || RING_BASE[4:0] ||
         CQ_REGION_BASE[4:0] || AXI_ID_WIDTH<1)
        $fatal(1,"invalid Ethernet TX ring or AXI contract");
    end
endmodule
`default_nettype wire
