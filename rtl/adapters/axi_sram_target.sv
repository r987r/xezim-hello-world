`timescale 1ns/1ps
// PULP AXI responder + upstream generic SRAM, with a bounded, non-aliasing
// window. Only immutable ROM/flash instances may specify an initialization file.
module axi_sram_target #(
  parameter type req_t = logic,
  parameter type rsp_t = logic,
  parameter int unsigned IdWidth = 5,
  parameter logic [63:0] Base = '0,
  parameter int unsigned Bytes = 16384,
  parameter bit ReadOnly = 0,
  parameter InitFile = ""
) (
  input logic clk_i, rst_ni,
  input req_t req_i,
  output rsp_t rsp_o,
  output logic mon_valid_o, mon_write_o,
  output logic [63:0] mon_addr_o, mon_data_o,
  output logic [7:0] mon_strb_o
);
  localparam int Words = Bytes/8;
  localparam int WordBits = $clog2(Words);
  logic [0:0] request, write_enable, response_valid, error_q;
  logic [0:0][63:0] address, wdata, rdata;
  logic [0:0][7:0] strobe;
  logic [0:0][WordBits-1:0] word_address;
  logic bad;
  assign bad = address[0] < Base || address[0] >= Base + Bytes || (ReadOnly && write_enable[0]);
  assign word_address[0] = WordBits'((address[0] - Base) >> 3);
  axi_to_detailed_mem #(
    .axi_req_t(req_t), .axi_resp_t(rsp_t), .AddrWidth(64), .DataWidth(64),
    .IdWidth(IdWidth), .UserWidth(1), .NumBanks(1), .BufDepth(1)
  ) u_axi (
    .clk_i, .rst_ni, .busy_o(), .axi_req_i(req_i), .axi_resp_o(rsp_o),
    .mem_req_o(request), .mem_gnt_i(1'b1), .mem_addr_o(address),
    .mem_wdata_o(wdata), .mem_strb_o(strobe), .mem_we_o(write_enable),
    .mem_atop_o(), .mem_lock_o(), .mem_id_o(), .mem_user_o(),
    .mem_cache_o(), .mem_prot_o(), .mem_qos_o(), .mem_region_o(),
    .mem_rvalid_i(response_valid), .mem_rdata_i(rdata),
    .mem_err_i(error_q), .mem_exokay_i('0)
  );
  tc_sram #(.NumWords(Words), .DataWidth(64), .NumPorts(1), .Latency(1), .SimInit("none")) u_ram (
    .clk_i, .rst_ni, .req_i(request & {1{!bad}}), .we_i(write_enable),
    .addr_i(word_address), .wdata_i(wdata), .be_i(strobe), .rdata_o(rdata)
  );
  always_ff @(posedge clk_i or negedge rst_ni)
    if (!rst_ni) begin response_valid <= '0; error_q <= '0; end
    else begin response_valid <= request; error_q <= request & {1{bad}}; end
  assign mon_valid_o = rst_ni && request[0] && !bad;
  assign mon_write_o = write_enable[0];
  assign mon_addr_o = address[0];
  assign mon_data_o = wdata[0];
  assign mon_strb_o = strobe[0];
  initial begin
    if (InitFile != "" && !ReadOnly) $fatal(1, "Cold SRAM must not be preloaded");
    if (InitFile != "") $readmemh(InitFile, u_ram.sram);
  end
endmodule
