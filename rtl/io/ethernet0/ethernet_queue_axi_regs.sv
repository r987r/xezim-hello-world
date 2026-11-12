`timescale 1ns/1ps
// Real Ethernet0 queue CSR frontdoor on independent 32-bit Config NoC.
// PULP axi_to_axi_lite performs AXI4/AXI4-Lite conversion. This target
// only serializes independent AW/W and AR handshakes into the queue's
// one-cycle register API; no custom interconnect or software proxy.
// All addresses are checked against physical base, preventing CSR aliases.
module ethernet_queue_axi_regs #(
  parameter type axi_req_t = logic,
  parameter type axi_rsp_t = logic,
  parameter type lite_req_t = logic,
  parameter type lite_rsp_t = logic,
  parameter int unsigned AxiIdWidth = 1,
  parameter logic [31:0] CsrBase = 32'h40050000
) (
  input logic clk_i,rst_ni,
  input axi_req_t cfg_req_i,
  output axi_rsp_t cfg_rsp_o,
  output logic queue_valid_o,queue_write_o,
  output logic [7:0] queue_addr_o,
  output logic [31:0] queue_wdata_o,
  output logic [3:0] queue_wstrb_o,
  input logic queue_ready_i,
  input logic [31:0] queue_rdata_i,
  input logic queue_error_i
);
  lite_req_t lite_req;
  lite_rsp_t lite_rsp;
  axi_to_axi_lite #(
    .AxiAddrWidth(32),.AxiDataWidth(32),.AxiIdWidth(AxiIdWidth),
    .AxiUserWidth(1),.AxiMaxWriteTxns(2),.AxiMaxReadTxns(2),
    .full_req_t(axi_req_t),.full_resp_t(axi_rsp_t),
    .lite_req_t(lite_req_t),.lite_resp_t(lite_rsp_t)
  ) u_axi4_to_lite (
    .clk_i,.rst_ni,.slv_req_i(cfg_req_i),.slv_resp_o(cfg_rsp_o),
    .mst_req_o(lite_req),.mst_resp_i(lite_rsp)
  );

  logic aw_waiting,w_waiting,bvalid_q,rvalid_q;
  logic [31:0] aw_address_q,w_data_q,rdata_q;
  logic [3:0] w_strb_q;
  logic [1:0] bresp_q,rresp_q;
  logic write_fire,read_fire,aw_in_window,ar_in_window;
  logic [31:0] aw_offset,ar_offset;
  assign aw_offset = aw_address_q-CsrBase;
  assign ar_offset = lite_req.ar.addr-CsrBase;
  // Only the first 256 bytes have defined queue registers (up to 0xa0).
  // The reserved full 64-KiB config window must never alias valid CSRs.
  assign aw_in_window = aw_address_q>=CsrBase &&
                        aw_offset<32'h100 &&
                        aw_address_q[1:0]==0;
  assign ar_in_window = lite_req.ar.addr>=CsrBase &&
                        ar_offset<32'h100 &&
                        lite_req.ar.addr[1:0]==0;
  assign lite_rsp.aw_ready = rst_ni && !aw_waiting && !bvalid_q;
  assign lite_rsp.w_ready = rst_ni && !w_waiting && !bvalid_q;
  assign write_fire = aw_waiting && w_waiting && !bvalid_q &&
                      queue_ready_i;
  assign lite_rsp.b_valid = bvalid_q;
  assign lite_rsp.b.resp = bresp_q;
  assign lite_rsp.ar_ready = rst_ni && !rvalid_q && !aw_waiting &&
                             !w_waiting && !bvalid_q && queue_ready_i;
  assign read_fire = lite_req.ar_valid && lite_rsp.ar_ready;
  assign lite_rsp.r_valid = rvalid_q;
  assign lite_rsp.r.data = rdata_q;
  assign lite_rsp.r.resp = rresp_q;

  assign queue_valid_o = (write_fire && aw_in_window) ||
                         (read_fire && ar_in_window);
  assign queue_write_o = write_fire;
  assign queue_addr_o = write_fire ? aw_offset[7:0] : ar_offset[7:0];
  assign queue_wdata_o = w_data_q;
  assign queue_wstrb_o = w_strb_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni)begin
      aw_waiting<=0;w_waiting<=0;
      aw_address_q<=0;w_data_q<=0;w_strb_q<=0;
      bvalid_q<=0;rvalid_q<=0;
      bresp_q<=0;rresp_q<=0;rdata_q<=0;
    end else begin
      if(lite_req.aw_valid && lite_rsp.aw_ready)begin
        aw_address_q<=lite_req.aw.addr;
        aw_waiting<=1;
      end
      if(lite_req.w_valid && lite_rsp.w_ready)begin
        w_data_q<=lite_req.w.data;
        w_strb_q<=lite_req.w.strb;
        w_waiting<=1;
      end
      if(write_fire)begin
        bvalid_q<=1;
        bresp_q<=!aw_in_window?2'b11:
                 queue_error_i?2'b10:2'b00;
        aw_waiting<=0;w_waiting<=0;
      end
      if(bvalid_q && lite_req.b_ready)bvalid_q<=0;
      if(read_fire)begin
        rvalid_q<=1;
        rresp_q<=!ar_in_window?2'b11:
                 queue_error_i?2'b10:2'b00;
        rdata_q<=ar_in_window?queue_rdata_i:32'd0;
      end
      if(rvalid_q && lite_req.r_ready)rvalid_q<=0;
    end
  end
endmodule
