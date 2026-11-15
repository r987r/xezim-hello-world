`timescale 1ns/1ps
module axis_demux_backpressure_tb;
  import pcie_datalink_pkg::*;
  localparam int N = 1600;
  logic clk=0, rst=1;
  logic [31:0] s_data=0;
  logic [3:0] s_keep='1;
  logic s_valid=0, s_last=0, s_ready;
  logic [1:0] s_user=0;
  logic [31:0] tlp_data, dllp_data;
  logic [3:0] tlp_keep, dllp_keep;
  logic [1:0] tlp_user, dllp_user;
  logic tlp_valid, dllp_valid, tlp_last, dllp_last;
  logic tlp_ready=0, dllp_ready=0;
  logic first_tlp_valid;
  axis_user_demux #(.DATA_WIDTH(32), .USER_WIDTH(2)) dut (
    .clk_i(clk), .rst_i(rst), .link_status_i(DL_ACTIVE),
    .first_tlp_valid_o(first_tlp_valid),
    .s_axis_tdata(s_data),.s_axis_tkeep(s_keep),.s_axis_tvalid(s_valid),
    .s_axis_tlast(s_last),.s_axis_tuser(s_user),.s_axis_tready(s_ready),
    .m_tlp_axis_tdata(tlp_data),.m_tlp_axis_tkeep(tlp_keep),
    .m_tlp_axis_tvalid(tlp_valid),.m_tlp_axis_tlast(tlp_last),
    .m_tlp_axis_tuser(tlp_user),.m_tlp_axis_tready(tlp_ready),
    .m_dllp_axis_tdata(dllp_data),.m_dllp_axis_tkeep(dllp_keep),
    .m_dllp_axis_tvalid(dllp_valid),.m_dllp_axis_tlast(dllp_last),
    .m_dllp_axis_tuser(dllp_user),.m_dllp_axis_tready(dllp_ready)
  );
  logic [31:0] tlp_expected_data [0:N-1],dllp_expected_data[0:N-1];
  logic tlp_expected_last [0:N-1],dllp_expected_last[0:N-1];
  int th=0,tt=0,dh=0,dt=0;
  int accepted=0, output_count=0, packets=0, stalled_input=0;
  logic accepted_this_cycle=0;
  int pending_length=0;
  logic pending_tlp=0;
  int unsigned rng=32'h65abc123;
  int unsigned seed;
  function automatic int unsigned rand32();
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
  endfunction
  task automatic step_clock;
    #3; clk=1;
    #3; clk=0;
    #3;
  endtask
  initial begin : run
    if (!$value$plusargs("SEED=%d",seed)) seed=$urandom;
    rng=seed==0?32'h11223344:seed;
    $display("AXIS_DEMUX_SEED=%0d",seed);
    repeat(5) step_clock();
    rst=0;
    for(int cyc=0;cyc<30000;cyc++) begin
      int unsigned r;
      r=rand32();
 ...[truncated]