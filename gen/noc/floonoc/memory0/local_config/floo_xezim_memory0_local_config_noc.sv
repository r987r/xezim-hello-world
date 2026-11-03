// Copyright 2026 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51

// AUTOMATICALLY GENERATED! DO NOT EDIT!

module floo_xezim_memory0_local_config_noc
  import floo_pkg::*;
  import floo_xezim_memory0_local_config_noc_pkg::*;
(
  input logic clk_i,
  input logic rst_ni,
  input logic test_enable_i,
  input axi_in_req_t              global_in_axi_in_req_i,
  output axi_in_rsp_t              global_in_axi_in_rsp_o,
  output axi_out_req_t              controller_regs_axi_out_req_o,
  input axi_out_rsp_t              controller_regs_axi_out_rsp_i

);
  // Derived from config/interface_contracts.yaml. Upstream chimney RTL unchanged.
  function automatic chimney_cfg_t xezim_chimney_cfg();
    chimney_cfg_t c;
    c = ChimneyDefaultCfg;
    c.MaxTxns = 2;
    c.MaxUniqueIds = 1;
    c.MaxTxnsPerId = 3;
    c.BRoBType = NoRoB;
    c.BRoBSize = 2;
    c.RRoBType = NoRoB;
    c.RRoBSize = 2;
    return c;
  endfunction


floo_req_t router_0_0_to_router_1_0_req;
floo_rsp_t router_1_0_to_router_0_0_rsp;

floo_req_t router_0_0_to_global_in_ni_req;
floo_rsp_t global_in_ni_to_router_0_0_rsp;

floo_req_t router_1_0_to_router_0_0_req;
floo_rsp_t router_0_0_to_router_1_0_rsp;

floo_req_t router_1_0_to_controller_regs_ni_req;
floo_rsp_t controller_regs_ni_to_router_1_0_rsp;

floo_req_t global_in_ni_to_router_0_0_req;
floo_rsp_t router_0_0_to_global_in_ni_rsp;

floo_req_t controller_regs_ni_to_router_1_0_req;
floo_rsp_t router_1_0_to_controller_regs_ni_rsp;



  localparam id_t GLOBAL_IN_NI_ID = '{x: 0, y: 0, port_id: 0};

floo_axi_chimney  #(
  .AxiCfg(AxiCfg),
  .ChimneyCfg(set_ports(xezim_chimney_cfg(), 1'b0, 1'b1)),
  .RouteCfg(RouteCfg),
  .id_t(id_t),
  .rob_idx_t(rob_idx_t),
  .hdr_t  (hdr_t),
  .sam_rule_t(sam_rule_t),
  .Sam(Sam),
  .axi_in_req_t(axi_in_req_t),
  .axi_in_rsp_t(axi_in_rsp_t),
  .axi_out_req_t(axi_out_req_t),
  .axi_out_rsp_t(axi_out_rsp_t),
  .floo_req_t(floo_req_t),
  .floo_rsp_t(floo_rsp_t)
) global_in_ni (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .sram_cfg_i ( '0 ),
  .axi_in_req_i  ( global_in_axi_in_req_i ),
  .axi_in_rsp_o  ( global_in_axi_in_rsp_o ),
  .axi_out_req_o (    ),
  .axi_out_rsp_i ( '0 ),
  .id_i             ( GLOBAL_IN_NI_ID       ),
  .route_table_i    ( '0                          ),
  .floo_req_o       ( global_in_ni_to_router_0_0_req   ),
  .floo_rsp_i       ( router_0_0_to_global_in_ni_rsp   ),
  .floo_req_i       ( router_0_0_to_global_in_ni_req   ),
  .floo_rsp_o       ( global_in_ni_to_router_0_0_rsp   )
);

  localparam id_t CONTROLLER_REGS_NI_ID = '{x: 1, y: 0, port_id: 0};

floo_axi_chimney  #(
  .AxiCfg(AxiCfg),
  .ChimneyCfg(set_ports(xezim_chimney_cfg(), 1'b1, 1'b0)),
  .RouteCfg(RouteCfg),
  .id_t(id_t),
  .rob_idx_t(rob_idx_t),
  .hdr_t  (hdr_t),
  .sam_rule_t(sam_rule_t),
  .Sam(Sam),
  .axi_in_req_t(axi_in_req_t),
  .axi_in_rsp_t(axi_in_rsp_t),
  .axi_out_req_t(axi_out_req_t),
  .axi_out_rsp_t(axi_out_rsp_t),
  .floo_req_t(floo_req_t),
  .floo_rsp_t(floo_rsp_t)
) controller_regs_ni (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .sram_cfg_i ( '0 ),
  .axi_in_req_i  ( '0 ),
  .axi_in_rsp_o  (    ),
  .axi_out_req_o ( controller_regs_axi_out_req_o ),
  .axi_out_rsp_i ( controller_regs_axi_out_rsp_i ),
  .id_i             ( CONTROLLER_REGS_NI_ID       ),
  .route_table_i    ( '0                          ),
  .floo_req_o       ( controller_regs_ni_to_router_1_0_req   ),
  .floo_rsp_i       ( router_1_0_to_controller_regs_ni_rsp   ),
  .floo_req_i       ( router_1_0_to_controller_regs_ni_req   ),
  .floo_rsp_o       ( controller_regs_ni_to_router_1_0_rsp   )
);


floo_req_t [4:0] router_0_0_req_in;
floo_rsp_t [4:0] router_0_0_rsp_out;
floo_req_t [4:0] router_0_0_req_out;
floo_rsp_t [4:0] router_0_0_rsp_in;

    assign router_0_0_req_in[0] = '0;
    assign router_0_0_req_in[1] = router_1_0_to_router_0_0_req;
    assign router_0_0_req_in[2] = '0;
    assign router_0_0_req_in[3] = '0;
    assign router_0_0_req_in[4] = global_in_ni_to_router_0_0_req;

    assign router_0_0_to_router_1_0_rsp = router_0_0_rsp_out[1];
    assign router_0_0_to_global_in_ni_rsp = router_0_0_rsp_out[4];

    assign router_0_0_to_router_1_0_req = router_0_0_req_out[1];
    assign router_0_0_to_global_in_ni_req = router_0_0_req_out[4];

    assign router_0_0_rsp_in[0] = '0;
    assign router_0_0_rsp_in[1] = router_1_0_to_router_0_0_rsp;
    assign router_0_0_rsp_in[2] = '0;
    assign router_0_0_rsp_in[3] = '0;
    assign router_0_0_rsp_in[4] = global_in_ni_to_router_0_0_rsp;

  localparam id_t ROUTER_0_0_ID = '{x: 0, y: 0, port_id: 0};

floo_axi_router #(
  .AxiCfg(AxiCfg),
  .RouteAlgo (XYRouting),
  .NumRoutes (5),
  .NumInputs (5),
  .NumOutputs (5),
  .InFifoDepth (2),
  .OutFifoDepth (2),
  .id_t(id_t),
  .hdr_t(hdr_t),
  .floo_req_t(floo_req_t),
  .floo_rsp_t(floo_rsp_t)
) router_0_0 (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .id_i (ROUTER_0_0_ID),
  .id_route_map_i ('0),
  .floo_req_i (router_0_0_req_in),
  .floo_rsp_o (router_0_0_rsp_out),
  .floo_req_o (router_0_0_req_out),
  .floo_rsp_i (router_0_0_rsp_in)
);


floo_req_t [4:0] router_1_0_req_in;
floo_rsp_t [4:0] router_1_0_rsp_out;
floo_req_t [4:0] router_1_0_req_out;
floo_rsp_t [4:0] router_1_0_rsp_in;

    assign router_1_0_req_in[0] = '0;
    assign router_1_0_req_in[1] = '0;
    assign router_1_0_req_in[2] = '0;
    assign router_1_0_req_in[3] = router_0_0_to_router_1_0_req;
    assign router_1_0_req_in[4] = controller_regs_ni_to_router_1_0_req;

    assign router_1_0_to_router_0_0_rsp = router_1_0_rsp_out[3];
    assign router_1_0_to_controller_regs_ni_rsp = router_1_0_rsp_out[4];

    assign router_1_0_to_router_0_0_req = router_1_0_req_out[3];
    assign router_1_0_to_controller_regs_ni_req = router_1_0_req_out[4];

    assign router_1_0_rsp_in[0] = '0;
    assign router_1_0_rsp_in[1] = '0;
    assign router_1_0_rsp_in[2] = '0;
    assign router_1_0_rsp_in[3] = router_0_0_to_router_1_0_rsp;
    assign router_1_0_rsp_in[4] = controller_regs_ni_to_router_1_0_rsp;

  localparam id_t ROUTER_1_0_ID = '{x: 1, y: 0, port_id: 0};

floo_axi_router #(
  .AxiCfg(AxiCfg),
  .RouteAlgo (XYRouting),
  .NumRoutes (5),
  .NumInputs (5),
  .NumOutputs (5),
  .InFifoDepth (2),
  .OutFifoDepth (2),
  .id_t(id_t),
  .hdr_t(hdr_t),
  .floo_req_t(floo_req_t),
  .floo_rsp_t(floo_rsp_t)
) router_1_0 (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .id_i (ROUTER_1_0_ID),
  .id_route_map_i ('0),
  .floo_req_i (router_1_0_req_in),
  .floo_rsp_o (router_1_0_rsp_out),
  .floo_req_o (router_1_0_req_out),
  .floo_rsp_i (router_1_0_rsp_in)
);



endmodule
