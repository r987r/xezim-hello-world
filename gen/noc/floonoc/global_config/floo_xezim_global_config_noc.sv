// Copyright 2026 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51

// AUTOMATICALLY GENERATED! DO NOT EDIT!

module floo_xezim_global_config_noc
  import floo_pkg::*;
  import floo_xezim_global_config_noc_pkg::*;
(
  input logic clk_i,
  input logic rst_ni,
  input logic test_enable_i,
  input axi_in_req_t              compute0_axi_in_req_i,
  output axi_in_rsp_t              compute0_axi_in_rsp_o,
  input axi_in_req_t              compute1_axi_in_req_i,
  output axi_in_rsp_t              compute1_axi_in_rsp_o,
  output axi_out_req_t              compute0_regs_axi_out_req_o,
  input axi_out_rsp_t              compute0_regs_axi_out_rsp_i,
  output axi_out_req_t              compute1_regs_axi_out_req_o,
  input axi_out_rsp_t              compute1_regs_axi_out_rsp_i,
  output axi_out_req_t              memory0_regs_axi_out_req_o,
  input axi_out_rsp_t              memory0_regs_axi_out_rsp_i

);
  // Derived from config/interface_contracts.yaml. Upstream chimney RTL unchanged.
  function automatic chimney_cfg_t xezim_chimney_cfg();
    chimney_cfg_t c;
    c = ChimneyDefaultCfg;
    c.MaxTxns = 2;
    c.MaxUniqueIds = 2;
    c.MaxTxnsPerId = 3;
    c.BRoBType = NoRoB;
    c.BRoBSize = 2;
    c.RRoBType = NoRoB;
    c.RRoBSize = 2;
    return c;
  endfunction

  // EnMgrPort=0: upstream NoMgrPortRobType requires NoRoB.
  function automatic chimney_cfg_t xezim_chimney_cfg_no_mgr();
    chimney_cfg_t c;
    c = xezim_chimney_cfg();
    c.BRoBType = NoRoB;
    c.RRoBType = NoRoB;
    return c;
  endfunction


floo_req_t router_0_0_to_router_0_1_req;
floo_rsp_t router_0_1_to_router_0_0_rsp;

floo_req_t router_0_0_to_router_1_0_req;
floo_rsp_t router_1_0_to_router_0_0_rsp;

floo_req_t router_0_0_to_compute0_ni_req;
floo_rsp_t compute0_ni_to_router_0_0_rsp;

floo_req_t router_0_1_to_router_0_0_req;
floo_rsp_t router_0_0_to_router_0_1_rsp;

floo_req_t router_0_1_to_router_1_1_req;
floo_rsp_t router_1_1_to_router_0_1_rsp;

floo_req_t router_0_1_to_compute1_regs_ni_req;
floo_rsp_t compute1_regs_ni_to_router_0_1_rsp;

floo_req_t router_1_0_to_router_0_0_req;
floo_rsp_t router_0_0_to_router_1_0_rsp;

floo_req_t router_1_0_to_router_1_1_req;
floo_rsp_t router_1_1_to_router_1_0_rsp;

floo_req_t router_1_0_to_router_2_0_req;
floo_rsp_t router_2_0_to_router_1_0_rsp;

floo_req_t router_1_0_to_compute1_ni_req;
floo_rsp_t compute1_ni_to_router_1_0_rsp;

floo_req_t router_1_1_to_router_0_1_req;
floo_rsp_t router_0_1_to_router_1_1_rsp;

floo_req_t router_1_1_to_router_1_0_req;
floo_rsp_t router_1_0_to_router_1_1_rsp;

floo_req_t router_1_1_to_router_2_1_req;
floo_rsp_t router_2_1_to_router_1_1_rsp;

floo_req_t router_1_1_to_memory0_regs_ni_req;
floo_rsp_t memory0_regs_ni_to_router_1_1_rsp;

floo_req_t router_2_0_to_router_1_0_req;
floo_rsp_t router_1_0_to_router_2_0_rsp;

floo_req_t router_2_0_to_router_2_1_req;
floo_rsp_t router_2_1_to_router_2_0_rsp;

floo_req_t router_2_0_to_compute0_regs_ni_req;
floo_rsp_t compute0_regs_ni_to_router_2_0_rsp;

floo_req_t router_2_1_to_router_1_1_req;
floo_rsp_t router_1_1_to_router_2_1_rsp;

floo_req_t router_2_1_to_router_2_0_req;
floo_rsp_t router_2_0_to_router_2_1_rsp;

floo_req_t compute0_ni_to_router_0_0_req;
floo_rsp_t router_0_0_to_compute0_ni_rsp;

floo_req_t compute1_ni_to_router_1_0_req;
floo_rsp_t router_1_0_to_compute1_ni_rsp;

floo_req_t compute0_regs_ni_to_router_2_0_req;
floo_rsp_t router_2_0_to_compute0_regs_ni_rsp;

floo_req_t compute1_regs_ni_to_router_0_1_req;
floo_rsp_t router_0_1_to_compute1_regs_ni_rsp;

floo_req_t memory0_regs_ni_to_router_1_1_req;
floo_rsp_t router_1_1_to_memory0_regs_ni_rsp;



  localparam id_t COMPUTE0_NI_ID = '{x: 0, y: 0, port_id: 0};

floo_axi_chimney  #(
  .AxiCfg(AxiCfg),
  .AtopSupport(1'b0),
    .MaxAtomicTxns(0),
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
) compute0_ni (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .sram_cfg_i ( '0 ),
  .axi_in_req_i  ( compute0_axi_in_req_i ),
  .axi_in_rsp_o  ( compute0_axi_in_rsp_o ),
  .axi_out_req_o (    ),
  .axi_out_rsp_i ( '0 ),
  .id_i             ( COMPUTE0_NI_ID       ),
  .route_table_i    ( '0                          ),
  .floo_req_o       ( compute0_ni_to_router_0_0_req   ),
  .floo_rsp_i       ( router_0_0_to_compute0_ni_rsp   ),
  .floo_req_i       ( router_0_0_to_compute0_ni_req   ),
  .floo_rsp_o       ( compute0_ni_to_router_0_0_rsp   )
);

  localparam id_t COMPUTE1_NI_ID = '{x: 1, y: 0, port_id: 0};

floo_axi_chimney  #(
  .AxiCfg(AxiCfg),
  .AtopSupport(1'b0),
    .MaxAtomicTxns(0),
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
) compute1_ni (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .sram_cfg_i ( '0 ),
  .axi_in_req_i  ( compute1_axi_in_req_i ),
  .axi_in_rsp_o  ( compute1_axi_in_rsp_o ),
  .axi_out_req_o (    ),
  .axi_out_rsp_i ( '0 ),
  .id_i             ( COMPUTE1_NI_ID       ),
  .route_table_i    ( '0                          ),
  .floo_req_o       ( compute1_ni_to_router_1_0_req   ),
  .floo_rsp_i       ( router_1_0_to_compute1_ni_rsp   ),
  .floo_req_i       ( router_1_0_to_compute1_ni_req   ),
  .floo_rsp_o       ( compute1_ni_to_router_1_0_rsp   )
);

  localparam id_t COMPUTE0_REGS_NI_ID = '{x: 2, y: 0, port_id: 0};

floo_axi_chimney  #(
  .AxiCfg(AxiCfg),
  .AtopSupport(1'b0),
    .MaxAtomicTxns(0),
    .ChimneyCfg(set_ports(xezim_chimney_cfg_no_mgr(), 1'b1, 1'b0)),
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
) compute0_regs_ni (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .sram_cfg_i ( '0 ),
  .axi_in_req_i  ( '0 ),
  .axi_in_rsp_o  (    ),
  .axi_out_req_o ( compute0_regs_axi_out_req_o ),
  .axi_out_rsp_i ( compute0_regs_axi_out_rsp_i ),
  .id_i             ( COMPUTE0_REGS_NI_ID       ),
  .route_table_i    ( '0                          ),
  .floo_req_o       ( compute0_regs_ni_to_router_2_0_req   ),
  .floo_rsp_i       ( router_2_0_to_compute0_regs_ni_rsp   ),
  .floo_req_i       ( router_2_0_to_compute0_regs_ni_req   ),
  .floo_rsp_o       ( compute0_regs_ni_to_router_2_0_rsp   )
);

  localparam id_t COMPUTE1_REGS_NI_ID = '{x: 0, y: 1, port_id: 0};

floo_axi_chimney  #(
  .AxiCfg(AxiCfg),
  .AtopSupport(1'b0),
    .MaxAtomicTxns(0),
    .ChimneyCfg(set_ports(xezim_chimney_cfg_no_mgr(), 1'b1, 1'b0)),
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
) compute1_regs_ni (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .sram_cfg_i ( '0 ),
  .axi_in_req_i  ( '0 ),
  .axi_in_rsp_o  (    ),
  .axi_out_req_o ( compute1_regs_axi_out_req_o ),
  .axi_out_rsp_i ( compute1_regs_axi_out_rsp_i ),
  .id_i             ( COMPUTE1_REGS_NI_ID       ),
  .route_table_i    ( '0                          ),
  .floo_req_o       ( compute1_regs_ni_to_router_0_1_req   ),
  .floo_rsp_i       ( router_0_1_to_compute1_regs_ni_rsp   ),
  .floo_req_i       ( router_0_1_to_compute1_regs_ni_req   ),
  .floo_rsp_o       ( compute1_regs_ni_to_router_0_1_rsp   )
);

  localparam id_t MEMORY0_REGS_NI_ID = '{x: 1, y: 1, port_id: 0};

floo_axi_chimney  #(
  .AxiCfg(AxiCfg),
  .AtopSupport(1'b0),
    .MaxAtomicTxns(0),
    .ChimneyCfg(set_ports(xezim_chimney_cfg_no_mgr(), 1'b1, 1'b0)),
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
) memory0_regs_ni (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .sram_cfg_i ( '0 ),
  .axi_in_req_i  ( '0 ),
  .axi_in_rsp_o  (    ),
  .axi_out_req_o ( memory0_regs_axi_out_req_o ),
  .axi_out_rsp_i ( memory0_regs_axi_out_rsp_i ),
  .id_i             ( MEMORY0_REGS_NI_ID       ),
  .route_table_i    ( '0                          ),
  .floo_req_o       ( memory0_regs_ni_to_router_1_1_req   ),
  .floo_rsp_i       ( router_1_1_to_memory0_regs_ni_rsp   ),
  .floo_req_i       ( router_1_1_to_memory0_regs_ni_req   ),
  .floo_rsp_o       ( memory0_regs_ni_to_router_1_1_rsp   )
);


floo_req_t [4:0] router_0_0_req_in;
floo_rsp_t [4:0] router_0_0_rsp_out;
floo_req_t [4:0] router_0_0_req_out;
floo_rsp_t [4:0] router_0_0_rsp_in;

    assign router_0_0_req_in[0] = router_0_1_to_router_0_0_req;
    assign router_0_0_req_in[1] = router_1_0_to_router_0_0_req;
    assign router_0_0_req_in[2] = '0;
    assign router_0_0_req_in[3] = '0;
    assign router_0_0_req_in[4] = compute0_ni_to_router_0_0_req;

    assign router_0_0_to_router_0_1_rsp = router_0_0_rsp_out[0];
    assign router_0_0_to_router_1_0_rsp = router_0_0_rsp_out[1];
    assign router_0_0_to_compute0_ni_rsp = router_0_0_rsp_out[4];

    assign router_0_0_to_router_0_1_req = router_0_0_req_out[0];
    assign router_0_0_to_router_1_0_req = router_0_0_req_out[1];
    assign router_0_0_to_compute0_ni_req = router_0_0_req_out[4];

    assign router_0_0_rsp_in[0] = router_0_1_to_router_0_0_rsp;
    assign router_0_0_rsp_in[1] = router_1_0_to_router_0_0_rsp;
    assign router_0_0_rsp_in[2] = '0;
    assign router_0_0_rsp_in[3] = '0;
    assign router_0_0_rsp_in[4] = compute0_ni_to_router_0_0_rsp;

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


floo_req_t [4:0] router_0_1_req_in;
floo_rsp_t [4:0] router_0_1_rsp_out;
floo_req_t [4:0] router_0_1_req_out;
floo_rsp_t [4:0] router_0_1_rsp_in;

    assign router_0_1_req_in[0] = '0;
    assign router_0_1_req_in[1] = router_1_1_to_router_0_1_req;
    assign router_0_1_req_in[2] = router_0_0_to_router_0_1_req;
    assign router_0_1_req_in[3] = '0;
    assign router_0_1_req_in[4] = compute1_regs_ni_to_router_0_1_req;

    assign router_0_1_to_router_1_1_rsp = router_0_1_rsp_out[1];
    assign router_0_1_to_router_0_0_rsp = router_0_1_rsp_out[2];
    assign router_0_1_to_compute1_regs_ni_rsp = router_0_1_rsp_out[4];

    assign router_0_1_to_router_1_1_req = router_0_1_req_out[1];
    assign router_0_1_to_router_0_0_req = router_0_1_req_out[2];
    assign router_0_1_to_compute1_regs_ni_req = router_0_1_req_out[4];

    assign router_0_1_rsp_in[0] = '0;
    assign router_0_1_rsp_in[1] = router_1_1_to_router_0_1_rsp;
    assign router_0_1_rsp_in[2] = router_0_0_to_router_0_1_rsp;
    assign router_0_1_rsp_in[3] = '0;
    assign router_0_1_rsp_in[4] = compute1_regs_ni_to_router_0_1_rsp;

  localparam id_t ROUTER_0_1_ID = '{x: 0, y: 1, port_id: 0};

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
) router_0_1 (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .id_i (ROUTER_0_1_ID),
  .id_route_map_i ('0),
  .floo_req_i (router_0_1_req_in),
  .floo_rsp_o (router_0_1_rsp_out),
  .floo_req_o (router_0_1_req_out),
  .floo_rsp_i (router_0_1_rsp_in)
);


floo_req_t [4:0] router_1_0_req_in;
floo_rsp_t [4:0] router_1_0_rsp_out;
floo_req_t [4:0] router_1_0_req_out;
floo_rsp_t [4:0] router_1_0_rsp_in;

    assign router_1_0_req_in[0] = router_1_1_to_router_1_0_req;
    assign router_1_0_req_in[1] = router_2_0_to_router_1_0_req;
    assign router_1_0_req_in[2] = '0;
    assign router_1_0_req_in[3] = router_0_0_to_router_1_0_req;
    assign router_1_0_req_in[4] = compute1_ni_to_router_1_0_req;

    assign router_1_0_to_router_1_1_rsp = router_1_0_rsp_out[0];
    assign router_1_0_to_router_2_0_rsp = router_1_0_rsp_out[1];
    assign router_1_0_to_router_0_0_rsp = router_1_0_rsp_out[3];
    assign router_1_0_to_compute1_ni_rsp = router_1_0_rsp_out[4];

    assign router_1_0_to_router_1_1_req = router_1_0_req_out[0];
    assign router_1_0_to_router_2_0_req = router_1_0_req_out[1];
    assign router_1_0_to_router_0_0_req = router_1_0_req_out[3];
    assign router_1_0_to_compute1_ni_req = router_1_0_req_out[4];

    assign router_1_0_rsp_in[0] = router_1_1_to_router_1_0_rsp;
    assign router_1_0_rsp_in[1] = router_2_0_to_router_1_0_rsp;
    assign router_1_0_rsp_in[2] = '0;
    assign router_1_0_rsp_in[3] = router_0_0_to_router_1_0_rsp;
    assign router_1_0_rsp_in[4] = compute1_ni_to_router_1_0_rsp;

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


floo_req_t [4:0] router_1_1_req_in;
floo_rsp_t [4:0] router_1_1_rsp_out;
floo_req_t [4:0] router_1_1_req_out;
floo_rsp_t [4:0] router_1_1_rsp_in;

    assign router_1_1_req_in[0] = '0;
    assign router_1_1_req_in[1] = router_2_1_to_router_1_1_req;
    assign router_1_1_req_in[2] = router_1_0_to_router_1_1_req;
    assign router_1_1_req_in[3] = router_0_1_to_router_1_1_req;
    assign router_1_1_req_in[4] = memory0_regs_ni_to_router_1_1_req;

    assign router_1_1_to_router_2_1_rsp = router_1_1_rsp_out[1];
    assign router_1_1_to_router_1_0_rsp = router_1_1_rsp_out[2];
    assign router_1_1_to_router_0_1_rsp = router_1_1_rsp_out[3];
    assign router_1_1_to_memory0_regs_ni_rsp = router_1_1_rsp_out[4];

    assign router_1_1_to_router_2_1_req = router_1_1_req_out[1];
    assign router_1_1_to_router_1_0_req = router_1_1_req_out[2];
    assign router_1_1_to_router_0_1_req = router_1_1_req_out[3];
    assign router_1_1_to_memory0_regs_ni_req = router_1_1_req_out[4];

    assign router_1_1_rsp_in[0] = '0;
    assign router_1_1_rsp_in[1] = router_2_1_to_router_1_1_rsp;
    assign router_1_1_rsp_in[2] = router_1_0_to_router_1_1_rsp;
    assign router_1_1_rsp_in[3] = router_0_1_to_router_1_1_rsp;
    assign router_1_1_rsp_in[4] = memory0_regs_ni_to_router_1_1_rsp;

  localparam id_t ROUTER_1_1_ID = '{x: 1, y: 1, port_id: 0};

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
) router_1_1 (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .id_i (ROUTER_1_1_ID),
  .id_route_map_i ('0),
  .floo_req_i (router_1_1_req_in),
  .floo_rsp_o (router_1_1_rsp_out),
  .floo_req_o (router_1_1_req_out),
  .floo_rsp_i (router_1_1_rsp_in)
);


floo_req_t [4:0] router_2_0_req_in;
floo_rsp_t [4:0] router_2_0_rsp_out;
floo_req_t [4:0] router_2_0_req_out;
floo_rsp_t [4:0] router_2_0_rsp_in;

    assign router_2_0_req_in[0] = router_2_1_to_router_2_0_req;
    assign router_2_0_req_in[1] = '0;
    assign router_2_0_req_in[2] = '0;
    assign router_2_0_req_in[3] = router_1_0_to_router_2_0_req;
    assign router_2_0_req_in[4] = compute0_regs_ni_to_router_2_0_req;

    assign router_2_0_to_router_2_1_rsp = router_2_0_rsp_out[0];
    assign router_2_0_to_router_1_0_rsp = router_2_0_rsp_out[3];
    assign router_2_0_to_compute0_regs_ni_rsp = router_2_0_rsp_out[4];

    assign router_2_0_to_router_2_1_req = router_2_0_req_out[0];
    assign router_2_0_to_router_1_0_req = router_2_0_req_out[3];
    assign router_2_0_to_compute0_regs_ni_req = router_2_0_req_out[4];

    assign router_2_0_rsp_in[0] = router_2_1_to_router_2_0_rsp;
    assign router_2_0_rsp_in[1] = '0;
    assign router_2_0_rsp_in[2] = '0;
    assign router_2_0_rsp_in[3] = router_1_0_to_router_2_0_rsp;
    assign router_2_0_rsp_in[4] = compute0_regs_ni_to_router_2_0_rsp;

  localparam id_t ROUTER_2_0_ID = '{x: 2, y: 0, port_id: 0};

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
) router_2_0 (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .id_i (ROUTER_2_0_ID),
  .id_route_map_i ('0),
  .floo_req_i (router_2_0_req_in),
  .floo_rsp_o (router_2_0_rsp_out),
  .floo_req_o (router_2_0_req_out),
  .floo_rsp_i (router_2_0_rsp_in)
);


floo_req_t [4:0] router_2_1_req_in;
floo_rsp_t [4:0] router_2_1_rsp_out;
floo_req_t [4:0] router_2_1_req_out;
floo_rsp_t [4:0] router_2_1_rsp_in;

    assign router_2_1_req_in[0] = '0;
    assign router_2_1_req_in[1] = '0;
    assign router_2_1_req_in[2] = router_2_0_to_router_2_1_req;
    assign router_2_1_req_in[3] = router_1_1_to_router_2_1_req;
    assign router_2_1_req_in[4] = '0;

    assign router_2_1_to_router_2_0_rsp = router_2_1_rsp_out[2];
    assign router_2_1_to_router_1_1_rsp = router_2_1_rsp_out[3];

    assign router_2_1_to_router_2_0_req = router_2_1_req_out[2];
    assign router_2_1_to_router_1_1_req = router_2_1_req_out[3];

    assign router_2_1_rsp_in[0] = '0;
    assign router_2_1_rsp_in[1] = '0;
    assign router_2_1_rsp_in[2] = router_2_0_to_router_2_1_rsp;
    assign router_2_1_rsp_in[3] = router_1_1_to_router_2_1_rsp;
    assign router_2_1_rsp_in[4] = '0;

  localparam id_t ROUTER_2_1_ID = '{x: 2, y: 1, port_id: 0};

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
) router_2_1 (
  .clk_i,
  .rst_ni,
  .test_enable_i,
  .id_i (ROUTER_2_1_ID),
  .id_route_map_i ('0),
  .floo_req_i (router_2_1_req_in),
  .floo_rsp_o (router_2_1_rsp_out),
  .floo_req_o (router_2_1_req_out),
  .floo_rsp_i (router_2_1_rsp_in)
);



endmodule
