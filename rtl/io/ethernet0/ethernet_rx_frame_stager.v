// Whole-frame Ethernet ingress staging and non-destructive header tap.
// A real GMII MAC/FCS+CDC must feed this AXIS input. Full-frame upstream
// verilog-axis FIFO holds bytes until policy metadata is accepted.
// V1 parses untagged Ethernet and fixed-IHL IPv4 UDP destination port;
// VLAN, IP options, fragments and checksum validation are later gates.
`timescale 1ns/1ps
`default_nettype none
module ethernet_rx_frame_stager #(
 parameter integer MAX_FRAME_BYTES=1518,
 parameter integer FIFO_DEPTH=2048
)(
 input wire clk,rst,
 input wire [63:0] s_axis_tdata,input wire [7:0] s_axis_tkeep,
 input wire s_axis_tvalid,output wire s_axis_tready,
 input wire s_axis_tlast,s_axis_tuser,
 output wire meta_valid,input wire meta_ready,
 output wire [15:0] meta_length,meta_ethertype,
 output wire meta_is_udp,output wire [15:0] meta_udp_dst_port,
 output wire [63:0] m_axis_tdata,output wire [7:0] m_axis_tkeep,
 output wire m_axis_tvalid,input wire m_axis_tready,
 output wire m_axis_tlast,m_axis_tuser,
 output reg dropped_frame_pulse,
 output wire fifo_overflow
);
 localparam [1:0] CAPTURE=0,COMMIT=1,META=2,FORWARD=3;
 reg [1:0] state=CAPTURE;
 reg [15:0] bytes_seen=0,ethertype=0,udp_port=0;
 reg [7:0] ip_version_ihl=0,ip_protocol=0;
 reg invalid_frame=0;
 wire fifo_ready,fifo_valid,fifo_last,fifo_user;
 wire [63:0] fifo_data;wire [7:0] fifo_keep;
 wire good_frame,bad_frame;
 integer valid_bytes;
 integer k;
 always @* begin
  valid_bytes=0;
  for(integer i=0;i<8;i=i+1)
   if(s_axis_tkeep[i])valid_bytes=valid_bytes+1;
 end
 wire bad_keep=(s_axis_tkeep==0) ||
                ((s_axis_tkeep & (s_axis_tkeep+8'd1))!=0) ||
                (!s_axis_tlast && s_axis_tkeep!=8'hff);
 wire bad_length=(bytes_seen+valid_bytes>MAX_FRAME_BYTES) ||
                 (s_axis_tlast && bytes_seen+valid_bytes<14);
 wire bad_now=s_axis_tuser || bad_keep || bad_length;
 wire fifo_mark_bad=s_axis_tlast && (bad_now || invalid_frame);
 assign s_axis_tready=(state==CAPTURE) && fifo_ready;
 assign meta_valid=state==META;
 assign meta_length=bytes_seen;
 assign meta_ethertype=ethertype;
 assign meta_is_udp=ethertype==16'h0800 &&
                    ip_version_ihl==8'h45 &&
                    ip_protocol==8'd17 && bytes_seen>=42;
 assign meta_udp_dst_port=udp_port;
 assign m_axis_tdata=fifo_data;
 assign m_axis_tkeep=fifo_keep;
 assign m_axis_tvalid=(state==FORWARD) && fifo_valid;
 assign m_axis_tlast=fifo_last;
 assign m_axis_tuser=fifo_user;

 axis_fifo #(
  .DEPTH(FIFO_DEPTH),.DATA_WIDTH(64),.KEEP_ENABLE(1),.KEEP_WIDTH(8),
  .LAST_ENABLE(1),.ID_ENABLE(0),.DEST_ENABLE(0),
  .USER_ENABLE(1),.USER_WIDTH(1),
  .FRAME_FIFO(1),.DROP_OVERSIZE_FRAME(1),
  .DROP_BAD_FRAME(1),.DROP_WHEN_FULL(0)
 ) u_packet_fifo (
  .clk,.rst,
  .s_axis_tdata(s_axis_tdata),.s_axis_tkeep(s_axis_tkeep),
  .s_axis_tvalid(s_axis_tvalid && state==CAPTURE),
  .s_axis_tready(fifo_ready),.s_axis_tlast(s_axis_tlast),
  .s_axis_tid(8'd0),.s_axis_tdest(8'd0),
  .s_axis_tuser(fifo_mark_bad),
  .m_axis_tdata(fifo_data),.m_axis_tkeep(fifo_keep),
  .m_axis_tvalid(fifo_valid),
  .m_axis_tready(m_axis_tready && state==FORWARD),
  .m_axis_tlast(fifo_last),.m_axis_tid(),.m_axis_tdest(),
  .m_axis_tuser(fifo_user),
  .pause_req(1'b0),.pause_ack(),
  .status_depth(),.status_depth_commit(),
  .status_overflow(fifo_overflow),
  .status_bad_frame(bad_frame),.status_good_frame(good_frame)
 );
 always @(posedge clk) begin
  if(rst) begin
   state<=CAPTURE;bytes_seen<=0;ethertype<=0;udp_port<=0;
   ip_version_ihl<=0;ip_protocol<=0;invalid_frame<=0;
   dropped_frame_pulse<=0;
  end else begin
   dropped_frame_pulse<=0;
   case(state)
    CAPTURE: if(s_axis_tvalid && s_axis_tready) begin
     bytes_seen<=bytes_seen+valid_bytes;
     invalid_frame<=invalid_frame || bad_now;
     for(k=0;k<8;k=k+1)if(s_axis_tkeep[k])begin
      case(bytes_seen+k)
       12: ethertype[15:8]<=s_axis_tdata[k*8+:8];
       13: ethertype[7:0]<=s_axis_tdata[k*8+:8];
       14: ip_version_ihl<=s_axis_tdata[k*8+:8];
       23: ip_protocol<=s_axis_tdata[k*8+:8];
       36: udp_port[15:8]<=s_axis_tdata[k*8+:8];
       37: udp_port[7:0]<=s_axis_tdata[k*8+:8];
       default: begin end
      endcase
     end
     if(s_axis_tlast)state<=COMMIT;
    end
    COMMIT: if(good_frame && !bad_frame && !fifo_overflow)
     state<=META;
    else if(bad_frame || fifo_overflow)begin
     dropped_frame_pulse<=1;
     bytes_seen<=0;ethertype<=0;udp_port<=0;
     ip_version_ihl<=0;ip_protocol<=0;invalid_frame<=0;
     state<=CAPTURE;
    end
    META: if(meta_ready)state<=FORWARD;
    FORWARD: if(fifo_valid && m_axis_tready && fifo_last)begin
     bytes_seen<=0;ethertype<=0;udp_port<=0;
     ip_version_ihl<=0;ip_protocol<=0;invalid_frame<=0;
     state<=CAPTURE;
    end
    default:state<=CAPTURE;
   endcase
  end
 end
endmodule
`default_nettype wire
