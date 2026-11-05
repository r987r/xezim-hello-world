// SRAM is real upstream axi_ram RTL. Populate via AXI frontdoor writes, then
// verify upstream AXI DMA reader produces exact AXIS bytes, tkeep, tlast.
`timescale 1ns/1ps
`default_nettype none
module ethernet_tx_dma_tb;
reg clk=0;always #5 clk=~clk;
reg rst=1;
reg desc_valid=0;
wire desc_ready;
reg [63:0] desc_src_addr=0;
reg [15:0] desc_length=0,desc_capacity=0;
reg [7:0] desc_tag=0;
wire status_valid,status_ok;
wire [3:0] status_error;
wire [7:0] status_tag;
wire [63:0] tdata;
wire [7:0] tkeep;
wire tvalid,tlast,tuser;
reg tready=0;
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
reg [15:0] init_awaddr=0;
reg init_awvalid=0,init_wvalid=0,init_wlast=0,init_bready=0;
reg [63:0] init_wdata=0;
reg [7:0] init_wstrb=0;
wire init_awready,init_wready,init_bvalid;
wire [3:0] init_bid;
wire [1:0] init_bresp;
integer checks=0,read_requests=0,stream_beats=0;

ethernet_tx_dma #(
    .AXI_ADDR_WIDTH(64),.AXI_DATA_WIDTH(64),.AXI_ID_WIDTH(4),
    .LEN_WIDTH(16),.REGION_BASE(64'h0),.REGION_BYTES(64'h10000)
) dut (
    .clk,.rst,.desc_valid,.desc_ready,.desc_src_addr,
    .desc_length,.desc_capacity,.desc_tag,
    .status_valid,.status_ok,.status_error,.status_tag,
    .m_axis_tdata(tdata),.m_axis_tkeep(tkeep),.m_axis_tvalid(tvalid),
    .m_axis_tready(tready),.m_axis_tlast(tlast),.m_axis_tuser(tuser),
    .m_axi_arid(arid),.m_axi_araddr(araddr),.m_axi_arlen(arlen),
    .m_axi_arsize(arsize),.m_axi_arburst(arburst),.m_axi_arlock(arlock),
    .m_axi_arcache(arcache),.m_axi_arprot(arprot),
    .m_axi_arvalid(arvalid),.m_axi_arready(arready),
    .m_axi_rid(rid),.m_axi_rdata(rdata),.m_axi_rresp(rresp),
    .m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready)
);
axi_ram #(.DATA_WIDTH(64),.ADDR_WIDTH(16),.ID_WIDTH(4)) u_ram (
    .clk,.rst,
    .s_axi_awid(4'd0),.s_axi_awaddr(init_awaddr),
    .s_axi_awlen(8'd0),.s_axi_awsize(3'd3),
    .s_axi_awburst(2'b01),.s_axi_awlock(1'b0),
    .s_axi_awcache(4'd0),.s_axi_awprot(3'd0),
    .s_axi_awvalid(init_awvalid),.s_axi_awready(init_awready),
    .s_axi_wdata(init_wdata),.s_axi_wstrb(init_wstrb),
    .s_axi_wlast(init_wlast),.s_axi_wvalid(init_wvalid),
    .s_axi_wready(init_wready),
    .s_axi_bid(init_bid),.s_axi_bresp(init_bresp),
    .s_axi_bvalid(init_bvalid),.s_axi_bready(init_bready),
    .s_axi_arid(arid),.s_axi_araddr(araddr[15:0]),
    .s_axi_arlen(arlen),.s_axi_arsize(arsize),.s_axi_arburst(arburst),
    .s_axi_arlock(arlock),.s_axi_arcache(arcache),.s_axi_arprot(arprot),
    .s_axi_arvalid(arvalid),.s_axi_arready(arready),
    .s_axi_rid(rid),.s_axi_rdata(rdata),.s_axi_rresp(rresp),
    .s_axi_rlast(rlast),.s_axi_rvalid(rvalid),.s_axi_rready(rready)
);
always @(posedge clk) if(!rst && arvalid && arready) begin
    if(araddr[63:16]!=0 || arsize!=3'd3 || arburst!=2'b01 ||
        araddr[11:0]+({56'd0,arlen}+1)*8 > 4096)
        $fatal(1,"Invalid AXI AR issued");
    read_requests<=read_requests+1;
end
// 50% downstream AXI-stream stalls to check beat stability/byte ordering.
always @(negedge clk) if(rst) tready=0; else tready=~tready;
task check(input logic good,input string why);
begin
    if(good!==1'b1)begin
        $display("FAIL ethernet TX DMA: %s at %0t",why,$time);
        $fatal(1);
    end
    checks=checks+1;
end
endtask
task automatic write_word(input [15:0] addr,input [63:0] data);
integer cycles;
reg accepted;
begin
    @(negedge clk);init_awaddr=addr;init_awvalid=1;
    accepted=0;cycles=0;
    while(!accepted && cycles<500) begin
        @(posedge clk);accepted=init_awready;cycles=cycles+1;
    end
    check(accepted,"AXI preload AW accepted");
    @(negedge clk);init_awvalid=0;
    init_wdata=data;init_wstrb=8'hff;init_wlast=1;init_wvalid=1;
    accepted=0;cycles=0;
    while(!accepted && cycles<500)begin
        @(posedge clk);accepted=init_wready;cycles=cycles+1;
    end
    check(accepted,"AXI preload W accepted");
    @(negedge clk);init_wvalid=0;init_wlast=0;init_bready=1;
    accepted=0;cycles=0;
    while(!accepted && cycles<500)begin
        @(posedge clk);accepted=init_bvalid;cycles=cycles+1;
    end
    check(accepted,"AXI preload B received");
    check(init_bresp==0,"AXI preload BRESP OKAY");
    @(negedge clk);init_bready=0;
end
endtask
task automatic preload(input [15:0] base,input integer n,input integer seed);
integer index,b;
reg [63:0] value;
begin
    for(index=0;index<n;index=index+8)begin
        value=0;
        for(b=0;b<8;b=b+1)
            value[b*8+:8]=(index+b+seed)&255;
        write_word(base+index,value);
    end
end
endtask
task automatic submit(input [63:0] addr,input integer n,
                      input integer cap,input [7:0] tag);
integer timeout;reg ack;
begin
    @(negedge clk);
    desc_src_addr=addr;desc_length=n;desc_capacity=cap;
    desc_tag=tag;desc_valid=1;
    ack=0;timeout=0;
    while(!ack && timeout<1000) begin
        @(posedge clk);ack=desc_ready;timeout=timeout+1;
    end
    check(ack,"TX descriptor accepted");
    @(negedge clk);desc_valid=0;
end
endtask
task automatic collect(input integer n,input integer seed);
integer received,remaining,b,timeout;
reg [7:0] exp_keep;
reg got,last_received;
begin
    received=0;timeout=0;last_received=0;
    while(received<n && timeout<20000)begin
        @(posedge clk);
        if(tvalid && tready)begin
            remaining=n-received;
            exp_keep=remaining>=8 ? 8'hff : ((1<<remaining)-1);
            check(tkeep==exp_keep,"TX tkeep, including final partial beat");
            check(tlast==(remaining<=8),"TX tlast exactly at packet end");
            check(!tuser,"unexpected TX stream error");
            for(b=0;b<8 && b<remaining;b=b+1)
                check(tdata[b*8+:8]===8'((received+b+seed)&255),
                      "TX byte matches AXI-initialized memory");
            received=received+(remaining>8 ? 8:remaining);
            stream_beats=stream_beats+1;
            last_received=tlast;
        end
        timeout=timeout+1;
    end
    check(received==n && last_received,"full TX AXIS frame received");
end
endtask
task automatic complete(input logic ok,input [3:0] error,
                         input [7:0] tag);
integer timeout;reg got;
begin
    timeout=0;got=0;
    while(!got && timeout<3000)begin
        @(posedge clk);got=status_valid;timeout=timeout+1;
    end
    check(got,"TX status delivered");
    check(status_ok==ok,"TX completion success classification");
    check(status_error==error,"TX completion error");
    check(status_tag==tag,"TX completion tag");
    @(negedge clk);
end
endtask
initial begin #10000000;$fatal(1,"TX DMA watchdog");end
initial begin
    repeat(8) @(posedge clk);
    @(negedge clk);rst=0;
    submit(64'h10000,64,64,8'h11);
    complete(0,4'h8,8'h11);
    check(read_requests==0,"invalid memory address did not issue AR");
    submit(64'h103,32,32,8'h12);
    complete(0,4'h8,8'h12);
    check(read_requests==0,"unaligned memory address rejected");
    submit(64'h100,100,16,8'h13);
    complete(0,4'h8,8'h13);
    check(read_requests==0,"insufficient capacity rejected");

    preload(16'h100,64,12);
    submit(64'h100,64,64,8'h14);
    collect(64,12);
    complete(1,0,8'h14);

    preload(16'h200,85,30);
    submit(64'h200,85,85,8'h15);
    collect(85,30);
    complete(1,0,8'h15);

    preload(16'h300,127,40);
    submit(64'h300,127,127,8'h16);
    collect(127,40);
    complete(1,0,8'h16);

    preload(16'h800,512,50);
    submit(64'h800,512,512,8'h17);
    collect(512,50);
    complete(1,0,8'h17);

    preload(16'h1000,1514,60);
    submit(64'h1000,1514,1514,8'h18);
    collect(1514,60);
    complete(1,0,8'h18);
    check(read_requests>=5,"real AXI RTL read transactions observed");
    $display("PASS ethernet_tx_dma_tb checks=%0d AR=%0d AXIS_beats=%0d",
             checks,read_requests,stream_beats);
    $finish;
end
endmodule
`default_nettype wire
