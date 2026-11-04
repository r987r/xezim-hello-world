`include "axi/typedef.svh"
// Only address classification/type wiring here. PULP modules own protocol
// demultiplexing, AXI-Lite conversion and byte-lane/data-width conversion.
module cpu_noc_adapter #(
  parameter type data_req_t = logic,
  parameter type data_rsp_t = logic,
  parameter type cfg_req_t = logic,
  parameter type cfg_rsp_t = logic,
  parameter logic [31:0] ConfigBase = 32'h40000000,
  parameter logic [31:0] ConfigEnd = 32'h40031000
) (
  input logic clk_i, rst_ni,
  input chip_types_pkg::lite_req_t cpu_req_i,
  output chip_types_pkg::lite_resp_t cpu_rsp_o,
  output data_req_t data_req_o,
  input data_rsp_t data_rsp_i,
  output cfg_req_t cfg_req_o,
  input cfg_rsp_t cfg_rsp_i
);
  import chip_types_pkg::*;
  lite_req_t [1:0] split_req;
  lite_resp_t [1:0] split_rsp;
  // AXI-Lite->AXI extends the 32-bit address into narrow's 64-bit address.
  narrow_req_t narrow_req;
  narrow_resp_t narrow_rsp;
  logic config_aw_select, config_ar_select;
  assign config_aw_select = cpu_req_i.aw.addr >= ConfigBase && cpu_req_i.aw.addr < ConfigEnd;
  assign config_ar_select = cpu_req_i.ar.addr >= ConfigBase && cpu_req_i.ar.addr < ConfigEnd;
  axi_lite_demux #(
    .aw_chan_t(lite_aw_chan_t), .w_chan_t(lite_w_chan_t), .b_chan_t(lite_b_chan_t),
    .ar_chan_t(lite_ar_chan_t), .r_chan_t(lite_r_chan_t),
    .axi_req_t(lite_req_t), .axi_resp_t(lite_resp_t), .NoMstPorts(2), .MaxTrans(1)
  ) u_split (
    .clk_i, .rst_ni, .slv_req_i(cpu_req_i), .slv_resp_o(cpu_rsp_o),
    .slv_aw_select_i(config_aw_select),
    .slv_ar_select_i(config_ar_select),
    .mst_reqs_o(split_req), .mst_resps_i(split_rsp)
  );
  axi_lite_to_axi #(.AxiDataWidth(32), .req_lite_t(lite_req_t), .resp_lite_t(lite_resp_t),
    .axi_req_t(narrow_req_t), .axi_resp_t(narrow_resp_t)) u_data_axi (
    .slv_req_lite_i(split_req[0]), .slv_resp_lite_o(split_rsp[0]),
    .slv_aw_cache_i('0), .slv_ar_cache_i('0), .mst_req_o(narrow_req), .mst_resp_i(narrow_rsp)
  );
  // Request/response typedefs infer the wide channels without a second bus model.
  typedef logic [63:0] wide_data_t;
  typedef logic [7:0] wide_strb_t;
  `AXI_TYPEDEF_W_CHAN_T(wide_w_t, wide_data_t, wide_strb_t, user_t)
  `AXI_TYPEDEF_R_CHAN_T(wide_r_t, wide_data_t, data_id_t, user_t)
  axi_dw_converter #(
    .AxiMaxReads(1), .AxiSlvPortDataWidth(32), .AxiMstPortDataWidth(64),
    .AxiAddrWidth(64), .AxiIdWidth(4),
    .aw_chan_t(narrow_aw_chan_t), .ar_chan_t(narrow_ar_chan_t), .b_chan_t(narrow_b_chan_t),
    .slv_w_chan_t(narrow_w_chan_t), .slv_r_chan_t(narrow_r_chan_t),
    .mst_w_chan_t(wide_w_t), .mst_r_chan_t(wide_r_t),
    .axi_slv_req_t(narrow_req_t), .axi_slv_resp_t(narrow_resp_t),
    .axi_mst_req_t(data_req_t), .axi_mst_resp_t(data_rsp_t)
  ) u_width (.clk_i, .rst_ni, .slv_req_i(narrow_req), .slv_resp_o(narrow_rsp),
            .mst_req_o(data_req_o), .mst_resp_i(data_rsp_i));
  axi_lite_to_axi #(.AxiDataWidth(32), .req_lite_t(lite_req_t), .resp_lite_t(lite_resp_t),
    .axi_req_t(cfg_req_t), .axi_resp_t(cfg_rsp_t)) u_config_axi (
    .slv_req_lite_i(split_req[1]), .slv_resp_lite_o(split_rsp[1]),
    .slv_aw_cache_i('0), .slv_ar_cache_i('0), .mst_req_o(cfg_req_o), .mst_resp_i(cfg_rsp_i)
  );
endmodule
