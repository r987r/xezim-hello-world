// Real TX descriptor and packet SRAM -> pinned AXI DMA -> MAC GMII
// -> B-gated CQ record; each RAM remains separate pending NoC mux wiring.
`timescale 1ns/1ps
`default_nettype none
module ethernet0_tx_mvp_tb (
 input wire logic_clk,logic_rst,
 input wire gmii_tx_clk,gmii_tx_rst,gmii_rx_clk,gmii_rx_rst,
 output wire [7:0] gmii_txd,
 output wire gmii_tx_en,gmii_tx_er,
 input wire tx_desc_valid,
 output wire tx_desc_ready,tx_cpl_written,tx_failed_o,
  input wire [15:0] desc_host_awaddr,
 input wire desc_host_awvalid,desc_host_wvalid,desc_host_wlast,
 input wire desc_host_bready,
 input wire [63:0] desc_host_wdata,
 output wire desc_host_awready,desc_host_wready,desc_host_bvalid,
 output wire [1:0] desc_host_bresp,
 input wire [15:0] data_host_awaddr,
 input wire data_host_awvalid,data_host_wvalid,data_host_wlast,
 input wire data_host_bready,
 input wire [63:0] data_host_wdata,
 output wire data_host_awready,data_host_wready,data_host_bvalid,
 output wire [1:0] data_host_bresp,
 input wire [15:0] cqr_araddr,
 input wire cqr_arvalid,cqr_rready,
 output wire cqr_arready,cqr_rvalid,cqr_rlast,
 output wire [63:0] cqr_rdata,
 output wire [1:0] cqr_rresp,
 input wire cq_release_b,
 output reg [31:0] descriptor_ar_count=0,packet_ar_count=0,cq_b_count=0
);
wire [3:0] desc_arid;
wire [63:0] desc_araddr;
wire [7:0] desc_arlen;
wire [2:0] desc_arsize;
wire [1:0] desc_arburst;
wire desc_arlock;
wire [3:0] desc_arcache;
wire [2:0] desc_arprot;
wire desc_arvalid;
wire desc_arready;
wire [3:0] desc_rid;
wire [63:0] desc_rdata;
wire [1:0] desc_rresp;
wire desc_rlast;
wire desc_rvalid;
wire desc_rready;
wire [3:0] data_arid;
wire [63:0] data_araddr;
wire [7:0] data_arlen;
wire [2:0] data_arsize;
wire [1:0] data_arburst;
wire data_arlock;
wire [3:0] data_arcache;
wire [2:0] data_arprot;
wire data_arvalid;
wire data_arready;
wire [3:0] data_rid;
wire [63:0] data_rdata;
wire [1:0] data_rresp;
wire data_rlast;
wire data_rvalid;
wire data_rready;
wire [3:0] cq_awid;
wire [63:0] cq_awaddr;
wire [7:0] cq_awlen;
wire [2:0] cq_awsize;
wire [1:0] cq_awburst;
wire cq_awlock;
wire [3:0] cq_awcache;
wire [2:0] cq_awprot;
wire cq_awvalid;
wire cq_awready;
wire [63:0] cq_wdata;
wire [7:0] cq_wstrb;
wire cq_wlast;
wire cq_wvalid;
wire cq_wready;
wire [3:0] cq_bid;
wire [1:0] cq_bresp;
wire cq_bvalid;
wire cq_bready;
wire [63:0] tx_axis_tdata;
wire [7:0] tx_axis_tkeep;
wire tx_axis_tvalid,tx_axis_tready,tx_axis_tlast,tx_axis_tuser;
wire tx_error_underflow;
wire cq_raw_bvalid;
assign cq_bvalid=cq_raw_bvalid && cq_release_b;

ethernet0_rx_gmii_stager #(.TX_ENABLE(1)) u_mac (
 .logic_clk,.logic_rst,.gmii_rx_clk,.gmii_rx_rst,
 .gmii_tx_clk,.gmii_tx_rst,
 .gmii_rxd(8'd0),.gmii_rx_dv(1'b0),.gmii_rx_er(1'b0),
 .tx_axis_tdata,.tx_axis_tkeep,.tx_axis_tvalid,.tx_axis_tready,
 .tx_axis_tlast,.tx_axis_tuser,
 .gmii_txd,.gmii_tx_en,.gmii_tx_er,.tx_error_underflow,
 .meta_valid(),.meta_ready(1'b0),.meta_length(),.meta_ethertype(),
 .meta_is_udp(),.meta_udp_dst_port(),
 .rx_axis_tdata(),.rx_axis_tkeep(),.rx_axis_tvalid(),
 .rx_axis_tready(1'b0),.rx_axis_tlast(),.rx_axis_tuser(),
 .rx_error_bad_fcs(),.rx_error_bad_frame(),.rx_fifo_overflow(),
 .rx_fifo_bad_frame(),.rx_fifo_good_frame(),.dropped_frame_pulse(),
 .stage_fifo_overflow()
);

ethernet0_tx_mvp dut (
 .clk(logic_clk),.rst(logic_rst),.gmii_tx_clk,.gmii_tx_rst,
 .tx_desc_valid,.tx_desc_ready,
 .tx_desc_addr(64'h600),.tx_cq_slot_addr(64'h700),
 .tx_cpl_written,.tx_failed_o,
 .gmii_tx_en,.gmii_tx_er,.tx_error_underflow,
 .tx_axis_tdata,.tx_axis_tkeep,.tx_axis_tvalid,.tx_axis_tready,
 .tx_axis_tlast,.tx_axis_tuser,
 .desc_arid(desc_arid),
 .desc_araddr(desc_araddr),
 .desc_arlen(desc_arlen),
 .desc_arsize(desc_arsize),
 .desc_arburst(desc_arburst),
 .desc_arlock(desc_arlock),
 .desc_arcache(desc_arcache),
 .desc_arprot(desc_arprot),
 .desc_arvalid(desc_arvalid),
 .desc_arready(desc_arready),
 .desc_rid(desc_rid),
 .desc_rdata(desc_rdata),
 .desc_rresp(desc_rresp),
 .desc_rlast(desc_rlast),
 .desc_rvalid(desc_rvalid),
 .desc_rready(desc_rready),
 .data_arid(data_arid),
 .data_araddr(data_araddr),
 .data_arlen(data_arlen),
 .data_arsize(data_arsize),
 .data_arburst(data_arburst),
 .data_arlock(data_arlock),
 .data_arcache(data_arcache),
 .data_arprot(data_arprot),
 .data_arvalid(data_arvalid),
 .data_arready(data_arready),
 .data_rid(data_rid),
 .data_rdata(data_rdata),
 .data_rresp(data_rresp),
 .data_rlast(data_rlast),
 .data_rvalid(data_rvalid),
 .data_rready(data_rready),
 .cq_awid(cq_awid),
 .cq_awaddr(cq_awaddr),
 .cq_awlen(cq_awlen),
 .cq_awsize(cq_awsize),
 .cq_awburst(cq_awburst),
 .cq_awlock(cq_awlock),
 .cq_awcache(cq_awcache),
 .cq_awprot(cq_awprot),
 .cq_awvalid(cq_awvalid),
 .cq_awready(cq_awready),
 .cq_wdata(cq_wdata),
 .cq_wstrb(cq_wstrb),
 .cq_wlast(cq_wlast),
 .cq_wvalid(cq_wvalid),
 .cq_wready(cq_wready),
 .cq_bid(cq_bid),
 .cq_bresp(cq_bresp),
 .cq_bvalid(cq_bvalid),
 .cq_bready(cq_bready)
);

axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_desc_ram (
 .clk(logic_clk),.rst(logic_rst),
 .s_axi_awid(4'd0),.s_axi_awaddr(desc_host_awaddr),
 .s_axi_awlen(8'd0),.s_axi_awsize(3'd3),.s_axi_awburst(2'b01),
 .s_axi_awlock(1'b0),.s_axi_awcache(4'd0),.s_axi_awprot(3'd0),
 .s_axi_awvalid(desc_host_awvalid),.s_axi_awready(desc_host_awready),
 .s_axi_wdata(desc_host_wdata),.s_axi_wstrb(8'hff),
 .s_axi_wlast(desc_host_wlast),.s_axi_wvalid(desc_host_wvalid),
 .s_axi_wready(desc_host_wready),.s_axi_bid(),
 .s_axi_bresp(desc_host_bresp),.s_axi_bvalid(desc_host_bvalid),
 .s_axi_bready(desc_host_bready),
 .s_axi_arid(desc_arid),.s_axi_araddr(desc_araddr[15:0]),
 .s_axi_arlen(desc_arlen),.s_axi_arsize(desc_arsize),
 .s_axi_arburst(desc_arburst),.s_axi_arlock(desc_arlock),
 .s_axi_arcache(desc_arcache),.s_axi_arprot(desc_arprot),
 .s_axi_arvalid(desc_arvalid),.s_axi_arready(desc_arready),
 .s_axi_rid(desc_rid),.s_axi_rdata(desc_rdata),
 .s_axi_rresp(desc_rresp),.s_axi_rlast(desc_rlast),
 .s_axi_rvalid(desc_rvalid),.s_axi_rready(desc_rready)
);
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_data_ram (
 .clk(logic_clk),.rst(logic_rst),
 .s_axi_awid(4'd0),.s_axi_awaddr(data_host_awaddr),
 .s_axi_awlen(8'd0),.s_axi_awsize(3'd3),.s_axi_awburst(2'b01),
 .s_axi_awlock(1'b0),.s_axi_awcache(4'd0),.s_axi_awprot(3'd0),
 .s_axi_awvalid(data_host_awvalid),.s_axi_awready(data_host_awready),
 .s_axi_wdata(data_host_wdata),.s_axi_wstrb(8'hff),
 .s_axi_wlast(data_host_wlast),.s_axi_wvalid(data_host_wvalid),
 .s_axi_wready(data_host_wready),.s_axi_bid(),
 .s_axi_bresp(data_host_bresp),.s_axi_bvalid(data_host_bvalid),
 .s_axi_bready(data_host_bready),
 .s_axi_arid(data_arid),.s_axi_araddr(data_araddr[15:0]),
 .s_axi_arlen(data_arlen),.s_axi_arsize(data_arsize),
 .s_axi_arburst(data_arburst),.s_axi_arlock(data_arlock),
 .s_axi_arcache(data_arcache),.s_axi_arprot(data_arprot),
 .s_axi_arvalid(data_arvalid),.s_axi_arready(data_arready),
 .s_axi_rid(data_rid),.s_axi_rdata(data_rdata),
 .s_axi_rresp(data_rresp),.s_axi_rlast(data_rlast),
 .s_axi_rvalid(data_rvalid),.s_axi_rready(data_rready)
);
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_cq_ram (
 .clk(logic_clk),.rst(logic_rst),
 .s_axi_awid(cq_awid),.s_axi_awaddr(cq_awaddr[15:0]),
 .s_axi_awlen(cq_awlen),.s_axi_awsize(cq_awsize),
 .s_axi_awburst(cq_awburst),.s_axi_awlock(cq_awlock),
 .s_axi_awcache(cq_awcache),.s_axi_awprot(cq_awprot),
 .s_axi_awvalid(cq_awvalid),.s_axi_awready(cq_awready),
 .s_axi_wdata(cq_wdata),.s_axi_wstrb(cq_wstrb),
 .s_axi_wlast(cq_wlast),.s_axi_wvalid(cq_wvalid),
 .s_axi_wready(cq_wready),.s_axi_bid(cq_bid),
 .s_axi_bresp(cq_bresp),.s_axi_bvalid(cq_raw_bvalid),
 .s_axi_bready(cq_bready && cq_release_b),
 .s_axi_arid(4'd0),.s_axi_araddr(cqr_araddr),
 .s_axi_arlen(8'd0),.s_axi_arsize(3'd3),
 .s_axi_arburst(2'b01),.s_axi_arlock(1'b0),
 .s_axi_arcache(4'd0),.s_axi_arprot(3'd0),
 .s_axi_arvalid(cqr_arvalid),.s_axi_arready(cqr_arready),
 .s_axi_rid(),.s_axi_rdata(cqr_rdata),
 .s_axi_rresp(cqr_rresp),.s_axi_rlast(cqr_rlast),
 .s_axi_rvalid(cqr_rvalid),.s_axi_rready(cqr_rready)
);
always @(posedge logic_clk)begin
 if(logic_rst)begin
  descriptor_ar_count<=0;packet_ar_count<=0;cq_b_count<=0;
 end else begin
  if(desc_arvalid && desc_arready)descriptor_ar_count<=descriptor_ar_count+1;
  if(data_arvalid && data_arready)packet_ar_count<=packet_ar_count+1;
  if(cq_raw_bvalid && cq_bready && cq_release_b)begin
   if(cq_bresp!=0)$fatal(1,"TX CQ bad B");
   cq_b_count<=cq_b_count+1;
  end
 end
end
endmodule
`default_nettype wire
