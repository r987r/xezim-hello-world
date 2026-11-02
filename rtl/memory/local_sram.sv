`timescale 1ns/1ps
// Reusable two-initiator behavioral RTL SRAM, uninitialized at power-on.
// Port A: AXI-Lite-facing CPU0; port B: Wishbone-facing SERV.
// A reads combinationally for the AXI-Lite responder's registered R channel.
// B reads synchronously, matching SERV's upstream servant_ram contract.
// This synthesizes as RTL but technology SRAM macro inference/replacement is
// platform-specific and is NOT claimed for any ASIC process.
module local_sram #(parameter integer BYTES = 16384) (
    input wire clk,
    input wire [31:0] a_read_addr,
    output wire [31:0] a_rdata,
    input wire a_we,
    input wire [31:0] a_write_addr,
    input wire [31:0] a_wdata,
    input wire [3:0] a_wstrb,
    input wire [31:0] b_read_addr,
    input wire b_read_en,
    output reg [31:0] b_rdata,
    input wire b_we,
    input wire [31:0] b_write_addr,
    input wire [31:0] b_wdata,
    input wire [3:0] b_wstrb
);
    localparam integer WORDS = BYTES/4;
    reg [31:0] mem [0:WORDS-1]; // intentionally no reset or initialization
    assign a_rdata = mem[a_read_addr[31:2]];
    always @(posedge clk) begin
`ifndef SYNTHESIS
        if (b_read_en) b_rdata <= mem[b_read_addr[31:2]];
        if (a_we && b_we && (a_write_addr[31:2] == b_write_addr[31:2]))
            $fatal(1, "SRAM: same-address dual-writer collision");
`endif
        for (integer i=0;i<4;i=i+1) begin
            if (a_we && a_wstrb[i]) mem[a_write_addr[31:2]][8*i +: 8] <= a_wdata[8*i +: 8];
            if (b_we && b_wstrb[i]) mem[b_write_addr[31:2]][8*i +: 8] <= b_wdata[8*i +: 8];
        end
    end
endmodule
