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
      // Forced full stalls, single-lane stalls, and random backpressure.
      case ((cyc / 11) % 5)
        0: begin tlp_ready=0; dllp_ready=0; end
        1: begin tlp_ready=1; dllp_ready=0; end
        2: begin tlp_ready=0; dllp_ready=1; end
        3: begin tlp_ready=r[0]; dllp_ready=r[3]; end
        default: begin tlp_ready=1; dllp_ready=1; end
      endcase
      if(!s_valid && accepted<N) begin
        if(pending_length==0) begin
          pending_tlp=rand32()[0];
          pending_length=1+int'(rand32()%8);
          packets++;
        end
        s_data=32'hD0000000 | accepted;
        s_user=pending_tlp?2'b10:2'b01;
        s_last=(pending_length==1);
        s_valid=1;
      end
      #1;
      if(s_valid && !s_ready) stalled_input++;
      accepted_this_cycle=(s_valid && s_ready);
      if(accepted_this_cycle) begin
        if(s_user[1]) begin
          tlp_expected_data[tt]=s_data;
          tlp_expected_last[tt]=s_last;
          tt++;
        end else begin
          dllp_expected_data[dt]=s_data;
          dllp_expected_last[dt]=s_last;
          dt++;
        end
        accepted++;
        pending_length--;
        // Change source valid only AFTER the edge that accepts the beat.
      end
      if(tlp_valid && tlp_ready) begin
        if(th>=tt || tlp_data!==tlp_expected_data[th] || tlp_last!==tlp_expected_last[th] || tlp_user!==2'b10)
          $fatal(1,"TLP mismatch seed=%0d cycle=%0d idx=%0d got=%h last=%b expected=%h",seed,cyc,th,tlp_data,tlp_last,tlp_expected_data[th]);
        th++;
        output_count++;
      end
      if(dllp_valid && dllp_ready) begin
        if(dh>=dt || dllp_data!==dllp_expected_data[dh] || dllp_last!==dllp_expected_last[dh] || dllp_user!==2'b01)
          $fatal(1,"DLLP mismatch seed=%0d cycle=%0d idx=%0d got=%h last=%b expected=%h",seed,cyc,dh,dllp_data,dllp_last,dllp_expected_data[dh]);
        dh++;
        output_count++;
      end
      step_clock();
      if(accepted_this_cycle) s_valid=0;
      if(accepted==N && output_count==N) begin
        if(th!=tt||dh!=dt || stalled_input<50 || packets<100)
          $fatal(1,"incomplete coverage accept=%0d out=%0d stalls=%0d packets=%0d",accepted,output_count,stalled_input,packets);
        $display("PASS: AXIS_DEMUX_RANDOM_BACKPRESSURE seed=%0d beats=%0d packets=%0d stalls=%0d tlp=%0d dllp=%0d",seed,accepted,packets,stalled_input,tt,dt);
        $finish;
      end
    end
    $fatal(1,"timeout seed=%0d accepted=%0d delivered=%0d tlp=%0d/%0d dllp=%0d/%0d",seed,accepted,output_count,th,tt,dh,dt);
  end
endmodule
