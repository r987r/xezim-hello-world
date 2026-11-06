// Real memory-resident 32-byte RX descriptor fetch through pinned AXI RTL.
// Writes descriptors through the AXI RAM frontdoor, never a memory backdoor.
// No MAC traffic, queue CSR or completion ring writes are implied.
`timescale 1ns/1ps
`default_nettype none
module ethernet_rx_desc_fetch_tb;
reg clk=0;always #5 clk=~clk;
reg rst=1,req_valid=0,result_ready=0;
wire req_ready,result_valid,result_ok;
reg [63:0] req_ring_addr=0;
reg [15:0] req_frame_len=0;
reg [7:0] req_tag=0;
wire [3:0] result_error;
wire [63:0] result_buffer_addr;
wire [31:0] result_capacity,result_cookie;
wire [7:0] result_tag;
wire [3:0] arid,rid;
wire [63:0] araddr,rdata;
wire [7:0] arlen;
wire [2:0] arsize;
wire [1:0] arburst;
wire arlock;
wire [3:0] arcache;
wire [2:0] arprot;
wire arvalid,arready,rvalid,rlast,rready;
wire [1:0] rresp;
reg [15:0] awaddr=0;
reg awvalid=0,wvalid=0,wlast=0,bready=0;
reg [63:0] wdata=0;
reg [7:0] wstrb=0;
wire awready,wready,bvalid;
wire [3:0] bid;
wire [1:0] bresp;
integer checks=0,read_requests=0;

ethernet_rx_desc_fetch #(
    .AXI_ADDR_WIDTH(64),.AXI_ID_WIDTH(4),
    .RING_BASE(64'h100),.RING_BYTES(64'h1000),
    .BUFFER_BASE(64'h2000),.BUFFER_BYTES(64'h8000),
    .ALT_BUFFER_BASE(64'h140000000),.ALT_BUFFER_BYTES(64'h2000000)
) dut (
    .clk,.rst,.req_valid,.req_ready,.req_ring_addr,.req_frame_len,.req_tag,
    .result_valid,.result_ready,.result_ok,.result_error,
    .result_buffer_addr,.result_capacity,.result_cookie,.result_tag,
    .m_axi_arid(arid),.m_axi_araddr(araddr),.m_axi_arlen(arlen),
    .m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arlock(arlock),
    .m_axi_arcache(arcache),.m_axi_arprot(arprot),
    .m_axi_arvalid(arvalid),.m_axi_arready(arready),
    .m_axi_rid(rid),.m_axi_rdata(rdata),.m_axi_rresp(rresp),
    .m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready)
);
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_mem (
    .clk,.rst,.s_axi_awid(4'd0),.s_axi_awaddr(awaddr),
    .s_axi_awlen(8'd0),.s_axi_awsize(3'd3),
    .s_axi_awburst(2'b01),.s_axi_awlock(1'b0),
    .s_axi_awcache(4'd0),.s_axi_awprot(3'd0),
    .s_axi_awvalid(awvalid),.s_axi_awready(awready),
    .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),
    .s_axi_wlast(wlast),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
    .s_axi_bid(bid),.s_axi_bresp(bresp),
    .s_axi_bvalid(bvalid),.s_axi_bready(bready),
    .s_axi_arid(arid),.s_axi_araddr(araddr[15:0]),
    .s_axi_arlen(arlen),.s_axi_arsize(arsize),
    .s_axi_arburst(arburst),.s_axi_arlock(arlock),
    .s_axi_arcache(arcache),.s_axi_arprot(arprot),
    .s_axi_arvalid(arvalid),.s_axi_arready(arready),
    .s_axi_rid(rid),.s_axi_rdata(rdata),.s_axi_rresp(rresp),
    .s_axi_rlast(rlast),.s_axi_rvalid(rvalid),.s_axi_rready(rready)
);
always @(posedge clk) if(!rst && arvalid && arready) begin
    if(araddr[63:16]!=0 || araddr[4:0]!=0 ||
       araddr<64'h100 || araddr+32>64'h1100 ||
       arsize!=3'd3 || arburst!=2'b01)
        $fatal(1,"Descriptor reader issued invalid AXI AR");
    read_requests<=read_requests+1;
end
task check(input logic good,input string why);
begin
    if(good!==1'b1)begin
        $display("FAIL RX descriptor fetch: %s at %0t",why,$time);
        $fatal(1);
    end
    checks=checks+1;
end
endtask
task automatic write_word(input [15:0] addr,input [63:0] value);
integer n;reg ack;
begin
    @(negedge clk);awaddr=addr;awvalid=1;
    n=0;ack=0;
    while(!ack && n<500)begin
        @(posedge clk);ack=awready;n=n+1;
    end
    check(ack,"AXI frontdoor AW handshake");
    @(negedge clk);awvalid=0;wdata=value;wstrb=8'hff;wlast=1;wvalid=1;
    n=0;ack=0;
    while(!ack && n<500)begin
        @(posedge clk);ack=wready;n=n+1;
    end
    check(ack,"AXI frontdoor W handshake");
    @(negedge clk);wvalid=0;wlast=0;bready=1;
    n=0;ack=0;
    while(!ack && n<500)begin
        @(posedge clk);ack=bvalid;n=n+1;
    end
    check(ack && bresp==0,"AXI frontdoor B OKAY");
    @(negedge clk);bready=0;
end
endtask
task automatic store(input [15:0] base,input [63:0] dest,
                     input [31:0] capacity,input [31:0] cookie,
                     input [31:0] flags,input [31:0] region,
                     input [63:0] reserved);
begin
    write_word(base,dest);
    write_word(base+8,{cookie,capacity});
    write_word(base+16,{region,flags});
    write_word(base+24,reserved);
end
endtask
task automatic request_desc(input [63:0] address,input [15:0] frame,
                            input [7:0] tag,input logic good,
                            input [3:0] error,
                            input [63:0] expect_dest,
                            input [31:0] expect_cap,
                            input [31:0] expect_cookie);
integer n;reg ack,got;
begin
    @(negedge clk);req_ring_addr=address;req_frame_len=frame;
    req_tag=tag;req_valid=1;
    n=0;ack=0;
    while(!ack && n<500)begin
        @(posedge clk);ack=req_ready;n=n+1;
    end
    check(ack,"ring request handshake");
    @(negedge clk);req_valid=0;
    n=0;got=0;
    while(!got && n<1000)begin
        @(posedge clk);got=result_valid;n=n+1;
    end
    check(got,"descriptor fetch result posted");
    check(result_ok==good,"descriptor acceptance/rejection");
    check(result_error==error,"descriptor rejection code");
    check(result_tag==tag,"descriptor tag preserved");
    if(good)begin
        check(result_buffer_addr==expect_dest,"fetched physical buffer address");
        check(result_capacity==expect_cap,"fetched buffer capacity");
        check(result_cookie==expect_cookie,"fetched software cookie");
    end
    @(negedge clk);result_ready=1;
    @(posedge clk);#1;
    check(!result_valid,"single result retires exactly once");
    @(negedge clk);result_ready=0;
end
endtask
initial begin #10000000;$fatal(1,"descriptor test watchdog");end
initial begin
    repeat(8) @(posedge clk);@(negedge clk);rst=0;
    // 32-byte descriptor is genuinely written and fetched through AXI RTL.
    store(16'h100,64'h2100,2048,32'habcdef01,0,0,0);
    request_desc(64'h100,85,8'h11,1,0,64'h2100,2048,32'habcdef01);
    store(16'h120,64'h2200,128,32'h00000002,0,0,0);
    request_desc(64'h120,85,8'h12,1,0,64'h2200,128,2);
    // An external packet cannot induce a write outside the authorized region.
    store(16'h140,64'h9ff8,128,3,0,0,0);
    request_desc(64'h140,85,8'h13,0,4'ha,0,0,0);
    // Too-small posted buffer and wrong region IDs are rejected before DMA.
    store(16'h160,64'h2400,32,4,0,0,0);
    request_desc(64'h160,85,8'h14,0,4'ha,0,0,0);
    // Region 1 accepts physical >4GiB modeled DDR without truncation.
    store(16'h180,64'h140000100,2048,5,0,1,0);
    request_desc(64'h180,85,8'h15,1,0,64'h140000100,2048,5);
    // Region 2 and wrong-region SRAM pointers must remain rejected.
    store(16'h1c0,64'h140000100,2048,7,0,2,0);
    request_desc(64'h1c0,85,8'h19,0,4'ha,0,0,0);
    store(16'h1e0,64'h2600,2048,8,0,1,0);
    request_desc(64'h1e0,85,8'h1a,0,4'ha,0,0,0);
    // Region crossing and high-bit aliasing are rejected before packet DMA.
    store(16'h200,64'h141fffff8,128,9,0,1,0);
    request_desc(64'h200,85,8'h1b,0,4'ha,0,0,0);
    store(16'h220,64'h100,128,10,0,1,0);
    request_desc(64'h220,85,8'h1c,0,4'ha,0,0,0);
    // Reserved fields are not silently treated as valid new ABI.
    store(16'h1a0,64'h2800,2048,6,0,0,64'h1);
    request_desc(64'h1a0,85,8'h16,0,4'ha,0,0,0);
    // Bad ring address must cause no new AXI read.
    request_desc(64'h20000,85,8'h17,0,4'h8,0,0,0);
    check(read_requests==10,"invalid ring address emitted no AR");
    request_desc(64'h123,85,8'h18,0,4'h8,0,0,0);
    check(read_requests==10,"unaligned ring address emitted no AR");
    $display("PASS ethernet_rx_desc_fetch_tb checks=%0d AXI_reads=%0d",
             checks,read_requests);
    $finish;
end
endmodule
`default_nettype wire
