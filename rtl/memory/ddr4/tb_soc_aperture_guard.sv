// Real Verilator RTL test of the DDR-B address guard; protocol/DECERR
// response handling and full-chip integration remain separate tasks.
module tb_ddr_litedram_aperture_guard;
    logic [63:0] phys_addr;
    logic [7:0]  axlen;
    logic [2:0]  axsize;
    logic [1:0]  axburst;
    logic [5:0]  atop;
    wire [31:0] local_addr;
    wire allow;
    wire [2:0] fault;

    localparam logic [63:0] BASE = 64'h0000_0001_4000_0000;
    localparam logic [63:0] MODEL = 64'h0200_0000;

    ddr_litedram_axi_aperture_guard dut (
        .phys_addr_i(phys_addr), .axlen_i(axlen),
        .axsize_i(axsize), .axburst_i(axburst), .atop_i(atop),
        .local_addr_o(local_addr), .allow_o(allow), .fault_o(fault)
    );

    task automatic check(input logic [63:0] address,
                         input logic [7:0] len,
                         input logic [2:0] size,
                         input logic [1:0] burst,
                         input logic [5:0] atomic,
                         input bit expected_allow,
                         input logic [2:0] expected_fault,
                         input logic [31:0] expected_local);
        phys_addr=address; axlen=len; axsize=size; axburst=burst; atop=atomic;
        #1;
        if (allow !== expected_allow || fault !== expected_fault ||
            local_addr !== expected_local)
            $fatal(1, "DDR guard fail addr=%h len=%d size=%d burst=%d atop=%d: allow=%b fault=%d local=%h",
                   address, len, size, burst, atomic, allow, fault, local_addr);
    endtask

    initial begin
        check(BASE,                 8'd0, 3'd3, 2'b01, 6'd0, 1'b1, 3'd0, 32'h00000000);
        check(BASE + 64'h1000,     8'd15, 3'd3, 2'b01, 6'd0, 1'b1, 3'd0, 32'h00001000);
        check(BASE + MODEL-64'd8,  8'd0, 3'd3, 2'b01, 6'd0, 1'b1, 3'd0, 32'h01fffff8);
        // Protect the unmodeled 1 GiB architectural DDR window.
        check(BASE + MODEL,        8'd0, 3'd3, 2'b01, 6'd0, 1'b0, 3'd4, 32'h0);
        check(BASE + MODEL-64'd8,  8'd1, 3'd3, 2'b01, 6'd0, 1'b0, 3'd4, 32'h0);
        // Do not accept a high-address alias of local 0x0000.
        check(BASE + 64'h1_0000_0000, 8'd0, 3'd3, 2'b01, 6'd0, 1'b0, 3'd3, 32'h0);
        check(BASE - 64'd8,        8'd0, 3'd3, 2'b01, 6'd0, 1'b0, 3'd3, 32'h0);
        // Reject a burst that crosses a 4 KiB AXI boundary.
        check(BASE + 64'hff8,      8'd1, 3'd3, 2'b01, 6'd0, 1'b0, 3'd5, 32'h0);
        check(BASE + 64'h1000,     8'd0, 3'd4, 2'b01, 6'd0, 1'b0, 3'd2, 32'h0);
        check(BASE + 64'h1000,     8'd0, 3'd3, 2'b10, 6'd0, 1'b0, 3'd2, 32'h0);
        check(BASE + 64'h1000,     8'd0, 3'd3, 2'b01, 6'd1, 1'b0, 3'd1, 32'h0);
        // Full 256-beat INCR access is legal when wholly inside a 4KiB page.
        check(BASE + 64'h1000,     8'hff,3'd3, 2'b01, 6'd0, 1'b1, 3'd0, 32'h00001000);
        $display("PASS real DDR-B RTL aperture/burst guard: no physical aliases");
        $finish;
    end
endmodule
