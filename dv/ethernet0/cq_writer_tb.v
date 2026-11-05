// Real completion DMA -> real upstream axi_ram readback.
// No packet GMII or NoC is instantiated in this scoped test.
`timescale 1ns/1ps
`default_nettype none

module ethernet_cq_axi_writer_tb;
 reg clk=0;always #5 clk=~clk;
 reg rst=1;
 reg req_valid=0;
 wire req_ready;
 reg [63:0] req_addr=0;
 reg [31:0] req_cookie=0,req_length=0,req_status=0;
 reg [31:0] req_policy=0,req_queue=0;
 reg [7:0] req_tag=0;
 wire cpl_done_valid,cpl_written;
 wire [3:0] cpl_error;
 wire [7:0] cpl_tag;
 wire [3:0] awid,bid;
 wire [63:0] awaddr,wdata;
 wire [7:0] awlen,wstrb;
 wire [2:0] awsize,awprot;
 wire [1:0] awburst,bresp;
 wire awlock,awvalid,awready,wlast,wvalid,wready,bvalid,bready;
 wire [3:0] awcache;
 reg [15:0] araddr=0;
 reg arvalid=0,rready=0;
 wire arready,rlast,rvalid;
 wire [3:0] rid;
 wire [63:0] rdata;
 wire [1:0] rresp;
 integer checks=0, aw_count=0,b_count=0,cpl_count=0;
 ethernet_cq_axi_writer #(.REGION_BASE(64'h0),
     .REGION_BYTES(64'h10000)) dut (
    .clk,.rst,.req_valid,.req_ready,.req_addr,.req_cookie,
    .req_length,.req_status,.req_policy,.req_queue,.req_tag,
    .cpl_done_valid,.cpl_written,.cpl_error,.cpl_tag,
    .m_axi_awid(awid),.m_axi_awaddr(awaddr),.m_axi_awlen(awlen),
    .m_axi_awsize(awsize),.m_axi_awburst(awburst),.m_axi_awlock(awlock),
    .m_axi_awcache(awcache),.m_axi_awprot(awprot),
    .m_axi_awvalid(awvalid),.m_axi_awready(awready),
    .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),
    .m_axi_wvalid(wvalid),.m_axi_wready(wready),
    .m_axi_bid(bid),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),
    .m_axi_bready(bready)
 );
 axi_ram #(.DATA_WIDTH(64), .ADDR_WIDTH(16), .ID_WIDTH(4)) sram (
    .clk,.rst,
    .s_axi_awid(awid),.s_axi_awaddr(awaddr[15:0]),
    .s_axi_awlen(awlen),.s_axi_awsize(awsize),.s_axi_awburst(awburst),
    .s_axi_awlock(awlock),.s_axi_awcache(awcache),
    .s_axi_awprot(awprot),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
    .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wlast(wlast),
    .s_axi_wvalid(wvalid),.s_axi_wready(wready),
    .s_axi_bid(bid),.s_axi_bresp(bresp),.s_axi_bvalid(bvalid),
    .s_axi_bready(bready),
    .s_axi_arid(4'd0),.s_axi_araddr(araddr),
    .s_axi_arlen(8'd0),.s_axi_arsize(3'd3),.s_axi_arburst(2'b01),
    .s_axi_arlock(1'b0),.s_axi_arcache(4'd0),.s_axi_arprot(3'd0),
    .s_axi_arvalid(arvalid),.s_axi_arready(arready),
    .s_axi_rid(rid),.s_axi_rdata(rdata),.s_axi_rresp(rresp),
    .s_axi_rlast(rlast),.s_axi_rvalid(rvalid),.s_axi_rready(rready)
 );
 task check(input logic ok,input string why);
 begin
   if(ok!==1'b1) begin $display("FAIL Ethernet CQ: %s @%0t",why,$time);$fatal(1);end
   checks=checks+1;
 end
 endtask
 always @(posedge clk) begin
   if(!rst) begin
     if(awvalid && awready) begin
        if(awaddr[63:16] || awlen != 8'd3 || awsize != 3'd3 ||
           awburst != 2'b01 || awaddr[4:0] != 0) begin
          $display("FAIL Ethernet CQ illegal AXI AW %h %d",awaddr,awlen);
          $fatal(1);
        end
        aw_count <= aw_count+1;
     end
     if(bvalid && bready) b_count <= b_count+1;
     if(cpl_written) begin
       if(b_count <= cpl_count) begin
         $display("FAIL completion was claimed before AXI B");
         $fatal(1);
       end
       cpl_count <= cpl_count+1;
     end
   end
 end
 task submit(input [63:0] addr,input [31:0] cookie,input [31:0] length,
             input [31:0] status,input [31:0] policy,
             input [31:0] queue_id,input [7:0] tag);
 integer timeout;
 reg accepted;
 begin
   @(negedge clk);
   req_addr=addr;req_cookie=cookie;req_length=length;
   req_status=status;req_policy=policy;req_queue=queue_id;
   req_tag=tag;req_valid=1;timeout=0;accepted=0;
   while(timeout<500 && !accepted) begin
      @(posedge clk);accepted=req_ready;timeout=timeout+1;
   end
   check(accepted,"descriptor accepted");
   @(negedge clk);req_valid=0;
 end
 endtask
 task done(input logic expect_success,input [7:0] tag);
 integer timeout;reg seen;
 begin
   timeout=0;seen=0;
   while(timeout<3000 && !seen) begin
     @(posedge clk);
     if(cpl_done_valid) begin
       check(cpl_tag==tag,"completion tag matches descriptor");
       check(cpl_written==expect_success,"written pulse follows AXI B");
       if(expect_success)check(cpl_error==0,"good AXI B gives status OK");
       else check(cpl_error!=0,"rejected descriptor flags error");
       seen=1;
     end
     timeout=timeout+1;
   end
   check(seen,"bounded completion");
 end
 endtask
 task frontdoor_word(input [15:0] addr,input [63:0] expected);
 integer timeout;reg accepted,seen;
 begin
   @(negedge clk);araddr=addr;arvalid=1;timeout=0;accepted=0;
   while(!accepted && timeout<300) begin
     @(posedge clk);accepted=arready;timeout=timeout+1;
   end
   check(accepted,"AXI AR accepted");
   @(negedge clk);arvalid=0;rready=1;seen=0;timeout=0;
   while(!seen && timeout<300) begin
     @(posedge clk);
     if(rvalid && rready)begin
       if(rresp!=0||!rlast||rdata!==expected)begin
         $display("FAIL CQ frontdoor addr=%h got=%h expected=%h",addr,rdata,expected);
         $fatal(1);
       end
       seen=1;
     end
     timeout=timeout+1;
   end
   check(seen,"AXI frontdoor completion payload");
   @(negedge clk);rready=0;
 end
 endtask
 initial begin #20000000;$fatal(1,"CQ watchdog");end
 initial begin
   repeat(8)@(posedge clk);
   @(negedge clk);rst=0;
   submit(64'h10000,1,2,3,4,5,8'h10);
   done(0,8'h10);
   submit(64'h104,1,2,3,4,5,8'h11);
   done(0,8'h11);
   check(aw_count==0,"invalid writes emit no AXI memory traffic");
   submit(64'h100,32'h11223344,85,0,3,0,8'h21);
   done(1,8'h21);
   frontdoor_word(16'h100,64'h0000000011223344);
   frontdoor_word(16'h108,64'h0000000000000055);
   frontdoor_word(16'h110,64'h0000000000000003);
   frontdoor_word(16'h118,64'd0);
   submit(64'h120,32'h76543210,1514,7,9,2,8'h22);
   done(1,8'h22);
   frontdoor_word(16'h120,64'h0000000076543210);
   frontdoor_word(16'h128,{32'd7,32'd1514});
   frontdoor_word(16'h130,{32'd2,32'd9});
   frontdoor_word(16'h138,64'd0);
   check(aw_count==2 && b_count>=2 && cpl_count>=2,
         "real CQ AXI writes returned B and retired two records");
   $display("PASS ethernet_cq_axi_writer_tb checks=%0d AW=%0d B=%0d",
            checks,aw_count,b_count);
   $finish;
 end
endmodule
`default_nettype wire
