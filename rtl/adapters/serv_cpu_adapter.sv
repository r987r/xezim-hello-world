`timescale 1ns/1ps
// Distinct CPU integration contract: SERV exposes separate Wishbone-like
// instruction and data buses. The chip boot configuration uses pinned
// ZipCPU bridges in serv_axi_lite_adapter and a PULP instruction/data mux.
module serv_cpu_adapter #(parameter [31:0] RESET_PC = 32'h0) (
    input wire clk, input wire rst,
    output wire [31:0] ibus_addr, output wire ibus_cyc,
    input wire [31:0] ibus_rdata, input wire ibus_ack,
    output wire [31:0] dbus_addr, output wire [31:0] dbus_data,
    output wire [3:0] dbus_select,
    output wire dbus_write, output wire dbus_cyc,
    input wire [31:0] dbus_rdata, input wire dbus_ack
);
    serv_rf_top #(.WITH_CSR(0), .RESET_PC(RESET_PC)) u_cpu (
        .clk(clk), .i_rst(rst), .i_timer_irq(1'b0),
        .o_ibus_adr(ibus_addr), .o_ibus_cyc(ibus_cyc),
        .i_ibus_rdt(ibus_rdata), .i_ibus_ack(ibus_ack),
        .o_dbus_adr(dbus_addr), .o_dbus_dat(dbus_data),
        .o_dbus_sel(dbus_select), .o_dbus_we(dbus_write),
        .o_dbus_cyc(dbus_cyc), .i_dbus_rdt(dbus_rdata), .i_dbus_ack(dbus_ack),
        .i_ext_rd(32'b0), .i_ext_ready(1'b0)
    );
endmodule
