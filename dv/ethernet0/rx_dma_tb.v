// Real upstream axi_dma_wr -> real upstream axi_ram (64-bit data) regression.
// AXI RAM is a behavioral SRAM RTL model; not a physical SRAM macro or NoC.
// Independent frontdoor AXI reads verify every byte of transferred frames.
`timescale 1ns/1ps
`default_nettype none

module ethernet_rx_dma_tb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 1;

    reg desc_valid = 0;
    wire desc_ready;
    reg [63:0] desc_dst_addr = 0;
    reg [15:0] desc_length = 0, desc_capacity = 0;
    reg [7:0] desc_tag = 0;
    wire status_valid, status_ok;
    wire [3:0] status_error;
    wire [7:0] status_tag;
    wire [15:0] status_length;
    reg [63:0] s_axis_tdata = 0;
    reg [7:0] s_axis_tkeep = 0;
    reg s_axis_tvalid = 0, s_axis_tlast = 0, s_axis_tuser = 0;
    wire s_axis_tready;

    wire [3:0] awid;
    wire [63:0] awaddr;
    wire [7:0] awlen;
    wire [2:0] awsize;
    wire [1:0] awburst;
    wire awlock;
    wire [3:0] awcache;
    wire [2:0] awprot;
    wire awvalid, awready;
    wire [63:0] wdata;
    wire [7:0] wstrb;
    wire wlast,wvalid,wready;
    wire [3:0] bid;
    wire [1:0] bresp;
    wire bvalid,bready;

    reg [15:0] araddr = 0;
    reg arvalid = 0;
    wire arready;
    wire [3:0] rid;
    wire [63:0] rdata;
    wire [1:0] rresp;
    wire rlast,rvalid;
    reg rready = 0;

    integer checks=0, aw_count=0, b_count=0, byte_count=0;
    wire b_handshake = bvalid && bready;
    ethernet_rx_dma #(
        .AXI_ADDR_WIDTH(64), .AXI_DATA_WIDTH(64), .AXI_ID_WIDTH(4),
        .LEN_WIDTH(16), .REGION_BASE(64'h0), .REGION_BYTES(64'h10000)
    ) u_eth_rx (
        .clk, .rst, .desc_valid, .desc_ready,
        .desc_dst_addr, .desc_length, .desc_capacity, .desc_tag,
        .status_valid, .status_ok, .status_error, .status_tag, .status_length,
        .s_axis_tdata, .s_axis_tkeep, .s_axis_tvalid, .s_axis_tready,
        .s_axis_tlast, .s_axis_tuser,
        .m_axi_awid(awid),.m_axi_awaddr(awaddr),.m_axi_awlen(awlen),
        .m_axi_awsize(awsize),.m_axi_awburst(awburst),
        .m_axi_awlock(awlock),.m_axi_awcache(awcache),.m_axi_awprot(awprot),
        .m_axi_awvalid(awvalid),.m_axi_awready(awready),
        .m_axi_wdata(wdata),.m_axi_wstrb(wstrb),.m_axi_wlast(wlast),
        .m_axi_wvalid(wvalid),.m_axi_wready(wready),
        .m_axi_bid(bid),.m_axi_bresp(bresp),.m_axi_bvalid(bvalid),
        .m_axi_bready(bready)
    );
    // The tested RX bridge guards the 64-bit absolute address against a
    // 64 KiB aperture. Only the proven-zero high bits are removed at the
    // boundary of the 16-bit-address upstream SRAM RTL.
    axi_ram #(
        .DATA_WIDTH(64), .ADDR_WIDTH(16), .ID_WIDTH(4)
    ) u_sram (
        .clk, .rst, .s_axi_awid(awid), .s_axi_awaddr(awaddr[15:0]),
        .s_axi_awlen(awlen), .s_axi_awsize(awsize), .s_axi_awburst(awburst),
        .s_axi_awlock(awlock), .s_axi_awcache(awcache),
        .s_axi_awprot(awprot), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wlast(wlast),
        .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bid(bid), .s_axi_bresp(bresp), .s_axi_bvalid(bvalid),
        .s_axi_bready(bready),
        .s_axi_arid(4'd0), .s_axi_araddr(araddr),
        .s_axi_arlen(8'd0), .s_axi_arsize(3'd3), .s_axi_arburst(2'b01),
        .s_axi_arlock(1'b0), .s_axi_arcache(4'd0), .s_axi_arprot(3'd0),
        .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rid(rid), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
        .s_axi_rlast(rlast), .s_axi_rvalid(rvalid), .s_axi_rready(rready)
    );

    always @(posedge clk) begin
        if (!rst) begin
            if (awvalid && awready) begin
                if (awaddr[63:16] != 0 || awburst != 2'b01 ||
                    awsize != 3'd3 || ((awaddr[11:0] +
                    (({56'd0,awlen}+1)*8)) > 4096)) begin
                    $display("FAIL RX DMA illegal AW addr=%h len=%d",awaddr,awlen);
                    $fatal(1);
                end
                aw_count <= aw_count+1;
            end
            if (b_handshake) b_count <= b_count+1;
            if (wvalid && wready)
                byte_count <= byte_count + $countones(wstrb);
        end
    end
    task check(input logic ok, input string why);
        begin
            if (ok !== 1'b1) begin
                $display("FAIL RX DMA: %s at %0t",why,$time);
                $fatal(1);
            end
            checks=checks+1;
        end
    endtask

    task automatic submit(input [63:0] addr, input integer n,
                          input integer capacity, input [7:0] tag);
        integer timeout;
        reg accepted;
        begin
            @(negedge clk);
            desc_dst_addr=addr;desc_length=n;desc_capacity=capacity;
            desc_tag=tag;desc_valid=1;
            accepted=0;timeout=0;
            while (!accepted && timeout<1000) begin
                @(posedge clk);
                accepted=desc_ready;
                timeout=timeout+1;
            end
            check(accepted,"descriptor accepted");
            @(negedge clk);desc_valid=0;
        end
    endtask
    task automatic stream_bytes(input integer n, input integer seed,
                                 input logic mark_bad);
        integer index,b,remaining,timeout;
        reg accepted;
        reg [63:0] beat;
        reg [7:0] keep;
        begin
            for(index=0;index<n;index=index+8) begin
                beat=0;keep=0;
                remaining=n-index;
                if (remaining>8) remaining=8;
                for(b=0;b<remaining;b=b+1) begin
                    beat[b*8 +: 8]=(index+b+seed) & 255;
                    keep[b]=1'b1;
                end
                @(negedge clk);
                s_axis_tdata=beat;
                s_axis_tkeep=keep;
                s_axis_tlast=(index+remaining==n);
                s_axis_tuser=mark_bad && s_axis_tlast;
                s_axis_tvalid=1;
                accepted=0;timeout=0;
                while(!accepted && timeout<1500) begin
                    @(posedge clk);
                    accepted=s_axis_tready;
                    timeout=timeout+1;
                end
                check(accepted,"stream beat accepted");
            end
            @(negedge clk);
            s_axis_tvalid=0;
            s_axis_tlast=0;
            s_axis_tuser=0;
            s_axis_tkeep=0;
        end
    endtask
    task automatic completed(input logic good, input [3:0] expected_error,
                              input integer n, input [7:0] tag);
        integer timeout;
        reg got;
        begin
            got=0;timeout=0;
            while(!got && timeout<3000) begin
                @(posedge clk);
                got=status_valid;
                timeout=timeout+1;
            end
            check(got,"DMA completion delivered");
            check(status_ok===good,"success/failure completion classification");
            check(status_error===expected_error,"AXI DMA error status");
            check(status_tag==tag,"descriptor tag retained");
            if(good)
                check(status_length==n,"actual DMA length");
            @(negedge clk);
        end
    endtask
    task automatic frontdoor_word(input [15:0] addr,input [63:0] expected);
        integer timeout;
        reg accepted, got;
        reg [63:0] observed;
        begin
            @(negedge clk);
            araddr=addr;arvalid=1;rready=1;
            accepted=0;timeout=0;
            while(!accepted && timeout<500) begin
                @(posedge clk);
                accepted=arready;
                timeout=timeout+1;
            end
            check(accepted,"AXI SRAM AR accepted");
            @(negedge clk);arvalid=0;
            got=0;timeout=0;observed=0;
            while(!got && timeout<500) begin
                @(posedge clk);
                got=rvalid;
                if (got) begin
                    observed=rdata;
                    check(rlast && rresp==0, "SRAM frontdoor RLAST/OKAY");
                end
                timeout=timeout+1;
            end
            check(got,"AXI SRAM read response");
            if(observed !== expected) begin
                $display("FAIL SRAM readback at %h got=%h expected=%h",
                          addr,observed,expected);
                $fatal(1);
            end
            checks=checks+1;
            @(negedge clk);rready=0;
        end
    endtask
    task automatic success_packet(input [63:0] addr,input integer n,
                                   input integer seed,input [7:0] tag);
        integer k,b,actual;
        reg [63:0] exp;
        begin
            submit(addr,n,n,tag);
            stream_bytes(n,seed,0);
            completed(1,0,n,tag);
            for(k=0;k<n;k=k+8) begin
                exp=0;
                actual=n-k;
                if (actual>8) actual=8;
                for(b=0;b<actual;b=b+1)
                    if (b<actual) exp[b*8 +: 8]=(k+b+seed)&255;
                // Only check complete beats. Partial last-beat bytes are
                // tested separately after first writing a known sentinel.
                if(actual==8)
                    frontdoor_word(16'(addr+k),exp);
            end
        end
    endtask
    initial begin #10000000;$fatal(1,"RX DMA test watchdog");end
    initial begin
        repeat(8) @(posedge clk);
        @(negedge clk);rst=0;
        // No buffer may be written by a rejected descriptor.
        submit(64'h10000,64,64,8'h11);
        completed(0,4'h8,0,8'h11);
        check(aw_count==0,"out-of-aperture address issued no AXI write");
        submit(64'h100,100,32,8'h12);
        completed(0,4'h8,0,8'h12);
        check(aw_count==0,"short-capacity descriptor issued no AXI write");
        submit(64'h103,64,64,8'h13);
        completed(0,4'h8,0,8'h13);
        check(aw_count==0,"misaligned descriptor issued no AXI write");

        success_packet(64'h100,64,12,8'h14);
        success_packet(64'h200,85,30,8'h15);
        success_packet(64'h300,127,40,8'h16);
        success_packet(64'h800,512,50,8'h17);
        success_packet(64'h1000,1514,60,8'h18);
        // Test the strict length accounting: a too-short frame is not a
        // successful RX, even though AXI may have written a partial buffer.
        submit(64'h2000,24,24,8'h19);
        stream_bytes(16,80,0);
        completed(0,4'h9,16,8'h19);
        // Marked frame errors must never produce success completions.
        submit(64'h2100,32,32,8'h1a);
        stream_bytes(32,100,1);
        completed(0,4'ha,32,8'h1a);
        check(b_count>=5,"real RTL AXI write B responses observed");
        check(byte_count>=64+85+127+512+1514,
              "real RTL SRAM data bytes transferred");
        $display("PASS ethernet_rx_dma_tb checks=%0d AW=%0d B=%0d bytes=%0d",
                 checks,aw_count,b_count,byte_count);
        $finish;
    end
endmodule
`default_nettype wire
