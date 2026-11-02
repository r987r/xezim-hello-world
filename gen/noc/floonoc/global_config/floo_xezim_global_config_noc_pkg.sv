// Copyright 2026 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51

// AUTOMATICALLY GENERATED! DO NOT EDIT!

`include "axi/typedef.svh"
`include "floo_noc/typedef.svh"

package floo_xezim_global_config_noc_pkg;

  import floo_pkg::*;


  /////////////////////
  //   Address Map   //
  /////////////////////

  typedef enum logic[2:0] {
    Compute0 = 0,
    Compute1 = 1,
    Compute0Regs = 2,
    Compute1Regs = 3,
    Memory0Regs = 4,
    NumEndpoints = 5} ep_id_e;



  typedef enum logic[1:0] {
    Compute0RegsSamIdx = 1,
    Compute1RegsSamIdx = 2,
    Memory0RegsSamIdx = 3} sam_idx_e;



  typedef logic[0:0] rob_idx_t;
typedef logic[0:0] port_id_t;
typedef logic[1:0] x_bits_t;
typedef logic[0:0] y_bits_t;
typedef struct packed {
    x_bits_t x;
    y_bits_t y;
    port_id_t port_id;
} id_t;

typedef logic route_t;


  typedef struct packed {
    id_t idx;
    id_t start_addr;
    id_t end_addr;
  } route_map_rule_t;

  localparam int unsigned SamNumRules = 4;

typedef struct packed {
    id_t idx;
    logic [31:0] start_addr;
    logic [31:0] end_addr;
} sam_rule_t;

localparam sam_rule_t[SamNumRules-1:0] Sam = '{
'{    idx: '{x: 1, y: 1, port_id: 0},
    start_addr: 32'h40030000,
    end_addr: 32'h40031000},// Memory0Regs
'{    idx: '{x: 0, y: 1, port_id: 0},
    start_addr: 32'h40010000,
    end_addr: 32'h40020000},// Compute1Regs
'{    idx: '{x: 2, y: 0, port_id: 0},
    start_addr: 32'h40000000,
    end_addr: 32'h40010000},// Compute0Regs
'{    idx: '{x: 2, y: 0, port_id: 0},
    start_addr: 32'h40020000,
    end_addr: 32'h40021000} // Compute0Regs

};



  localparam route_cfg_t RouteCfg = '{    RouteAlgo: XYRouting,
    UseIdTable: 1'b1,
    XYAddrOffsetX: 31,
    XYAddrOffsetY: 33,
    IdAddrOffset: 0,
    NumSamRules: 4,
    NumRoutes: 0,
    CollectiveCfg: '{    OpCfg: '{    EnNarrowMulticast: 1'b0,
    EnWideMulticast: 1'b0,
    EnLsbAnd: 1'b0,
    EnNarrowSeqReduction: 1'b0,
    EnWideSeqReduction: 1'b0},
    NarrRedCfg: RedDefaultCfg,
    WideRedCfg: RedDefaultCfg}};

  

    typedef logic[31:0] axi_in_addr_t;
typedef logic[31:0] axi_in_data_t;
typedef logic[3:0] axi_in_strb_t;
typedef logic[0:0] axi_in_id_t;
typedef logic[0:0] axi_in_user_t;
`AXI_TYPEDEF_ALL_CT(axi_in,             axi_in_req_t,             axi_in_rsp_t,             axi_in_addr_t,             axi_in_id_t,             axi_in_data_t,             axi_in_strb_t,             axi_in_user_t)


    typedef logic[31:0] axi_out_addr_t;
typedef logic[31:0] axi_out_data_t;
typedef logic[3:0] axi_out_strb_t;
typedef logic[0:0] axi_out_id_t;
typedef logic[0:0] axi_out_user_t;
`AXI_TYPEDEF_ALL_CT(axi_out,             axi_out_req_t,             axi_out_rsp_t,             axi_out_addr_t,             axi_out_id_t,             axi_out_data_t,             axi_out_strb_t,             axi_out_user_t)



  `FLOO_TYPEDEF_HDR_T(hdr_t, id_t, id_t, axi_ch_e, rob_idx_t)
  localparam axi_cfg_t AxiCfg = '{    AddrWidth: 32,
    DataWidth: 32,
    InIdWidth: 1,
    OutIdWidth: 1,
    UserWidth: 1};
`FLOO_TYPEDEF_AXI_CHAN_ALL(axi, req, rsp, axi_in, AxiCfg, hdr_t)

`FLOO_TYPEDEF_AXI_LINK_ALL(req, rsp, req, rsp)


endpackage
