`timescale 1ns/1ps
module local_sram_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg [31:0] ar=0, aw=0, ad=0, br=0, bw=0, bd=0;
    reg ae=0, be=0, bre=0;
    reg [3:0] as=0, bs=0;
    wire [31:0] aq, bq;
    local_sram #(.BYTES(256)) dut (
        .clk(clk),.a_read_addr(ar),.a_rdata(aq),.a_we(ae),
        .a_write_addr(aw),.a_wdata(ad),.a_wstrb(as),
        .b_read_addr(br),.b_read_en(bre),.b_rdata(bq),
        .b_we(be),.b_write_addr(bw),.b_wdata(bd),.b_wstrb(bs)
    );
    initial begin
        #1;
        if (aq !== 32'bx)
            $fatal(1, "SRAM must not be preinitialized");
        @(negedge clk);
        aw=0; ad=32'h11223344; as=4'hf; ae=1;
        @(negedge clk); ae=0;
        #1;
        if(aq!==32'h11223344) $fatal(1,"SRAM A full-word write mismatch: %h",aq);
        aw=0; ad=32'h0000aabb; as=4'b0011; ae=1;
        @(negedge clk); ae=0; #1;
        if(aq!==32'h1122aabb) $fatal(1,"SRAM A byte strobes broken: %h",aq);
        bre=1; br=0;
        @(negedge clk); bre=0; #1;
        if(bq!==32'h1122aabb) $fatal(1,"SRAM B registered read broken: %h",bq);
        bw=4; bd=32'h88776655; bs=4'hf; be=1;
        @(negedge clk); be=0; ar=4; #1;
        if(aq!==32'h88776655) $fatal(1,"SRAM B write not visible to A: %h",aq);
        ar=0; #1;
        if(aq!==32'h1122aabb) $fatal(1,"SRAM independent address corruption");
        $display("PASS: local_sram_tb uninitialized, byte-lanes, A/B read-write");
        $finish;
    end
endmodule
