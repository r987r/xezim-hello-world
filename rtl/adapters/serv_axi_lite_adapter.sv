`timescale 1ns/1ps
// SERV uses classic, single-request Wishbone. ZipCPU's proven pipelined
// bridge owns AXI timing; this latch submits each held classic cycle once.
module serv_axi_lite_adapter (
  input logic clk_i, rst_ni,
  input logic cyc_i, we_i,
  input logic [31:0] addr_i, wdata_i,
  input logic [3:0] strb_i,
  output logic ack_o,
  output logic [31:0] rdata_o,
  output chip_types_pkg::lite_req_t req_o,
  input chip_types_pkg::lite_resp_t rsp_i
);
  logic submitted, stall, error;
  always_ff @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) submitted <= 1'b0;
    else if (!cyc_i) submitted <= 1'b0;
    else if (!submitted && !stall) submitted <= 1'b1;
  wbm2axilite #(.C_AXI_ADDR_WIDTH(32)) u_bridge (
    .i_clk(clk_i), .i_reset(!rst_ni),
    .i_wb_cyc(cyc_i), .i_wb_stb(cyc_i && !submitted), .i_wb_we(we_i),
    .i_wb_addr(addr_i[31:2]), .i_wb_data(wdata_i), .i_wb_sel(strb_i),
    .o_wb_stall(stall), .o_wb_ack(ack_o), .o_wb_data(rdata_o), .o_wb_err(error),
    .o_axi_awvalid(req_o.aw_valid), .i_axi_awready(rsp_i.aw_ready),
    .o_axi_awaddr(req_o.aw.addr), .o_axi_awprot(req_o.aw.prot),
    .o_axi_wvalid(req_o.w_valid), .i_axi_wready(rsp_i.w_ready),
    .o_axi_wdata(req_o.w.data), .o_axi_wstrb(req_o.w.strb),
    .i_axi_bvalid(rsp_i.b_valid), .o_axi_bready(req_o.b_ready), .i_axi_bresp(rsp_i.b.resp),
    .o_axi_arvalid(req_o.ar_valid), .i_axi_arready(rsp_i.ar_ready),
    .o_axi_araddr(req_o.ar.addr), .o_axi_arprot(req_o.ar.prot),
    .i_axi_rvalid(rsp_i.r_valid), .o_axi_rready(req_o.r_ready),
    .i_axi_rdata(rsp_i.r.data), .i_axi_rresp(rsp_i.r.resp)
  );
  always @(posedge clk_i) if (rst_ni && error)
    $fatal(1, "SERV Wishbone-to-AXI-Lite error at %h", addr_i);
endmodule
