// Physical GMII -> MAC -> header stager -> RX queue -> AXI SRAM/CQ testbed.
// Each target is a real upstream axi_ram; no data-path behavioral shortcuts.
// The three AXI masters are still on separate memory ports (not full NoC).
`timescale 1ns/1ps
`default_nettype none
module ethernet0_rx_mvp_tb (
 input wire logic_clk,gmii_rx_clk,gmii_tx_clk,
 input wire logic_rst,gmii_rx_rst,gmii_tx_rst,
 input wire [7:0] gmii_rxd,
 input wire gmii_rx_dv,gmii_rx_er,
 input wire cfg_valid,cfg_write,
 input wire [7:0] cfg_addr,
 input wire [31:0] cfg_wdata,
 input wire [3:0] cfg_wstrb,
 output wire cfg_ready,
 output wire [31:0] cfg_rdata,
 output wire cfg_error,
 output wire irq,frame_drop,bad_fcs,
 input wire [15:0] desc_awaddr,
 input wire desc_awvalid,desc_wvalid,desc_wlast,desc_bready,
 input wire [63:0] desc_wdata,
 output wire desc_awready,desc_wready,desc_bvalid,
 output wire [1:0] desc_bresp,
 input wire [15:0] pkt_araddr,
 input wire pkt_arvalid,pkt_rready,
 output wire pkt_arready,pkt_rvalid,pkt_rlast,
 output wire [63:0] pkt_rdata,
 output wire [1:0] pkt_rresp,
 input wire [15:0] cqr_araddr,
 input wire cqr_arvalid,cqr_rready,
 output wire cqr_arready,cqr_rvalid,cqr_rlast,
 output wire [63:0] cqr_rdata,
 output wire [1:0] cqr_rresp,
 input wire cq_release_b,
 output reg [31:0] desc_ar_count=0,
 output reg [31:0] packet_b_count=0,
 output reg [31:0] cq_b_count=0
);
wire [3:0] rd_arid;
wire [63:0] rd_araddr;
wire [7:0] rd_arlen;
wire [2:0] rd_arsize;
wire [1:0] rd_arburst;
wire rd_arlock;
wire [3:0] rd_arcache;
wire [2:0] rd_arprot;
wire rd_arvalid;
wire rd_arready;
wire [3:0] rd_rid;
wire [63:0] rd_rdata;
wire [1:0] rd_rresp;
wire rd_rlast;
wire rd_rvalid;
wire rd_rready;
wire [3:0] wr_awid;
wire [63:0] wr_awaddr;
wire [7:0] wr_awlen;
wire [2:0] wr_awsize;
wire [1:0] wr_awburst;
wire wr_awlock;
wire [3:0] wr_awcache;
wire [2:0] wr_awprot;
wire wr_awvalid;
wire wr_awready;
wire [63:0] wr_wdata;
wire [7:0] wr_wstrb;
wire wr_wlast;
wire wr_wvalid;
wire wr_wready;
wire [3:0] wr_bid;
wire [1:0] wr_bresp;
wire wr_bvalid;
wire wr_bready;
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
ethernet0_rx_mvp dut (
 .logic_clk,.logic_rst,.gmii_rx_clk,.gmii_rx_rst,
 .gmii_tx_clk,.gmii_tx_rst,.gmii_rxd,.gmii_rx_dv,.gmii_rx_er,
 .cfg_valid,.cfg_write,.cfg_addr,.cfg_wdata,.cfg_wstrb,
 .cfg_ready,.cfg_rdata,.cfg_error,
 .irq_o(irq),.frame_drop_o(frame_drop),
 .cq_failed_o(),.rx_error_bad_fcs_o(bad_fcs),
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
 .wr_bready(wr_bready),
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
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_ring_ram (
 .clk(logic_clk),.rst(logic_rst),
 .s_axi_awid(4'd0),.s_axi_awaddr(desc_awaddr),.s_axi_awlen(8'd0),
 .s_axi_awsize(3'd3),.s_axi_awburst(2'b01),.s_axi_awlock(1'b0),
 .s_axi_awcache(4'd0),.s_axi_awprot(3'd0),
 .s_axi_awvalid(desc_awvalid),.s_axi_awready(desc_awready),
 .s_axi_wdata(desc_wdata),.s_axi_wstrb(8'hff),
 .s_axi_wlast(desc_wlast),.s_axi_wvalid(desc_wvalid),
 .s_axi_wready(desc_wready),.s_axi_bid(),
 .s_axi_bresp(desc_bresp),.s_axi_bvalid(desc_bvalid),
 .s_axi_bready(desc_bready),
 .s_axi_arid(rd_arid),.s_axi_araddr(rd_araddr[15:0]),
 .s_axi_arlen(rd_arlen),.s_axi_arsize(rd_arsize),
 .s_axi_arburst(rd_arburst),.s_axi_arlock(rd_arlock),
 .s_axi_arcache(rd_arcache),.s_axi_arprot(rd_arprot),
 .s_axi_arvalid(rd_arvalid),.s_axi_arready(rd_arready),
 .s_axi_rid(rd_rid),.s_axi_rdata(rd_rdata),
 .s_axi_rresp(rd_rresp),.s_axi_rlast(rd_rlast),
 .s_axi_rvalid(rd_rvalid),.s_axi_rready(rd_rready)
);
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_packet_ram (
 .clk(logic_clk),.rst(logic_rst),
 .s_axi_awid(wr_awid),.s_axi_awaddr(wr_awaddr[15:0]),
 .s_axi_awlen(wr_awlen),.s_axi_awsize(wr_awsize),
 .s_axi_awburst(wr_awburst),.s_axi_awlock(wr_awlock),
 .s_axi_awcache(wr_awcache),.s_axi_awprot(wr_awprot),
 .s_axi_awvalid(wr_awvalid),.s_axi_awready(wr_awready),
 .s_axi_wdata(wr_wdata),.s_axi_wstrb(wr_wstrb),
 .s_axi_wlast(wr_wlast),.s_axi_wvalid(wr_wvalid),
 .s_axi_wready(wr_wready),.s_axi_bid(wr_bid),
 .s_axi_bresp(wr_bresp),.s_axi_bvalid(wr_bvalid),
 .s_axi_bready(wr_bready),
 .s_axi_arid(4'd0),.s_axi_araddr(pkt_araddr),
 .s_axi_arlen(8'd0),.s_axi_arsize(3'd3),
 .s_axi_arburst(2'b01),.s_axi_arlock(1'b0),
 .s_axi_arcache(4'd0),.s_axi_arprot(3'd0),
 .s_axi_arvalid(pkt_arvalid),.s_axi_arready(pkt_arready),
 .s_axi_rid(),.s_axi_rdata(pkt_rdata),
 .s_axi_rresp(pkt_rresp),.s_axi_rlast(pkt_rlast),
 .s_axi_rvalid(pkt_rvalid),.s_axi_rready(pkt_rready)
);
wire cq_ram_bvalid;
wire cq_writer_bvalid = cq_ram_bvalid && cq_release_b;
wire cq_ram_bready = cq_bready && cq_release_b;
assign cq_bvalid = cq_writer_bvalid;
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
 .s_axi_bresp(cq_bresp),.s_axi_bvalid(cq_ram_bvalid),
 .s_axi_bready(cq_ram_bready),
 .s_axi_arid(4'd0),.s_axi_araddr(cqr_araddr),
 .s_axi_arlen(8'd0),.s_axi_arsize(3'd3),
 .s_axi_arburst(2'b01),.s_axi_arlock(1'b0),
 .s_axi_arcache(4'd0),.s_axi_arprot(3'd0),
 .s_axi_arvalid(cqr_arvalid),.s_axi_arready(cqr_arready),
 .s_axi_rid(),.s_axi_rdata(cqr_rdata),
 .s_axi_rresp(cqr_rresp),.s_axi_rlast(cqr_rlast),
 .s_axi_rvalid(cqr_rvalid),.s_axi_rready(cqr_rready)
);
always @(posedge logic_clk) begin
 if(logic_rst)begin
  desc_ar_count<=0;packet_b_count<=0;cq_b_count<=0;
 end else begin
  if(rd_arvalid && rd_arready) desc_ar_count<=desc_ar_count+1;
  if(wr_bvalid && wr_bready)begin
   if(wr_bresp!=0) $fatal(1,"packet B error");
   packet_b_count<=packet_b_count+1;
  end
  if(cq_ram_bvalid && cq_ram_bready)begin
   if(cq_bresp!=0) $fatal(1,"completion B error");
   cq_b_count<=cq_b_count+1;
  end
  if(cq_b_count>packet_b_count) $fatal(1,"CQ before payload B");
 end
end
endmodule
`default_nettype wire
