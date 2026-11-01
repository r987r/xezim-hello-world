`timescale 1ns/1ps
// PicoRV32's native AXI4-Lite initiator, normalized to an active-high reset.
// Full-chip data-fabric attachment additionally needs AXI4-Lite to AXI4
// conversion and a 32-to-64-bit address translator at the subsystem edge.
module picorv32_cpu_adapter (
    input wire clk, input wire rst,
    output wire trap,
    output wire awvalid, input wire awready, output wire [31:0] awaddr,
    output wire [2:0] awprot,
    output wire wvalid, input wire wready, output wire [31:0] wdata,
    output wire [3:0] wstrb,
    input wire bvalid, output wire bready,
    output wire arvalid, input wire arready, output wire [31:0] araddr,
    output wire [2:0] arprot,
    input wire rvalid, output wire rready, input wire [31:0] rdata
);
    picorv32_axi #(.ENABLE_MUL(0), .ENABLE_DIV(0)) u_cpu (
        .clk(clk), .resetn(~rst), .trap(trap),
        .mem_axi_awvalid(awvalid), .mem_axi_awready(awready),
        .mem_axi_awaddr(awaddr), .mem_axi_awprot(awprot),
        .mem_axi_wvalid(wvalid), .mem_axi_wready(wready),
        .mem_axi_wdata(wdata), .mem_axi_wstrb(wstrb),
        .mem_axi_bvalid(bvalid), .mem_axi_bready(bready),
        .mem_axi_arvalid(arvalid), .mem_axi_arready(arready),
        .mem_axi_araddr(araddr), .mem_axi_arprot(arprot),
        .mem_axi_rvalid(rvalid), .mem_axi_rready(rready),
        .mem_axi_rdata(rdata),
        .irq(32'b0), .pcpi_wr(1'b0), .pcpi_rd(32'b0),
        .pcpi_wait(1'b0), .pcpi_ready(1'b0)
    );
endmodule
