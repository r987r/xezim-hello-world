// Actual upstream axis_fifo in frame mode; validated Ethernet0 header tap.
`timescale 1ns/1ps
module ethernet_rx_frame_stager_tb;
reg clk=0;always #5 clk=~clk;
reg rst=1;
reg [63:0] s_axis_tdata=0;reg [7:0] s_axis_tkeep=0;
reg s_axis_tvalid=0,s_axis_tlast=0,s_axis_tuser=0;
wire s_axis_tready;
wire meta_valid;reg meta_ready=0;
wire [15:0] meta_length,meta_ethertype,meta_udp_dst_port;
wire meta_is_udp;
wire [63:0] m_axis_tdata;wire [7:0] m_axis_tkeep;
wire m_axis_tvalid,m_axis_tlast,m_axis_tuser;
reg m_axis_tready=0;
wire dropped_frame_pulse,fifo_overflow;
integer checks=0,drops=0,outputs=0;
ethernet_rx_frame_stager dut(
 .clk,.rst,.s_axis_tdata,.s_axis_tkeep,.s_axis_tvalid,.s_axis_tready,
 .s_axis_tlast,.s_axis_tuser,.meta_valid,.meta_ready,
 .meta_length,.meta_ethertype,.meta_is_udp,.meta_udp_dst_port,
 .m_axis_tdata,.m_axis_tkeep,.m_axis_tvalid,.m_axis_tready,
 .m_axis_tlast,.m_axis_tuser,.dropped_frame_pulse,.fifo_overflow
);
always @(posedge clk)if(!rst && dropped_frame_pulse)drops<=drops+1;
task check(input logic good,input string why);
begin
 if(good!==1'b1)begin $display("FAIL RX stager: %s at %0t",why,$time);$fatal(1);end
 checks=checks+1;
end
endtask
function automatic [7:0] packet_byte(input integer j,input integer seed,
                                     input logic arp);
begin
 packet_byte=(j+seed)&255;
 if(j==12)packet_byte=8'h08;
 if(j==13)packet_byte=arp?8'h06:8'h00;
 if(j==14)packet_byte=8'h45;
 if(j==23)packet_byte=8'd17;
 if(j==36)packet_byte=8'h17;
 if(j==37)packet_byte=8'h70;
end
endfunction
task automatic inject(input integer n,input integer seed,
                      input logic arp,input logic bad,
                      input logic bad_keep);
integer index,b,remaining,cycles;reg accepted;
reg [63:0] beat;reg [7:0] keep;
begin
 for(index=0;index<n;index=index+8)begin
  beat=0;keep=0;remaining=n-index;
  if(remaining>8)remaining=8;
  for(b=0;b<remaining;b=b+1)begin
   beat[b*8+:8]=packet_byte(index+b,seed,arp);keep[b]=1;
  end
  if(bad_keep && index+remaining==n)keep=8'h15;
  @(negedge clk);s_axis_tdata=beat;s_axis_tkeep=keep;
  s_axis_tvalid=1;s_axis_tlast=(index+remaining==n);
  s_axis_tuser=bad && s_axis_tlast;
  cycles=0;accepted=0;
  while(!accepted && cycles<1000)begin
   @(posedge clk);accepted=s_axis_tready;cycles=cycles+1;
  end
  check(accepted,"stage accepted RX beat");
  check(!meta_valid && !m_axis_tvalid,"uncommitted frame never escapes");
 end
 @(negedge clk);s_axis_tvalid=0;s_axis_tlast=0;
 s_axis_tuser=0;s_axis_tkeep=0;
end
endtask
task automatic release_frame(input integer n,input integer seed,
                             input logic arp);
integer cycles,index,b,remaining;reg [7:0] keep;
begin
 cycles=0;
 while(!meta_valid && cycles<1000)begin @(posedge clk);cycles=cycles+1;end
 check(meta_valid,"full-frame ready metadata");
 check(meta_length==n,"exact packet byte length");
 check(meta_ethertype==(arp?16'h0806:16'h0800),"EtherType parsed");
 check(meta_is_udp==!arp,"only IPv4/UDP classified as UDP");
 if(!arp)check(meta_udp_dst_port==6000,"UDP destination port parsed");
 check(!m_axis_tvalid,"no payload before metadata is accepted");
 @(negedge clk);meta_ready=1;
 @(posedge clk);
 @(negedge clk);meta_ready=0;
 index=0;cycles=0;
 while(index<n && cycles<3000)begin
  m_axis_tready=(cycles%3)!=0; // downstream backpressure
  @(posedge clk);
  if(m_axis_tvalid && m_axis_tready)begin
   remaining=n-index;if(remaining>8)remaining=8;
   keep=remaining==8?8'hff:(8'hff>>(8-remaining));
   check(m_axis_tkeep==keep,"AXIS byte mask");
   check(m_axis_tlast==(index+remaining==n),"last exactly once");
   check(!m_axis_tuser,"no upstream error on valid packet");
   for(b=0;b<remaining;b=b+1)
    check(m_axis_tdata[b*8+:8]===packet_byte(index+b,seed,arp),
          "unchanged MAC payload bytes");
   index=index+remaining;
   outputs=outputs+1;
  end
  @(negedge clk);cycles=cycles+1;
 end
 check(index==n,"entire packet delivered");
 m_axis_tready=0;
 repeat(6)@(posedge clk);
 check(!meta_valid && !m_axis_tvalid,"no duplicate buffered packet");
end
endtask
task automatic expect_drop(input integer previous);
integer cycles;
begin
 cycles=0;
 while(drops==previous && cycles<1000)begin @(posedge clk);cycles=cycles+1;end
 check(drops==previous+1,"whole bad/oversize frame dropped");
 check(!meta_valid && !m_axis_tvalid,"bad frame never advertised");
 repeat(8)@(posedge clk);
end
endtask
initial begin #30000000;$fatal(1,"RX frame stager watchdog");end
initial begin
 repeat(8)@(posedge clk);@(negedge clk);rst=0;
 inject(85,7,0,0,0);
 release_frame(85,7,0);
 inject(60,19,1,0,0);
 release_frame(60,19,1);
 inject(128,23,0,1,0);
 expect_drop(0);
 inject(85,37,0,0,1);
 expect_drop(1);
 inject(1600,53,0,0,0);
 expect_drop(2);
 check(!fifo_overflow,"none of these framed inputs exceeded physical FIFO");
 $display("PASS ethernet_rx_frame_stager_tb checks=%0d good_beats=%0d drops=%0d",
          checks,outputs,drops);
 $finish;
end
endmodule
