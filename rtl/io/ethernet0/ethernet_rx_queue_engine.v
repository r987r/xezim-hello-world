// Standalone verified-frame queue ingress: policy -> AXI descriptor -> AXI write.
// For real MAC integration, a whole-frame staging buffer must supply the
// immutable header, byte length and AXI-stream payload. No CQ writer here.
`timescale 1ns/1ps
module ethernet_rx_queue_engine #(
 parameter [63:0] RING_BASE=64'h100, RING_BYTES=64'h1000,
 parameter [63:0] BUFFER_BASE=64'h2000, BUFFER_BYTES=64'h8000
)(
 input wire clk,rst,cfg_valid,cfg_write,
 input wire [7:0] cfg_addr,input wire [31:0] cfg_wdata,
 input wire [3:0] cfg_wstrb,
 output wire cfg_ready,output wire [31:0] cfg_rdata,output wire cfg_error,
 input wire tx_desc_ready_i, input wire tx_cpl_written_i,
 output wire tx_desc_valid_o, output wire [63:0] tx_desc_addr_o,
 output wire [63:0] rx_cq_slot_addr_o, tx_cq_slot_addr_o,
 input wire frame_valid,output wire frame_ready,
 input wire [15:0] frame_length,frame_ethertype,
 input wire frame_is_udp,input wire [15:0] frame_udp_dst_port,
 input wire [63:0] rx_axis_tdata,input wire [7:0] rx_axis_tkeep,
 input wire rx_axis_tvalid,output wire rx_axis_tready,
 input wire rx_axis_tlast,rx_axis_tuser,
 output reg write_result_valid,write_result_ok,
 output reg [3:0] write_result_error,
 output reg [15:0] write_result_length,
 output reg [31:0] write_result_cookie,
 output reg [7:0] write_result_policy,
 output reg [7:0] write_result_tag,
 output reg frame_drop_pulse,
 input wire cpl_written_i,output wire irq,
 output wire [3:0] rd_arid,output wire [63:0] rd_araddr,
 output wire [7:0] rd_arlen,output wire [2:0] rd_arsize,
 output wire [1:0] rd_arburst,output wire rd_arlock,
 output wire [3:0] rd_arcache,output wire [2:0] rd_arprot,
 output wire rd_arvalid,input wire rd_arready,
 input wire [3:0] rd_rid,input wire [63:0] rd_rdata,
 input wire [1:0] rd_rresp,input wire rd_rlast,rd_rvalid,
 output wire rd_rready,
 output wire [3:0] wr_awid,output wire [63:0] wr_awaddr,
 output wire [7:0] wr_awlen,output wire [2:0] wr_awsize,
 output wire [1:0] wr_awburst,output wire wr_awlock,
 output wire [3:0] wr_awcache,output wire [2:0] wr_awprot,
 output wire wr_awvalid,input wire wr_awready,
 output wire [63:0] wr_wdata,output wire [7:0] wr_wstrb,
 output wire wr_wlast,wr_wvalid,input wire wr_wready,
 input wire [3:0] wr_bid,input wire [1:0] wr_bresp,
 input wire wr_bvalid,output wire wr_bready
);
 localparam [2:0] IDLE=0,ROUTE=1,FETCH=2,WAIT_DESC=3,
                  ISSUE=4,STREAM=5,DROP=6,WAIT_CPL=7;
 reg [2:0] state=IDLE;
 reg [15:0] packet_length=0,capacity=0;
 reg [63:0] dst_addr=0;
 reg [31:0] cookie=0;
 reg [7:0] active_tag=0;
 reg owns_descriptor=0;
 wire route_valid,route_drop,route_ready;
 wire [0:0] route_q,rx_desc_q,tx_desc_q;
 wire [7:0] route_policy;
 wire [7:0] queue_active_policy;
 wire rx_desc_valid,rx_desc_ready,tx_desc_valid;
 wire [63:0] rx_desc_addr,tx_desc_addr;
 wire fetch_ready,fetch_valid,fetch_ok;
 wire [3:0] fetch_error;
 wire [63:0] fetch_dst;
 wire [31:0] fetch_capacity,fetch_cookie;
 wire [7:0] fetch_tag;
 wire dma_ready,dma_axis_ready,dma_status_valid,dma_status_ok;
 wire [3:0] dma_error;
 wire [7:0] dma_tag;
 wire [15:0] dma_length;
 assign frame_ready=state==IDLE && route_ready;
 assign tx_desc_valid_o=tx_desc_valid;
 assign tx_desc_addr_o=tx_desc_addr;
 assign rx_axis_tready=state==STREAM ? dma_axis_ready : state==DROP;
 assign rx_desc_ready=state==FETCH && fetch_ready;

 ethernet_queue_ctrl #(.RX_QUEUES(1),.TX_QUEUES(1),
  .POLICY_ENTRIES(4),.RING_LOG2(4)) u_queue (
  .clk,.rst,.cfg_valid,.cfg_write,.cfg_addr,.cfg_wdata,.cfg_wstrb,
  .cfg_ready,.cfg_rdata,.cfg_error,
  .rx_meta_valid(frame_valid && frame_ready),.rx_meta_ready(route_ready),
  .rx_ethertype(frame_ethertype),.rx_is_udp(frame_is_udp),
  .rx_udp_dst_port(frame_udp_dst_port),.rx_route_valid(route_valid),
  .rx_route_drop(route_drop),.rx_route_queue(route_q),
  .rx_route_policy(route_policy),.rx_desc_valid(rx_desc_valid),
  .rx_desc_ready(rx_desc_ready),.rx_desc_addr(rx_desc_addr),
  .rx_desc_queue(rx_desc_q),.tx_desc_valid(tx_desc_valid),
  .tx_desc_ready(tx_desc_ready_i),.tx_desc_addr(tx_desc_addr),
  .rx_cq_slot_addr(rx_cq_slot_addr_o),
  .tx_cq_slot_addr(tx_cq_slot_addr_o),
  .rx_active_policy_o(queue_active_policy),
  .tx_desc_queue(tx_desc_q),
  .rx_cpl_written(cpl_written_i && state==WAIT_CPL),
  .tx_cpl_written(tx_cpl_written_i),.irq
 );
 ethernet_rx_desc_fetch #(.AXI_ADDR_WIDTH(64),.AXI_ID_WIDTH(4),
  .RING_BASE(RING_BASE),.RING_BYTES(RING_BYTES),
  .BUFFER_BASE(BUFFER_BASE),.BUFFER_BYTES(BUFFER_BYTES)) u_fetch (
  .clk,.rst,.req_valid(rx_desc_valid && state==FETCH),
  .req_ready(fetch_ready),.req_ring_addr(rx_desc_addr),
  .req_frame_len(packet_length),.req_tag(8'd0),
  .result_valid(fetch_valid),.result_ready(state==WAIT_DESC),
  .result_ok(fetch_ok),.result_error(fetch_error),
  .result_buffer_addr(fetch_dst),.result_capacity(fetch_capacity),
  .result_cookie(fetch_cookie),.result_tag(fetch_tag),
  .m_axi_arid(rd_arid),.m_axi_araddr(rd_araddr),
  .m_axi_arlen(rd_arlen),.m_axi_arsize(rd_arsize),
  .m_axi_arburst(rd_arburst),.m_axi_arlock(rd_arlock),
  .m_axi_arcache(rd_arcache),.m_axi_arprot(rd_arprot),
  .m_axi_arvalid(rd_arvalid),.m_axi_arready(rd_arready),
  .m_axi_rid(rd_rid),.m_axi_rdata(rd_rdata),
  .m_axi_rresp(rd_rresp),.m_axi_rlast(rd_rlast),
  .m_axi_rvalid(rd_rvalid),.m_axi_rready(rd_rready)
 );
 ethernet_rx_dma #(.AXI_ADDR_WIDTH(64),.AXI_DATA_WIDTH(64),
  .AXI_ID_WIDTH(4),.LEN_WIDTH(16),
  .REGION_BASE(BUFFER_BASE),.REGION_BYTES(BUFFER_BYTES)) u_write (
  .clk,.rst,.desc_valid(state==ISSUE),.desc_ready(dma_ready),
  .desc_dst_addr(dst_addr),.desc_length(packet_length),
  .desc_capacity(capacity),.desc_tag(active_tag),
  .status_valid(dma_status_valid),.status_ok(dma_status_ok),
  .status_error(dma_error),.status_tag(dma_tag),
  .status_length(dma_length),.s_axis_tdata(rx_axis_tdata),
  .s_axis_tkeep(rx_axis_tkeep),.s_axis_tvalid(rx_axis_tvalid && state==STREAM),
  .s_axis_tready(dma_axis_ready),.s_axis_tlast(rx_axis_tlast),
  .s_axis_tuser(rx_axis_tuser),
  .m_axi_awid(wr_awid),.m_axi_awaddr(wr_awaddr),
  .m_axi_awlen(wr_awlen),.m_axi_awsize(wr_awsize),
  .m_axi_awburst(wr_awburst),.m_axi_awlock(wr_awlock),
  .m_axi_awcache(wr_awcache),.m_axi_awprot(wr_awprot),
  .m_axi_awvalid(wr_awvalid),.m_axi_awready(wr_awready),
  .m_axi_wdata(wr_wdata),.m_axi_wstrb(wr_wstrb),
  .m_axi_wlast(wr_wlast),.m_axi_wvalid(wr_wvalid),
  .m_axi_wready(wr_wready),.m_axi_bid(wr_bid),
  .m_axi_bresp(wr_bresp),.m_axi_bvalid(wr_bvalid),
  .m_axi_bready(wr_bready)
 );
 always @(posedge clk) begin
  if(rst) begin
   state<=IDLE;packet_length<=0;capacity<=0;dst_addr<=0;
   cookie<=0;active_tag<=0;owns_descriptor<=0;
   write_result_valid<=0;write_result_ok<=0;
   write_result_error<=0;write_result_length<=0;
   write_result_cookie<=0;write_result_tag<=0;frame_drop_pulse<=0;
   write_result_policy<=0;
  end else begin
   write_result_valid<=0;frame_drop_pulse<=0;
   case(state)
    IDLE: if(frame_valid && frame_ready) begin
     packet_length<=frame_length;owns_descriptor<=0;state<=ROUTE;
    end
    ROUTE: if(route_valid) begin
     write_result_policy<=queue_active_policy;
     if(route_drop) begin frame_drop_pulse<=1;state<=DROP;end
     else state<=FETCH;
    end
    FETCH: if(rx_desc_valid && rx_desc_ready) begin
     owns_descriptor<=1;state<=WAIT_DESC;
    end
    WAIT_DESC: if(fetch_valid) begin
     cookie<=fetch_cookie;
     if(!fetch_ok) begin
      write_result_valid<=1;write_result_ok<=0;
      write_result_error<=fetch_error;write_result_length<=0;
      write_result_cookie<=fetch_cookie;write_result_tag<=fetch_tag;
      frame_drop_pulse<=1;state<=DROP;
     end else begin
      dst_addr<=fetch_dst;capacity<=fetch_capacity[15:0];
      active_tag<=fetch_tag;state<=ISSUE;
     end
    end
    ISSUE: if(dma_ready) state<=STREAM;
    STREAM: if(dma_status_valid) begin
     write_result_valid<=1;write_result_ok<=dma_status_ok;
     write_result_error<=dma_error;write_result_length<=dma_length;
     write_result_cookie<=cookie;write_result_tag<=dma_tag;
     state<=WAIT_CPL;
    end
    DROP: if(rx_axis_tvalid && rx_axis_tready && rx_axis_tlast)
     state<=owns_descriptor ? WAIT_CPL : IDLE;
    WAIT_CPL: if(cpl_written_i) state<=IDLE;
    default: state<=IDLE;
   endcase
  end
 end
endmodule
