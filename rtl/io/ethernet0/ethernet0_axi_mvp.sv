// Ethernet0 Data NoC integration adapter.
// SIX real AXI initiators: RX descriptor AR/R, RX packet AW/W/B, RX CQ AW/W/B,
// TX descriptor AR/R, TX payload AR/R, TX CQ AW/W/B.
// Only upstream PULP axi_mux arbitrates and preserves transaction IDs.
// 1-bit per-IP source ID + 3-bit mux port number == 4-bit Ethernet0 NI ID.
// All requests (including CQ B) traverse one AXI4 master to the local NoC.
// No homegrown bus arbitration or invented/masked successful completions.
`include "axi/typedef.svh"
module ethernet0_axi_mvp #(
  parameter logic [63:0] RX_RING_BASE=64'h100,
  parameter logic [63:0] RX_RING_BYTES=64'h1000,
  parameter logic [63:0] TX_RING_BASE=64'h600,
  parameter logic [63:0] TX_RING_BYTES=64'h200,
  parameter logic [63:0] BUFFER_BASE=64'h2000,
  parameter logic [63:0] BUFFER_BYTES=64'h8000,
  parameter logic [63:0] ALT_BUFFER_BASE=64'd0,
  parameter logic [63:0] ALT_BUFFER_BYTES=64'd0,
  parameter logic [63:0] RX_CQ_BASE=64'h500,
  parameter logic [63:0] TX_CQ_BASE=64'h700,
  parameter logic [63:0] CQ_WINDOW_BYTES=64'h200
)(
  input wire logic_clk,logic_rst,
  input wire gmii_rx_clk,gmii_rx_rst,gmii_tx_clk,gmii_tx_rst,
  input wire [7:0] gmii_rxd,
  input wire gmii_rx_dv,gmii_rx_er,
  output wire [7:0] gmii_txd,
  output wire gmii_tx_en,gmii_tx_er,
  input wire cfg_valid,cfg_write,
  input wire [7:0] cfg_addr,
  input wire [31:0] cfg_wdata,
  input wire [3:0] cfg_wstrb,
  output wire cfg_ready,cfg_error,irq_o,frame_drop_o,
  output wire [31:0] cfg_rdata,
  output wire rx_error_bad_fcs_o,tx_failed_o,
  output wire [3:0] axi_awid,
  output wire [63:0] axi_awaddr,
  output wire [7:0] axi_awlen,
  output wire [2:0] axi_awsize,
  output wire [1:0] axi_awburst,
  output wire axi_awlock,
  output wire [3:0] axi_awcache,
  output wire [2:0] axi_awprot,
  output wire axi_awvalid,
  input wire axi_awready,
  output wire [63:0] axi_wdata,
  output wire [7:0] axi_wstrb,
  output wire axi_wlast,
  output wire axi_wvalid,
  input wire axi_wready,
  input wire [3:0] axi_bid,
  input wire [1:0] axi_bresp,
  input wire axi_bvalid,
  output wire axi_bready,
  output wire [3:0] axi_arid,
  output wire [63:0] axi_araddr,
  output wire [7:0] axi_arlen,
  output wire [2:0] axi_arsize,
  output wire [1:0] axi_arburst,
  output wire axi_arlock,
  output wire [3:0] axi_arcache,
  output wire [2:0] axi_arprot,
  output wire axi_arvalid,
  input wire axi_arready,
  input wire [3:0] axi_rid,
  input wire [63:0] axi_rdata,
  input wire [1:0] axi_rresp,
  input wire axi_rlast,
  input wire axi_rvalid,
  output wire axi_rready
);
  typedef logic [63:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [7:0] strb_t;
  typedef logic [0:0] id1_t;
  typedef logic [3:0] id4_t;
  typedef logic [0:0] user_t;
  `AXI_TYPEDEF_ALL(eth1, addr_t, id1_t, data_t, strb_t, user_t)
  `AXI_TYPEDEF_ALL(eth4, addr_t, id4_t, data_t, strb_t, user_t)
  eth1_req_t [5:0] in_req;
  eth1_resp_t [5:0] in_rsp;
  eth4_req_t out_req;
  eth4_resp_t out_rsp;
  wire rx_desc_arid;
  wire [63:0] rx_desc_araddr;
  wire [7:0] rx_desc_arlen;
  wire [2:0] rx_desc_arsize;
  wire [1:0] rx_desc_arburst;
  wire rx_desc_arlock;
  wire [3:0] rx_desc_arcache;
  wire [2:0] rx_desc_arprot;
  wire rx_desc_arvalid;
  wire rx_desc_arready;
  wire rx_desc_rid;
  wire [63:0] rx_desc_rdata;
  wire [1:0] rx_desc_rresp;
  wire rx_desc_rlast;
  wire rx_desc_rvalid;
  wire rx_desc_rready;
  wire rx_data_awid;
  wire [63:0] rx_data_awaddr;
  wire [7:0] rx_data_awlen;
  wire [2:0] rx_data_awsize;
  wire [1:0] rx_data_awburst;
  wire rx_data_awlock;
  wire [3:0] rx_data_awcache;
  wire [2:0] rx_data_awprot;
  wire rx_data_awvalid;
  wire rx_data_awready;
  wire [63:0] rx_data_wdata;
  wire [7:0] rx_data_wstrb;
  wire rx_data_wlast;
  wire rx_data_wvalid;
  wire rx_data_wready;
  wire rx_data_bid;
  wire [1:0] rx_data_bresp;
  wire rx_data_bvalid;
  wire rx_data_bready;
  wire rx_cq_awid;
  wire [63:0] rx_cq_awaddr;
  wire [7:0] rx_cq_awlen;
  wire [2:0] rx_cq_awsize;
  wire [1:0] rx_cq_awburst;
  wire rx_cq_awlock;
  wire [3:0] rx_cq_awcache;
  wire [2:0] rx_cq_awprot;
  wire rx_cq_awvalid;
  wire rx_cq_awready;
  wire [63:0] rx_cq_wdata;
  wire [7:0] rx_cq_wstrb;
  wire rx_cq_wlast;
  wire rx_cq_wvalid;
  wire rx_cq_wready;
  wire rx_cq_bid;
  wire [1:0] rx_cq_bresp;
  wire rx_cq_bvalid;
  wire rx_cq_bready;
  wire tx_desc_arid;
  wire [63:0] tx_desc_araddr;
  wire [7:0] tx_desc_arlen;
  wire [2:0] tx_desc_arsize;
  wire [1:0] tx_desc_arburst;
  wire tx_desc_arlock;
  wire [3:0] tx_desc_arcache;
  wire [2:0] tx_desc_arprot;
  wire tx_desc_arvalid;
  wire tx_desc_arready;
  wire tx_desc_rid;
  wire [63:0] tx_desc_rdata;
  wire [1:0] tx_desc_rresp;
  wire tx_desc_rlast;
  wire tx_desc_rvalid;
  wire tx_desc_rready;
  wire tx_data_arid;
  wire [63:0] tx_data_araddr;
  wire [7:0] tx_data_arlen;
  wire [2:0] tx_data_arsize;
  wire [1:0] tx_data_arburst;
  wire tx_data_arlock;
  wire [3:0] tx_data_arcache;
  wire [2:0] tx_data_arprot;
  wire tx_data_arvalid;
  wire tx_data_arready;
  wire tx_data_rid;
  wire [63:0] tx_data_rdata;
  wire [1:0] tx_data_rresp;
  wire tx_data_rlast;
  wire tx_data_rvalid;
  wire tx_data_rready;
  wire tx_cq_awid;
  wire [63:0] tx_cq_awaddr;
  wire [7:0] tx_cq_awlen;
  wire [2:0] tx_cq_awsize;
  wire [1:0] tx_cq_awburst;
  wire tx_cq_awlock;
  wire [3:0] tx_cq_awcache;
  wire [2:0] tx_cq_awprot;
  wire tx_cq_awvalid;
  wire tx_cq_awready;
  wire [63:0] tx_cq_wdata;
  wire [7:0] tx_cq_wstrb;
  wire tx_cq_wlast;
  wire tx_cq_wvalid;
  wire tx_cq_wready;
  wire tx_cq_bid;
  wire [1:0] tx_cq_bresp;
  wire tx_cq_bvalid;
  wire tx_cq_bready;
  ethernet0_mvp #(
    .AXI_ID_WIDTH(1),.RX_RING_BASE(RX_RING_BASE),
    .RX_RING_BYTES(RX_RING_BYTES),.TX_RING_BASE(TX_RING_BASE),
    .TX_RING_BYTES(TX_RING_BYTES),.BUFFER_BASE(BUFFER_BASE),
    .BUFFER_BYTES(BUFFER_BYTES),.ALT_BUFFER_BASE(ALT_BUFFER_BASE),
    .ALT_BUFFER_BYTES(ALT_BUFFER_BYTES),.RX_CQ_BASE(RX_CQ_BASE),
    .TX_CQ_BASE(TX_CQ_BASE),.CQ_WINDOW_BYTES(CQ_WINDOW_BYTES)
  ) u_mvp (
    .logic_clk,.logic_rst,.gmii_rx_clk,.gmii_rx_rst,
    .gmii_tx_clk,.gmii_tx_rst,.gmii_rxd,.gmii_rx_dv,.gmii_rx_er,
    .gmii_txd,.gmii_tx_en,.gmii_tx_er,
    .cfg_valid,.cfg_write,.cfg_addr,.cfg_wdata,.cfg_wstrb,
    .cfg_ready,.cfg_error,.irq_o,.frame_drop_o,
    .cfg_rdata,.rx_error_bad_fcs_o,.tx_failed_o,
    .rx_desc_arid(rx_desc_arid),
    .rx_desc_araddr(rx_desc_araddr),
    .rx_desc_arlen(rx_desc_arlen),
    .rx_desc_arsize(rx_desc_arsize),
    .rx_desc_arburst(rx_desc_arburst),
    .rx_desc_arlock(rx_desc_arlock),
    .rx_desc_arcache(rx_desc_arcache),
    .rx_desc_arprot(rx_desc_arprot),
    .rx_desc_arvalid(rx_desc_arvalid),
    .rx_desc_arready(rx_desc_arready),
    .rx_desc_rid(rx_desc_rid),
    .rx_desc_rdata(rx_desc_rdata),
    .rx_desc_rresp(rx_desc_rresp),
    .rx_desc_rlast(rx_desc_rlast),
    .rx_desc_rvalid(rx_desc_rvalid),
    .rx_desc_rready(rx_desc_rready),
    .rx_data_awid(rx_data_awid),
    .rx_data_awaddr(rx_data_awaddr),
    .rx_data_awlen(rx_data_awlen),
    .rx_data_awsize(rx_data_awsize),
    .rx_data_awburst(rx_data_awburst),
    .rx_data_awlock(rx_data_awlock),
    .rx_data_awcache(rx_data_awcache),
    .rx_data_awprot(rx_data_awprot),
    .rx_data_awvalid(rx_data_awvalid),
    .rx_data_awready(rx_data_awready),
    .rx_data_wdata(rx_data_wdata),
    .rx_data_wstrb(rx_data_wstrb),
    .rx_data_wlast(rx_data_wlast),
    .rx_data_wvalid(rx_data_wvalid),
    .rx_data_wready(rx_data_wready),
    .rx_data_bid(rx_data_bid),
    .rx_data_bresp(rx_data_bresp),
    .rx_data_bvalid(rx_data_bvalid),
    .rx_data_bready(rx_data_bready),
    .rx_cq_awid(rx_cq_awid),
    .rx_cq_awaddr(rx_cq_awaddr),
    .rx_cq_awlen(rx_cq_awlen),
    .rx_cq_awsize(rx_cq_awsize),
    .rx_cq_awburst(rx_cq_awburst),
    .rx_cq_awlock(rx_cq_awlock),
    .rx_cq_awcache(rx_cq_awcache),
    .rx_cq_awprot(rx_cq_awprot),
    .rx_cq_awvalid(rx_cq_awvalid),
    .rx_cq_awready(rx_cq_awready),
    .rx_cq_wdata(rx_cq_wdata),
    .rx_cq_wstrb(rx_cq_wstrb),
    .rx_cq_wlast(rx_cq_wlast),
    .rx_cq_wvalid(rx_cq_wvalid),
    .rx_cq_wready(rx_cq_wready),
    .rx_cq_bid(rx_cq_bid),
    .rx_cq_bresp(rx_cq_bresp),
    .rx_cq_bvalid(rx_cq_bvalid),
    .rx_cq_bready(rx_cq_bready),
    .tx_desc_arid(tx_desc_arid),
    .tx_desc_araddr(tx_desc_araddr),
    .tx_desc_arlen(tx_desc_arlen),
    .tx_desc_arsize(tx_desc_arsize),
    .tx_desc_arburst(tx_desc_arburst),
    .tx_desc_arlock(tx_desc_arlock),
    .tx_desc_arcache(tx_desc_arcache),
    .tx_desc_arprot(tx_desc_arprot),
    .tx_desc_arvalid(tx_desc_arvalid),
    .tx_desc_arready(tx_desc_arready),
    .tx_desc_rid(tx_desc_rid),
    .tx_desc_rdata(tx_desc_rdata),
    .tx_desc_rresp(tx_desc_rresp),
    .tx_desc_rlast(tx_desc_rlast),
    .tx_desc_rvalid(tx_desc_rvalid),
    .tx_desc_rready(tx_desc_rready),
    .tx_data_arid(tx_data_arid),
    .tx_data_araddr(tx_data_araddr),
    .tx_data_arlen(tx_data_arlen),
    .tx_data_arsize(tx_data_arsize),
    .tx_data_arburst(tx_data_arburst),
    .tx_data_arlock(tx_data_arlock),
    .tx_data_arcache(tx_data_arcache),
    .tx_data_arprot(tx_data_arprot),
    .tx_data_arvalid(tx_data_arvalid),
    .tx_data_arready(tx_data_arready),
    .tx_data_rid(tx_data_rid),
    .tx_data_rdata(tx_data_rdata),
    .tx_data_rresp(tx_data_rresp),
    .tx_data_rlast(tx_data_rlast),
    .tx_data_rvalid(tx_data_rvalid),
    .tx_data_rready(tx_data_rready),
    .tx_cq_awid(tx_cq_awid),
    .tx_cq_awaddr(tx_cq_awaddr),
    .tx_cq_awlen(tx_cq_awlen),
    .tx_cq_awsize(tx_cq_awsize),
    .tx_cq_awburst(tx_cq_awburst),
    .tx_cq_awlock(tx_cq_awlock),
    .tx_cq_awcache(tx_cq_awcache),
    .tx_cq_awprot(tx_cq_awprot),
    .tx_cq_awvalid(tx_cq_awvalid),
    .tx_cq_awready(tx_cq_awready),
    .tx_cq_wdata(tx_cq_wdata),
    .tx_cq_wstrb(tx_cq_wstrb),
    .tx_cq_wlast(tx_cq_wlast),
    .tx_cq_wvalid(tx_cq_wvalid),
    .tx_cq_wready(tx_cq_wready),
    .tx_cq_bid(tx_cq_bid),
    .tx_cq_bresp(tx_cq_bresp),
    .tx_cq_bvalid(tx_cq_bvalid),
    .tx_cq_bready(tx_cq_bready)
  );
  // UNUSED channel requests remain zero; no synthetic AXI transactions.

  // AXI source 0: rx_desc (rd).
  assign in_req[0].aw = '0;
  assign in_req[0].aw_valid = 1'b0;
  assign in_req[0].w = '0;
  assign in_req[0].w_valid = 1'b0;
  assign in_req[0].b_ready = 1'b0;
  assign in_req[0].ar.id = rx_desc_arid;
  assign in_req[0].ar.addr = rx_desc_araddr;
  assign in_req[0].ar.len = rx_desc_arlen;
  assign in_req[0].ar.size = rx_desc_arsize;
  assign in_req[0].ar.burst = rx_desc_arburst;
  assign in_req[0].ar.lock = rx_desc_arlock;
  assign in_req[0].ar.cache = rx_desc_arcache;
  assign in_req[0].ar.prot = rx_desc_arprot;
  assign in_req[0].ar_valid = rx_desc_arvalid;
  assign rx_desc_arready = in_rsp[0].ar_ready;
  assign rx_desc_rid = in_rsp[0].r.id;
  assign rx_desc_rdata = in_rsp[0].r.data;
  assign rx_desc_rresp = in_rsp[0].r.resp;
  assign rx_desc_rlast = in_rsp[0].r.last;
  assign rx_desc_rvalid = in_rsp[0].r_valid;
  assign in_req[0].r_ready = rx_desc_rready;
  assign in_req[0].ar.qos = '0;
  assign in_req[0].ar.region = '0;
  assign in_req[0].ar.user = '0;

  // AXI source 1: rx_data (wr).
  assign in_req[1].ar = '0;
  assign in_req[1].ar_valid = 1'b0;
  assign in_req[1].r_ready = 1'b0;
  assign in_req[1].aw.id = rx_data_awid;
  assign in_req[1].aw.addr = rx_data_awaddr;
  assign in_req[1].aw.len = rx_data_awlen;
  assign in_req[1].aw.size = rx_data_awsize;
  assign in_req[1].aw.burst = rx_data_awburst;
  assign in_req[1].aw.lock = rx_data_awlock;
  assign in_req[1].aw.cache = rx_data_awcache;
  assign in_req[1].aw.prot = rx_data_awprot;
  assign in_req[1].aw_valid = rx_data_awvalid;
  assign rx_data_awready = in_rsp[1].aw_ready;
  assign in_req[1].w.data = rx_data_wdata;
  assign in_req[1].w.strb = rx_data_wstrb;
  assign in_req[1].w.last = rx_data_wlast;
  assign in_req[1].w_valid = rx_data_wvalid;
  assign rx_data_wready = in_rsp[1].w_ready;
  assign rx_data_bid = in_rsp[1].b.id;
  assign rx_data_bresp = in_rsp[1].b.resp;
  assign rx_data_bvalid = in_rsp[1].b_valid;
  assign in_req[1].b_ready = rx_data_bready;
  assign in_req[1].aw.qos = '0;
  assign in_req[1].aw.region = '0;
  assign in_req[1].aw.user = '0;
  assign in_req[1].aw.atop = '0;
  assign in_req[1].w.user = '0;

  // AXI source 2: rx_cq (wr).
  assign in_req[2].ar = '0;
  assign in_req[2].ar_valid = 1'b0;
  assign in_req[2].r_ready = 1'b0;
  assign in_req[2].aw.id = rx_cq_awid;
  assign in_req[2].aw.addr = rx_cq_awaddr;
  assign in_req[2].aw.len = rx_cq_awlen;
  assign in_req[2].aw.size = rx_cq_awsize;
  assign in_req[2].aw.burst = rx_cq_awburst;
  assign in_req[2].aw.lock = rx_cq_awlock;
  assign in_req[2].aw.cache = rx_cq_awcache;
  assign in_req[2].aw.prot = rx_cq_awprot;
  assign in_req[2].aw_valid = rx_cq_awvalid;
  assign rx_cq_awready = in_rsp[2].aw_ready;
  assign in_req[2].w.data = rx_cq_wdata;
  assign in_req[2].w.strb = rx_cq_wstrb;
  assign in_req[2].w.last = rx_cq_wlast;
  assign in_req[2].w_valid = rx_cq_wvalid;
  assign rx_cq_wready = in_rsp[2].w_ready;
  assign rx_cq_bid = in_rsp[2].b.id;
  assign rx_cq_bresp = in_rsp[2].b.resp;
  assign rx_cq_bvalid = in_rsp[2].b_valid;
  assign in_req[2].b_ready = rx_cq_bready;
  assign in_req[2].aw.qos = '0;
  assign in_req[2].aw.region = '0;
  assign in_req[2].aw.user = '0;
  assign in_req[2].aw.atop = '0;
  assign in_req[2].w.user = '0;

  // AXI source 3: tx_desc (rd).
  assign in_req[3].aw = '0;
  assign in_req[3].aw_valid = 1'b0;
  assign in_req[3].w = '0;
  assign in_req[3].w_valid = 1'b0;
  assign in_req[3].b_ready = 1'b0;
  assign in_req[3].ar.id = tx_desc_arid;
  assign in_req[3].ar.addr = tx_desc_araddr;
  assign in_req[3].ar.len = tx_desc_arlen;
  assign in_req[3].ar.size = tx_desc_arsize;
  assign in_req[3].ar.burst = tx_desc_arburst;
  assign in_req[3].ar.lock = tx_desc_arlock;
  assign in_req[3].ar.cache = tx_desc_arcache;
  assign in_req[3].ar.prot = tx_desc_arprot;
  assign in_req[3].ar_valid = tx_desc_arvalid;
  assign tx_desc_arready = in_rsp[3].ar_ready;
  assign tx_desc_rid = in_rsp[3].r.id;
  assign tx_desc_rdata = in_rsp[3].r.data;
  assign tx_desc_rresp = in_rsp[3].r.resp;
  assign tx_desc_rlast = in_rsp[3].r.last;
  assign tx_desc_rvalid = in_rsp[3].r_valid;
  assign in_req[3].r_ready = tx_desc_rready;
  assign in_req[3].ar.qos = '0;
  assign in_req[3].ar.region = '0;
  assign in_req[3].ar.user = '0;

  // AXI source 4: tx_data (rd).
  assign in_req[4].aw = '0;
  assign in_req[4].aw_valid = 1'b0;
  assign in_req[4].w = '0;
  assign in_req[4].w_valid = 1'b0;
  assign in_req[4].b_ready = 1'b0;
  assign in_req[4].ar.id = tx_data_arid;
  assign in_req[4].ar.addr = tx_data_araddr;
  assign in_req[4].ar.len = tx_data_arlen;
  assign in_req[4].ar.size = tx_data_arsize;
  assign in_req[4].ar.burst = tx_data_arburst;
  assign in_req[4].ar.lock = tx_data_arlock;
  assign in_req[4].ar.cache = tx_data_arcache;
  assign in_req[4].ar.prot = tx_data_arprot;
  assign in_req[4].ar_valid = tx_data_arvalid;
  assign tx_data_arready = in_rsp[4].ar_ready;
  assign tx_data_rid = in_rsp[4].r.id;
  assign tx_data_rdata = in_rsp[4].r.data;
  assign tx_data_rresp = in_rsp[4].r.resp;
  assign tx_data_rlast = in_rsp[4].r.last;
  assign tx_data_rvalid = in_rsp[4].r_valid;
  assign in_req[4].r_ready = tx_data_rready;
  assign in_req[4].ar.qos = '0;
  assign in_req[4].ar.region = '0;
  assign in_req[4].ar.user = '0;

  // AXI source 5: tx_cq (wr).
  assign in_req[5].ar = '0;
  assign in_req[5].ar_valid = 1'b0;
  assign in_req[5].r_ready = 1'b0;
  assign in_req[5].aw.id = tx_cq_awid;
  assign in_req[5].aw.addr = tx_cq_awaddr;
  assign in_req[5].aw.len = tx_cq_awlen;
  assign in_req[5].aw.size = tx_cq_awsize;
  assign in_req[5].aw.burst = tx_cq_awburst;
  assign in_req[5].aw.lock = tx_cq_awlock;
  assign in_req[5].aw.cache = tx_cq_awcache;
  assign in_req[5].aw.prot = tx_cq_awprot;
  assign in_req[5].aw_valid = tx_cq_awvalid;
  assign tx_cq_awready = in_rsp[5].aw_ready;
  assign in_req[5].w.data = tx_cq_wdata;
  assign in_req[5].w.strb = tx_cq_wstrb;
  assign in_req[5].w.last = tx_cq_wlast;
  assign in_req[5].w_valid = tx_cq_wvalid;
  assign tx_cq_wready = in_rsp[5].w_ready;
  assign tx_cq_bid = in_rsp[5].b.id;
  assign tx_cq_bresp = in_rsp[5].b.resp;
  assign tx_cq_bvalid = in_rsp[5].b_valid;
  assign in_req[5].b_ready = tx_cq_bready;
  assign in_req[5].aw.qos = '0;
  assign in_req[5].aw.region = '0;
  assign in_req[5].aw.user = '0;
  assign in_req[5].aw.atop = '0;
  assign in_req[5].w.user = '0;

  axi_mux #(
    .SlvAxiIDWidth(1),
    .slv_aw_chan_t(eth1_aw_chan_t),.mst_aw_chan_t(eth4_aw_chan_t),
    .w_chan_t(eth1_w_chan_t),
    .slv_b_chan_t(eth1_b_chan_t),.mst_b_chan_t(eth4_b_chan_t),
    .slv_ar_chan_t(eth1_ar_chan_t),.mst_ar_chan_t(eth4_ar_chan_t),
    .slv_r_chan_t(eth1_r_chan_t),.mst_r_chan_t(eth4_r_chan_t),
    .slv_req_t(eth1_req_t),.slv_resp_t(eth1_resp_t),
    .mst_req_t(eth4_req_t),.mst_resp_t(eth4_resp_t),
    .NoSlvPorts(6),.MaxWTrans(2)
  ) u_axi_mux (
    .clk_i(logic_clk),.rst_ni(~logic_rst),
    .slv_reqs_i(in_req),.slv_resps_o(in_rsp),
    .mst_req_o(out_req),.mst_resp_i(out_rsp)
  );
  assign axi_awid = out_req.aw.id;
  assign axi_awaddr = out_req.aw.addr;
  assign axi_awlen = out_req.aw.len;
  assign axi_awsize = out_req.aw.size;
  assign axi_awburst = out_req.aw.burst;
  assign axi_awlock = out_req.aw.lock;
  assign axi_awcache = out_req.aw.cache;
  assign axi_awprot = out_req.aw.prot;
  assign axi_awvalid = out_req.aw_valid;
  assign out_rsp.aw_ready = axi_awready;
  assign axi_wdata = out_req.w.data;
  assign axi_wstrb = out_req.w.strb;
  assign axi_wlast = out_req.w.last;
  assign axi_wvalid = out_req.w_valid;
  assign out_rsp.w_ready = axi_wready;
  assign out_rsp.b.id = axi_bid;
  assign out_rsp.b.resp = axi_bresp;
  assign out_rsp.b_valid = axi_bvalid;
  assign axi_bready = out_req.b_ready;
  assign axi_arid = out_req.ar.id;
  assign axi_araddr = out_req.ar.addr;
  assign axi_arlen = out_req.ar.len;
  assign axi_arsize = out_req.ar.size;
  assign axi_arburst = out_req.ar.burst;
  assign axi_arlock = out_req.ar.lock;
  assign axi_arcache = out_req.ar.cache;
  assign axi_arprot = out_req.ar.prot;
  assign axi_arvalid = out_req.ar_valid;
  assign out_rsp.ar_ready = axi_arready;
  assign out_rsp.r.id = axi_rid;
  assign out_rsp.r.data = axi_rdata;
  assign out_rsp.r.resp = axi_rresp;
  assign out_rsp.r.last = axi_rlast;
  assign out_rsp.r_valid = axi_rvalid;
  assign axi_rready = out_req.r_ready;
  assign out_rsp.b.user = '0;
  assign out_rsp.r.user = '0;
  initial begin
    if($bits(out_req.aw.id)!=4 || $bits(in_req[0].ar.id)!=1)
      $fatal(1,"Ethernet0 AXI mux ID width mismatch");
  end
endmodule
