`timescale 1ns/1ps
// Passive fabric boundary checker. Verifies that output ports route only their
// address window and that crossbar ID extension identifies the source master.
module axi_route_monitor #(
    parameter integer N_IN = 2,
    parameter integer N_MEM = 2,
    parameter integer ADDR_BITS = 64,
    parameter integer IN_ID_BITS = 4,
    parameter integer OUT_ID_BITS = 5,
    parameter [N_MEM*ADDR_BITS-1:0] TARGET_BASES = '0,
    parameter [N_MEM*32-1:0] TARGET_WIDTHS = '0,
    parameter [N_IN*N_MEM-1:0] ENABLED_ROUTES = {N_IN*N_MEM{1'b1}}
) (
    input wire clk,
    input wire rst,
    input wire [N_MEM-1:0] m_awvalid,
    input wire [N_MEM-1:0] m_awready,
    input wire [N_MEM*ADDR_BITS-1:0] m_awaddr,
    input wire [N_MEM*OUT_ID_BITS-1:0] m_awid,
    input wire [N_MEM-1:0] m_arvalid,
    input wire [N_MEM-1:0] m_arready,
    input wire [N_MEM*ADDR_BITS-1:0] m_araddr,
    input wire [N_MEM*OUT_ID_BITS-1:0] m_arid
);
    integer writes [0:N_IN-1][0:N_MEM-1];
    integer reads  [0:N_IN-1][0:N_MEM-1];
    integer i, j, target, src;
    reg [ADDR_BITS-1:0] addr;
    reg [ADDR_BITS-1:0] lo, hi;
    integer width;

    initial begin
        for (integer m = 0; m < N_IN; m = m + 1)
            for (integer h = 0; h < N_MEM; h = h + 1) begin
                writes[m][h] = 0;
                reads[m][h] = 0;
            end
    end

    always @(posedge clk) begin
        if (!rst) begin
            for (target = 0; target < N_MEM; target = target + 1) begin
                lo = TARGET_BASES[target*ADDR_BITS +: ADDR_BITS];
                width = TARGET_WIDTHS[target*32 +: 32];
                hi = lo + (ADDR_BITS'(1) << width);
                if (m_awvalid[target] && m_awready[target]) begin
                    addr = m_awaddr[target*ADDR_BITS +: ADDR_BITS];
                    src = int'(m_awid[target*OUT_ID_BITS +: OUT_ID_BITS] >> IN_ID_BITS);
                    if (src >= N_IN || addr < lo || addr >= hi ||
                        !ENABLED_ROUTES[src*N_MEM+target])
                        $fatal(1,"FAIL route AW: src=%0d target=%0d address=%h expected=[%h,%h)",src,target,addr,lo,hi);
                    writes[src][target] = writes[src][target] + 1;
                end
                if (m_arvalid[target] && m_arready[target]) begin
                    addr = m_araddr[target*ADDR_BITS +: ADDR_BITS];
                    src = int'(m_arid[target*OUT_ID_BITS +: OUT_ID_BITS] >> IN_ID_BITS);
                    if (src >= N_IN || addr < lo || addr >= hi ||
                        !ENABLED_ROUTES[src*N_MEM+target])
                        $fatal(1,"FAIL route AR: src=%0d target=%0d address=%h expected=[%h,%h)",src,target,addr,lo,hi);
                    reads[src][target] = reads[src][target] + 1;
                end
            end
        end
    end

    task check_coverage;
        begin
            for (integer m = 0; m < N_IN; m = m + 1)
                for (integer h = 0; h < N_MEM; h = h + 1) begin
                    if (ENABLED_ROUTES[m*N_MEM+h] && (writes[m][h] < 1 || reads[m][h] < 1))
                        $fatal(1,"FAIL missing route coverage: master=%0d memory=%0d writes=%0d reads=%0d",m,h,writes[m][h],reads[m][h]);
                    $display("COVER ROUTE master=%0d hbm=%0d writes=%0d reads=%0d",m,h,writes[m][h],reads[m][h]);
                end
        end
    endtask
endmodule
