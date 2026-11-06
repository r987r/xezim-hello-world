// Real queue -> AXI ring descriptor -> AXI packet write integration.
// Both SRAM instances are upstream axi_ram RTL, NOT host-only models.
// The frame source is a TEST BFM for already FCS-checked complete frames.
// Real upstream axi_dma_wr CQ adapter writes a 32-byte record after packet B.
// A separate AXI SRAM models the CQ target pending shared-NoC arbitration.
`timescale 1ns/1ps
module ethernet_rx_queue_engine_tb;
reg clk=0; always #5 clk=~clk; reg rst=1;
reg cfg_valid=0,cfg_write=0;
reg [7:0] cfg_addr=0;reg [31:0] cfg_wdata=0;
reg [3:0] cfg_wstrb=4'hf;
wire cfg_ready,cfg_error,irq;wire [31:0] cfg_rdata;
reg frame_valid=0,frame_is_udp=1;
reg [15:0] frame_length=85,frame_ethertype=16'h0800,frame_udp_dst_port=6000;
wire frame_ready,rx_axis_tready;
reg [63:0] rx_axis_tdata=0;reg [7:0] rx_axis_tkeep=0;
reg rx_axis_tvalid=0,rx_axis_tlast=0,rx_axis_tuser=0;
wire write_result_valid,write_result_ok,frame_drop_pulse;
wire [3:0] write_result_error;wire [15:0] write_result_length;
wire [31:0] write_result_cookie;wire [7:0] write_result_tag;
wire [7:0] write_result_policy;
wire [63:0] rx_cq_slot_addr_o,tx_cq_slot_addr_o;
wire cpl_written_i;
wire cq_done_valid, cq_written;
wire [3:0] cq_error;
wire [7:0] cq_done_tag;
integer cq_aw_count=0, cq_b_count=0;

wire [3:0] rd_arid,rd_rid,wr_awid,wr_bid;
wire [63:0] rd_araddr,rd_rdata,wr_awaddr,wr_wdata;
wire [7:0] rd_arlen,wr_awlen,wr_wstrb;
wire [2:0] rd_arsize,wr_awsize;
wire [1:0] rd_arburst,rd_rresp,wr_awburst,wr_bresp;
wire rd_arlock,rd_arvalid,rd_arready,rd_rlast,rd_rvalid,rd_rready;
wire wr_awlock,wr_awvalid,wr_awready,wr_wlast,wr_wvalid,wr_wready,wr_bvalid,wr_bready;
wire [3:0] rd_arcache,wr_awcache;
wire [2:0] rd_arprot,wr_awprot;
wire [3:0] cq_awid,cq_bid,cq_arcache;
wire [63:0] cq_awaddr,cq_wdata;
wire [7:0] cq_awlen,cq_wstrb;
wire [2:0] cq_awsize,cq_arprot;
wire [1:0] cq_awburst,cq_bresp;
wire cq_awlock,cq_awvalid,cq_awready,cq_wlast,cq_wvalid,cq_wready;
wire cq_bvalid,cq_bready;
reg [15:0] cq_check_araddr=0;
reg cq_check_arvalid=0,cq_check_rready=0;
wire cq_check_arready,cq_check_rvalid,cq_check_rlast;
wire [3:0] cq_check_rid;
wire [63:0] cq_check_rdata;
wire [1:0] cq_check_rresp;

ethernet_rx_queue_engine u_eth (
 .clk,.rst,.cfg_valid,.cfg_write,.cfg_addr,.cfg_wdata,.cfg_wstrb,
 .cfg_ready,.cfg_rdata,.cfg_error,
 .tx_desc_ready_i(1'b0),.tx_cpl_written_i(1'b0),
 .tx_desc_valid_o(),.tx_desc_addr_o(),
 .rx_cq_slot_addr_o,.tx_cq_slot_addr_o,
 .frame_valid,.frame_ready,.frame_length,.frame_ethertype,.frame_is_udp,
 .frame_udp_dst_port,.rx_axis_tdata,.rx_axis_tkeep,.rx_axis_tvalid,
 .rx_axis_tready,.rx_axis_tlast,.rx_axis_tuser,
 .write_result_valid,.write_result_ok,.write_result_error,
 .write_result_length,.write_result_cookie,.write_result_policy,.write_result_tag,
 .frame_drop_pulse,.cpl_written_i,.irq,
 .rd_arid,.rd_araddr,.rd_arlen,.rd_arsize,.rd_arburst,.rd_arlock,
 .rd_arcache,.rd_arprot,.rd_arvalid,.rd_arready,.rd_rid,
 .rd_rdata,.rd_rresp,.rd_rlast,.rd_rvalid,.rd_rready,
 .wr_awid,.wr_awaddr,.wr_awlen,.wr_awsize,.wr_awburst,.wr_awlock,
 .wr_awcache,.wr_awprot,.wr_awvalid,.wr_awready,.wr_wdata,
 .wr_wstrb,.wr_wlast,.wr_wvalid,.wr_wready,.wr_bid,.wr_bresp,
 .wr_bvalid,.wr_bready
);

// Synthesizable, real B-gated completion writer rather than a BFM pulse.
// Completion slot comes directly from the queue producer, and the writer's
// cpl_written can advance the queue only after its accepted AXI write B.
ethernet_cq_axi_writer #(
 .REGION_BASE(64'h500),.REGION_BYTES(64'h200)
) u_cq_writer (
 .clk,.rst,
 .req_valid(write_result_valid),.req_ready(),
 .req_addr(rx_cq_slot_addr_o),
 .req_cookie(write_result_cookie),
 .req_length({16'd0,write_result_length}),
 .req_status(write_result_ok ? 32'd0 : {28'd0,write_result_error}),
 .req_policy({24'd0,write_result_policy}),
 .req_queue(32'd0),.req_tag(write_result_tag),
 .cpl_done_valid(cq_done_valid),.cpl_written(cq_written),
 .cpl_error(cq_error),.cpl_tag(cq_done_tag),
 .m_axi_awid(cq_awid),.m_axi_awaddr(cq_awaddr),
 .m_axi_awlen(cq_awlen),.m_axi_awsize(cq_awsize),
 .m_axi_awburst(cq_awburst),.m_axi_awlock(cq_awlock),
 .m_axi_awcache(cq_arcache),.m_axi_awprot(cq_arprot),
 .m_axi_awvalid(cq_awvalid),.m_axi_awready(cq_awready),
 .m_axi_wdata(cq_wdata),.m_axi_wstrb(cq_wstrb),
 .m_axi_wlast(cq_wlast),.m_axi_wvalid(cq_wvalid),
 .m_axi_wready(cq_wready),.m_axi_bid(cq_bid),
 .m_axi_bresp(cq_bresp),.m_axi_bvalid(cq_bvalid),
 .m_axi_bready(cq_bready)
);
assign cpl_written_i = cq_written;
// Separate CQ RAM in this focused adapter test: its frontdoor AR/R is used
// solely for independent inspection. Full-chip integration must route both
// packet and CQ masters through the same real Data NoC before #64 closure.
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_cq_ram (
 .clk,.rst,
 .s_axi_awid(cq_awid),.s_axi_awaddr(cq_awaddr[15:0]),
 .s_axi_awlen(cq_awlen),.s_axi_awsize(cq_awsize),
 .s_axi_awburst(cq_awburst),.s_axi_awlock(cq_awlock),
 .s_axi_awcache(cq_arcache),.s_axi_awprot(cq_arprot),
 .s_axi_awvalid(cq_awvalid),.s_axi_awready(cq_awready),
 .s_axi_wdata(cq_wdata),.s_axi_wstrb(cq_wstrb),
 .s_axi_wlast(cq_wlast),.s_axi_wvalid(cq_wvalid),
 .s_axi_wready(cq_wready),.s_axi_bid(cq_bid),
 .s_axi_bresp(cq_bresp),.s_axi_bvalid(cq_bvalid),
 .s_axi_bready(cq_bready),
 .s_axi_arid(4'd0),.s_axi_araddr(cq_check_araddr),
 .s_axi_arlen(8'd0),.s_axi_arsize(3'd3),
 .s_axi_arburst(2'b01),.s_axi_arlock(1'b0),
 .s_axi_arcache(4'd0),.s_axi_arprot(3'd0),
 .s_axi_arvalid(cq_check_arvalid),.s_axi_arready(cq_check_arready),
 .s_axi_rid(cq_check_rid),.s_axi_rdata(cq_check_rdata),
 .s_axi_rresp(cq_check_rresp),.s_axi_rlast(cq_check_rlast),
 .s_axi_rvalid(cq_check_rvalid),.s_axi_rready(cq_check_rready)
);
always @(posedge clk) if (!rst) begin
 if(cq_awvalid && cq_awready)begin
  if(cq_awaddr!=64'h500 || cq_awlen!=8'd3 ||
     cq_awsize!=3'd3 || cq_awburst!=2'b01)
   $fatal(1,"invalid completion-ring AXI AW");
  cq_aw_count<=cq_aw_count+1;
 end
 if(cq_bvalid && cq_bready)begin
  if(cq_bresp!=0) $fatal(1,"CQ AXI B not OKAY");
  cq_b_count<=cq_b_count+1;
 end
end

// Memory 1: RX descriptors written by test software through real AXI.
reg [15:0] ctrl_awaddr=0;reg ctrl_awvalid=0;
wire ctrl_awready;reg [63:0] ctrl_wdata=0;reg [7:0] ctrl_wstrb=0;
reg ctrl_wvalid=0,ctrl_wlast=0,ctrl_bready=0;
wire ctrl_wready,ctrl_bvalid;wire [1:0] ctrl_bresp;
wire [3:0] ctrl_bid;
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_ring_ram (
 .clk,.rst,
 .s_axi_awid(4'd0),.s_axi_awaddr(ctrl_awaddr),.s_axi_awlen(8'd0),
 .s_axi_awsize(3'd3),.s_axi_awburst(2'b01),.s_axi_awlock(1'b0),
 .s_axi_awcache(4'd0),.s_axi_awprot(3'd0),
 .s_axi_awvalid(ctrl_awvalid),.s_axi_awready(ctrl_awready),
 .s_axi_wdata(ctrl_wdata),.s_axi_wstrb(ctrl_wstrb),
 .s_axi_wlast(ctrl_wlast),.s_axi_wvalid(ctrl_wvalid),
 .s_axi_wready(ctrl_wready),.s_axi_bid(ctrl_bid),
 .s_axi_bresp(ctrl_bresp),.s_axi_bvalid(ctrl_bvalid),
 .s_axi_bready(ctrl_bready),
 .s_axi_arid(rd_arid),.s_axi_araddr(rd_araddr[15:0]),
 .s_axi_arlen(rd_arlen),.s_axi_arsize(rd_arsize),
 .s_axi_arburst(rd_arburst),.s_axi_arlock(rd_arlock),
 .s_axi_arcache(rd_arcache),.s_axi_arprot(rd_arprot),
 .s_axi_arvalid(rd_arvalid),.s_axi_arready(rd_arready),
 .s_axi_rid(rd_rid),.s_axi_rdata(rd_rdata),.s_axi_rresp(rd_rresp),
 .s_axi_rlast(rd_rlast),.s_axi_rvalid(rd_rvalid),.s_axi_rready(rd_rready)
);
// Memory 2: data packets; readback is through *real* AXI frontdoor.
reg [15:0] check_araddr=0;reg check_arvalid=0,check_rready=0;
wire check_arready;wire [3:0] check_rid;wire [63:0] check_rdata;
wire [1:0] check_rresp;wire check_rlast,check_rvalid;
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_packet_ram (
 .clk,.rst,
 .s_axi_awid(wr_awid),.s_axi_awaddr(wr_awaddr[15:0]),
 .s_axi_awlen(wr_awlen),.s_axi_awsize(wr_awsize),
 .s_axi_awburst(wr_awburst),.s_axi_awlock(wr_awlock),
 .s_axi_awcache(wr_awcache),.s_axi_awprot(wr_awprot),
 .s_axi_awvalid(wr_awvalid),.s_axi_awready(wr_awready),
 .s_axi_wdata(wr_wdata),.s_axi_wstrb(wr_wstrb),
 .s_axi_wlast(wr_wlast),.s_axi_wvalid(wr_wvalid),
 .s_axi_wready(wr_wready),.s_axi_bid(wr_bid),
 .s_axi_bresp(wr_bresp),.s_axi_bvalid(wr_bvalid),
 .s_axi_bready(wr_bready),
 .s_axi_arid(4'd0),.s_axi_araddr(check_araddr),
 .s_axi_arlen(8'd0),.s_axi_arsize(3'd3),
 .s_axi_arburst(2'b01),.s_axi_arlock(1'b0),
 .s_axi_arcache(4'd0),.s_axi_arprot(3'd0),
 .s_axi_arvalid(check_arvalid),.s_axi_arready(check_arready),
 .s_axi_rid(check_rid),.s_axi_rdata(check_rdata),
 .s_axi_rresp(check_rresp),.s_axi_rlast(check_rlast),
 .s_axi_rvalid(check_rvalid),.s_axi_rready(check_rready)
);
integer checks=0,packet_writes=0,desc_reads=0,status_count=0,drops=0;
reg last_ok=0;reg [3:0] last_error=0;
reg [31:0] last_cookie=0;reg [15:0] last_length=0;
always @(posedge clk) if(!rst) begin
 if(rd_arvalid && rd_arready)begin
  if(rd_araddr[63:16]!=0 || rd_araddr<64'h100 ||
     rd_araddr+({56'd0,rd_arlen}+1)*8>64'h1100)
   $fatal(1,"Descriptor read outside ring");
  desc_reads<=desc_reads+1;
 end
 if(wr_awvalid && wr_awready)begin
  if(wr_awaddr[63:16]!=0 || wr_awaddr<64'h2000 ||
     wr_awaddr+({56'd0,wr_awlen}+1)*8>64'ha000)
   $fatal(1,"Payload write outside permitted region");
  packet_writes<=packet_writes+1;
 end
 if(write_result_valid)begin
  status_count<=status_count+1;
  last_ok<=write_result_ok;
  last_error<=write_result_error;
  last_cookie<=write_result_cookie;
  last_length<=write_result_length;
 end
 if(frame_drop_pulse) drops<=drops+1;
end
task check(input logic ok,input string why);
begin
 if(ok!==1'b1)begin
  $display("FAIL queue+descriptor+DMA: %s @%0t",why,$time);
  $fatal(1);
 end
 checks=checks+1;
end
endtask
task automatic wr_reg(input [7:0] addr,input [31:0] val);
begin
 @(negedge clk);cfg_addr=addr;cfg_wdata=val;cfg_write=1;cfg_valid=1;
 #1;check(!cfg_error,"config CSR accepted");
 @(posedge clk);#1;
 @(negedge clk);cfg_valid=0;cfg_write=0;
end
endtask
task automatic rd_reg(input [7:0] addr,input [31:0] expected);
begin
 @(negedge clk);cfg_addr=addr;cfg_valid=1;cfg_write=0;
 #1;
 if(cfg_error || cfg_rdata!==expected)
  $fatal(1,"CSR %h expected %h got %h error %b",addr,expected,cfg_rdata,cfg_error);
 checks=checks+1;
 @(negedge clk);cfg_valid=0;
end
endtask
task automatic frontdoor_write(input [15:0] addr,input [63:0] value);
integer n;reg accepted;
begin
 @(negedge clk);ctrl_awaddr=addr;ctrl_awvalid=1;
 n=0;accepted=0;
 while(!accepted && n<400)begin
  @(posedge clk);accepted=ctrl_awready;n=n+1;
 end
 check(accepted,"descriptor AXI AW");@(negedge clk);ctrl_awvalid=0;
 ctrl_wdata=value;ctrl_wstrb=8'hff;ctrl_wlast=1;ctrl_wvalid=1;
 n=0;accepted=0;
 while(!accepted && n<400)begin
  @(posedge clk);accepted=ctrl_wready;n=n+1;
 end
 check(accepted,"descriptor AXI W");@(negedge clk);ctrl_wvalid=0;ctrl_wlast=0;
 ctrl_bready=1;n=0;accepted=0;
 while(!accepted && n<400)begin
  @(posedge clk);accepted=ctrl_bvalid;n=n+1;
 end
 check(accepted && ctrl_bresp==0,"descriptor AXI B OKAY");
 @(negedge clk);ctrl_bready=0;
end
endtask
task automatic send_frame(input [15:0] length,input [15:0] ethertype,
                          input integer seed);
integer n,index,b,tail,timeout;reg accepted;reg [63:0] data;reg [7:0] keep;
begin
 @(negedge clk);frame_length=length;frame_ethertype=ethertype;
 frame_is_udp=1;frame_udp_dst_port=6000;frame_valid=1;
 timeout=0;accepted=0;
 while(!accepted && timeout<400)begin
  @(posedge clk);accepted=frame_ready;timeout=timeout+1;
 end
 check(accepted,"packet metadata accepted");@(negedge clk);frame_valid=0;
 for(index=0;index<length;index=index+8)begin
  data=0;keep=0;tail=length-index;if(tail>8)tail=8;
  for(b=0;b<tail;b=b+1)begin
   data[b*8+:8]=(index+b+seed)&255;keep[b]=1;
  end
  rx_axis_tdata=data;rx_axis_tkeep=keep;rx_axis_tlast=(index+tail==length);
  rx_axis_tvalid=1;rx_axis_tuser=0;
  timeout=0;accepted=0;
  while(!accepted && timeout<2000)begin
   @(posedge clk);accepted=rx_axis_tready;timeout=timeout+1;
  end
  check(accepted,"DMA or drop consumed packet beat");
  @(negedge clk);
 end
 rx_axis_tvalid=0;rx_axis_tlast=0;rx_axis_tkeep=0;
end
endtask
task automatic wait_status(input integer target,input logic good);
integer cycles;
begin
 cycles=0;
 while(status_count<target && cycles<3000)begin
  @(posedge clk);cycles=cycles+1;
 end
 check(status_count==target,"write-result status observed");
 check(last_ok==good,"write-result status classification");
end
endtask
task automatic check_packet(input [15:0] addr,input integer len,input integer seed);
integer index,n,b,actual;reg ack,got;reg [63:0] observed;
begin
 for(index=0;index<len;index=index+8)begin
  @(negedge clk);check_araddr=addr+index;check_arvalid=1;check_rready=1;
  ack=0;n=0;
  while(!ack && n<400)begin
   @(posedge clk);ack=check_arready;n=n+1;
  end
  check(ack,"packet AXI frontdoor AR");
  @(negedge clk);check_arvalid=0;got=0;n=0;observed=0;
  while(!got && n<400)begin
   @(posedge clk);got=check_rvalid;
   if(got)begin
    observed=check_rdata;
    check(check_rresp==0 && check_rlast,"packet AXI R response");
   end
   n=n+1;
  end
  check(got,"packet SRAM AXI readback");
  actual=len-index;if(actual>8)actual=8;
  for(b=0;b<actual;b=b+1)
   check(observed[b*8+:8]===8'((index+b+seed)&255),
         "DMA byte correct, including partial final beat");
  @(negedge clk);check_rready=0;
 end
end
endtask
task automatic cq_read(input [15:0] addr,input [63:0] expected);
 integer n;reg got,ack;reg [63:0] observed;
 begin
  @(negedge clk);cq_check_araddr=addr;
  cq_check_arvalid=1;cq_check_rready=1;
  ack=0;n=0;
  while(!ack && n<400)begin
   @(posedge clk);ack=cq_check_arready;n=n+1;
  end
  check(ack,"CQ frontdoor AXI AR");
  @(negedge clk);cq_check_arvalid=0;got=0;n=0;observed=0;
  while(!got && n<400)begin
   @(posedge clk);got=cq_check_rvalid;
   if(got)begin
    observed=cq_check_rdata;
    check(cq_check_rresp==0 && cq_check_rlast,
          "CQ real AXI R last/OKAY");
   end
   n=n+1;
  end
  check(got,"CQ SRAM real AXI readback");
  check(observed===expected,"CQ record exact 64-bit payload");
  @(negedge clk);cq_check_rready=0;
 end
endtask

initial begin #30000000;$fatal(1,"integrated RX watchdog");end
initial begin
 repeat(8)@(posedge clk);@(negedge clk);rst=0;
 // Software/CPU frontdoor setup: descriptor ring and separate CQ, no
 // direct testbench writes to the underlying RTL RAM arrays.
 frontdoor_write(16'h100,64'h2100);
 frontdoor_write(16'h108,{32'hc0febabe,32'd2048});
 frontdoor_write(16'h110,0);frontdoor_write(16'h118,0);
 wr_reg(8'h20,32'h100);wr_reg(8'h24,0);
 wr_reg(8'h30,32'h500);wr_reg(8'h34,0);
 wr_reg(8'h74,32'h0800);wr_reg(8'h78,32'hffff);
 wr_reg(8'h7c,6000);wr_reg(8'h80,32'hffff);
 wr_reg(8'h84,3);wr_reg(8'h28,1);wr_reg(8'h08,1);
 check(rx_cq_slot_addr_o==64'h500,"RX CQ slot matches SRAM ring base");
 send_frame(85,16'h0800,37);
 wait_status(1,1);
 check(last_error==0 && last_length==85 &&
       last_cookie==32'hc0febabe,"DMA B completed, cookie and length checked");
 check(write_result_policy==8'd0,"RX policy exported with write result");
 check(rx_cq_slot_addr_o==64'h500,"CQ slot unchanged before CQ B");
 check(desc_reads>0 && packet_writes>0,"actual AXI descriptor read and payload write");
 rd_reg(8'h2c,1);
 rd_reg(8'h38,0);
 check(!irq,"IRQ withheld until CQ record actually written");
 check_packet(16'h2100,85,37);
 // The same RTL CQ writer now consumes the queued DMA result, writes four
 // 64-bit words using actual upstream axi_dma_wr, and observes AXI B.
 // No testbench completion pulse is injected.
 begin : wait_real_cq
  integer cycles;
  cycles=0;
  while(cq_b_count<1 && cycles<3000)begin
   @(posedge clk);cycles=cycles+1;
  end
  check(cq_b_count==1 && cq_aw_count==1,"one real CQ AXI AW/B");
  repeat(5)@(posedge clk);
 end
 check(cq_done_valid===1'b0 && cq_error==0,
       "CQ writer completed without a latched error");
 check(irq,"IRQ posted after real CQ writer B response");
 rd_reg(8'h38,1);
 cq_read(16'h500,64'hc0febabe);
 cq_read(16'h508,{32'd0,32'd85});
 cq_read(16'h510,64'd0);
 cq_read(16'h518,64'd0);
 check(rx_cq_slot_addr_o==64'h520,"CQ slot follows successful B-gated retirement");
 // No more RX descriptors: unsolicited valid frames drop without
 // overwriting the first buffer or incrementing the CQ producer.
 send_frame(64,16'h0800,50);
 repeat(10)@(posedge clk);
 rd_reg(8'h2c,1);rd_reg(8'h38,1);
 check(status_count==1 && drops>0,"no-buffer whole-packet drop");
 // Unmatched EtherType is also dropped with zero new DMA writes.
 send_frame(60,16'h0806,80);
 repeat(10)@(posedge clk);
 check(status_count==1,"unmatched frame cannot cause write result");
 check_packet(16'h2100,85,37);
 $display("PASS ethernet_rx_queue_engine_tb checks=%0d AXI_desc_AR=%0d AXI_payload_AW=%0d CQ_AW=%0d CQ_B=%0d",
          checks,desc_reads,packet_writes,cq_aw_count,cq_b_count);
 $finish;
end
endmodule
