// Opt-in DDR-B memory0 attachment: real pinned LiteDRAM RTL + modeled DFI PHY.
// Reuses the existing DDR 64->25-bit bounded AXI bridge and Config NoC WB bridge.
// This is NOT the normal fast AXI RAM target; no fake memory or controller status.
module ddr_litedram_fullchip_target #(
  parameter type data_req_t = logic,
  parameter type data_rsp_t = logic,
  parameter type cfg_req_t  = logic,
  parameter type cfg_rsp_t  = logic,
  parameter int unsigned WB_ADR_BITS = 30,
  parameter logic [31:0] WB_BASE = 32'h0
) (
  input logic clk_i, rst_ni,
  input data_req_t data_req_i,
  output data_rsp_t data_rsp_o,
  input cfg_req_t cfg_req_i,
  output cfg_rsp_t cfg_rsp_o,
  output logic ddr_init_done_o, ddr_init_error_o
);
  logic ddr_user_clk, ddr_user_rst;
  logic wb_ctrl_cyc, wb_ctrl_stb, wb_ctrl_we, wb_ctrl_ack, wb_ctrl_err;
  logic [WB_ADR_BITS-1:0] wb_ctrl_adr;
  logic [31:0] wb_ctrl_dat_w, wb_ctrl_dat_r;
  logic [3:0] wb_ctrl_sel;
  logic [2:0] wb_ctrl_cti;
  logic [1:0] wb_ctrl_bte;
  logic [3:0] m_awid,m_bid,m_arid,m_rid;
  logic [24:0] m_awaddr,m_araddr;
  logic [7:0] m_awlen,m_arlen,m_wstrb;
  logic [2:0] m_awsize,m_arsize;
  logic [1:0] m_awburst,m_arburst;
  logic [63:0] m_wdata,m_rdata;
  logic [1:0] m_bresp,m_rresp;
  logic m_awvalid,m_awready,m_wvalid,m_wready,m_wlast;
  logic m_bvalid,m_bready,m_arvalid,m_arready,m_rvalid,m_rready,m_rlast;
  logic [63:0] unused_user_flags;
  // Data crossbar targets have local AXI ID width 4; reject reconfiguration.
  initial begin
    assert ($bits(data_req_i.aw.id) == 4 && $bits(data_req_i.aw.addr) == 64)
      else $fatal(1, "DDR Data NoC AXI width mismatch");
    assert ($bits(cfg_req_i.aw.addr) == 32 && $bits(cfg_req_i.aw.id) == 1)
      else $fatal(1, "DDR Config NoC AXI width mismatch");
  end
  ddr_litedram_axi_bridge #(.LOCAL_ADDR_WIDTH(25)) u_ddr_axi_bridge (
    .clk_i(clk_i), .rst_ni(rst_ni),
    .controller_ready_i(ddr_init_done_o && !ddr_init_error_o && !ddr_user_rst),
    .s_awid(data_req_i.aw.id),
    .s_awaddr(data_req_i.aw.addr),
    .s_awlen(data_req_i.aw.len),
    .s_awsize(data_req_i.aw.size),
    .s_awburst(data_req_i.aw.burst),
    .s_awatop(data_req_i.aw.atop),
    .s_awvalid(data_req_i.aw_valid),
    .s_awready(data_rsp_o.aw_ready),
    .s_wdata(data_req_i.w.data),
    .s_wstrb(data_req_i.w.strb),
    .s_wlast(data_req_i.w.last),
    .s_wvalid(data_req_i.w_valid),
    .s_wready(data_rsp_o.w_ready),
    .s_bid(data_rsp_o.b.id),
    .s_bresp(data_rsp_o.b.resp),
    .s_bvalid(data_rsp_o.b_valid),
    .s_bready(data_req_i.b_ready),
    .s_arid(data_req_i.ar.id),
    .s_araddr(data_req_i.ar.addr),
    .s_arlen(data_req_i.ar.len),
    .s_arsize(data_req_i.ar.size),
    .s_arburst(data_req_i.ar.burst),
    .s_arvalid(data_req_i.ar_valid),
    .s_arready(data_rsp_o.ar_ready),
    .s_rid(data_rsp_o.r.id),
    .s_rdata(data_rsp_o.r.data),
    .s_rresp(data_rsp_o.r.resp),
    .s_rlast(data_rsp_o.r.last),
    .s_rvalid(data_rsp_o.r_valid),
    .s_rready(data_req_i.r_ready),
    .m_awid(m_awid),
    .m_awaddr(m_awaddr),
    .m_awlen(m_awlen),
    .m_awsize(m_awsize),
    .m_awburst(m_awburst),
    .m_awvalid(m_awvalid),
    .m_awready(m_awready),
    .m_wdata(m_wdata),
    .m_wstrb(m_wstrb),
    .m_wlast(m_wlast),
    .m_wvalid(m_wvalid),
    .m_wready(m_wready),
    .m_bid(m_bid),
    .m_bresp(m_bresp),
    .m_bvalid(m_bvalid),
    .m_bready(m_bready),
    .m_arid(m_arid),
    .m_araddr(m_araddr),
    .m_arlen(m_arlen),
    .m_arsize(m_arsize),
    .m_arburst(m_arburst),
    .m_arvalid(m_arvalid),
    .m_arready(m_arready),
    .m_rid(m_rid),
    .m_rdata(m_rdata),
    .m_rresp(m_rresp),
    .m_rlast(m_rlast),
    .m_rvalid(m_rvalid),
    .m_rready(m_rready)
  );
  always_comb begin
    data_rsp_o.b.user = '0;
    data_rsp_o.r.user = '0;
    cfg_rsp_o.b.user = '0;
    cfg_rsp_o.r.user = '0;
  end
  ddr_litedram_axi_wishbone_bridge #(
    .WB_ADR_BITS(WB_ADR_BITS), .CFG_BASE(32'h4003_0000),
    .CFG_BYTES(32'h0000_4000), .WB_BASE(WB_BASE)
  ) u_config_bridge (
    .clk_i(clk_i), .rst_ni(rst_ni),
    .s_awid(cfg_req_i.aw.id),
    .s_awaddr(cfg_req_i.aw.addr),
    .s_awlen(cfg_req_i.aw.len),
    .s_awsize(cfg_req_i.aw.size),
    .s_awburst(cfg_req_i.aw.burst),
    .s_awvalid(cfg_req_i.aw_valid),
    .s_awready(cfg_rsp_o.aw_ready),
    .s_wdata(cfg_req_i.w.data),
    .s_wstrb(cfg_req_i.w.strb),
    .s_wlast(cfg_req_i.w.last),
    .s_wvalid(cfg_req_i.w_valid),
    .s_wready(cfg_rsp_o.w_ready),
    .s_bid(cfg_rsp_o.b.id),
    .s_bresp(cfg_rsp_o.b.resp),
    .s_bvalid(cfg_rsp_o.b_valid),
    .s_bready(cfg_req_i.b_ready),
    .s_arid(cfg_req_i.ar.id),
    .s_araddr(cfg_req_i.ar.addr),
    .s_arlen(cfg_req_i.ar.len),
    .s_arsize(cfg_req_i.ar.size),
    .s_arburst(cfg_req_i.ar.burst),
    .s_arvalid(cfg_req_i.ar_valid),
    .s_arready(cfg_rsp_o.ar_ready),
    .s_rid(cfg_rsp_o.r.id),
    .s_rdata(cfg_rsp_o.r.data),
    .s_rresp(cfg_rsp_o.r.resp),
    .s_rlast(cfg_rsp_o.r.last),
    .s_rvalid(cfg_rsp_o.r_valid),
    .s_rready(cfg_req_i.r_ready),
    .wb_ctrl_cyc(wb_ctrl_cyc),
    .wb_ctrl_stb(wb_ctrl_stb),
    .wb_ctrl_we(wb_ctrl_we),
    .wb_ctrl_ack(wb_ctrl_ack),
    .wb_ctrl_adr(wb_ctrl_adr),
    .wb_ctrl_dat_w(wb_ctrl_dat_w),
    .wb_ctrl_dat_r(wb_ctrl_dat_r),
    .wb_ctrl_sel(wb_ctrl_sel),
    .wb_ctrl_cti(wb_ctrl_cti),
    .wb_ctrl_bte(wb_ctrl_bte),
    .wb_ctrl_err(wb_ctrl_err)
  );
  soc_ddr4_sim u_controller (
    .clk(clk_i), .init_done(ddr_init_done_o), .init_error(ddr_init_error_o),
    .user_clk(ddr_user_clk), .user_rst(ddr_user_rst),
    .wb_ctrl_cyc(wb_ctrl_cyc),
    .wb_ctrl_stb(wb_ctrl_stb),
    .wb_ctrl_we(wb_ctrl_we),
    .wb_ctrl_ack(wb_ctrl_ack),
    .wb_ctrl_adr(wb_ctrl_adr),
    .wb_ctrl_dat_w(wb_ctrl_dat_w),
    .wb_ctrl_dat_r(wb_ctrl_dat_r),
    .wb_ctrl_sel(wb_ctrl_sel),
    .wb_ctrl_cti(wb_ctrl_cti),
    .wb_ctrl_bte(wb_ctrl_bte),
    .wb_ctrl_err(wb_ctrl_err),
    .user_port_axi_0_awid(m_awid),
    .user_port_axi_0_awaddr(m_awaddr),
    .user_port_axi_0_awlen(m_awlen),
    .user_port_axi_0_awsize(m_awsize),
    .user_port_axi_0_awburst(m_awburst),
    .user_port_axi_0_awvalid(m_awvalid),
    .user_port_axi_0_awready(m_awready),
    .user_port_axi_0_wdata(m_wdata),
    .user_port_axi_0_wstrb(m_wstrb),
    .user_port_axi_0_wlast(m_wlast),
    .user_port_axi_0_wvalid(m_wvalid),
    .user_port_axi_0_wready(m_wready),
    .user_port_axi_0_bid(m_bid),
    .user_port_axi_0_bresp(m_bresp),
    .user_port_axi_0_bvalid(m_bvalid),
    .user_port_axi_0_bready(m_bready),
    .user_port_axi_0_arid(m_arid),
    .user_port_axi_0_araddr(m_araddr),
    .user_port_axi_0_arlen(m_arlen),
    .user_port_axi_0_arsize(m_arsize),
    .user_port_axi_0_arburst(m_arburst),
    .user_port_axi_0_arvalid(m_arvalid),
    .user_port_axi_0_arready(m_arready),
    .user_port_axi_0_rid(m_rid),
    .user_port_axi_0_rdata(m_rdata),
    .user_port_axi_0_rresp(m_rresp),
    .user_port_axi_0_rlast(m_rlast),
    .user_port_axi_0_rvalid(m_rvalid),
    .user_port_axi_0_rready(m_rready)
  );
endmodule
