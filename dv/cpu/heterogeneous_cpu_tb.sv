`timescale 1ns/1ps
// Elaboration and reset/request activity check with two distinct real CPU RTL
// implementations. Not a boot/ISA/full-NoC integration test.
module heterogeneous_cpu_tb;
    reg clk=0, rst=1;
    always #5 clk=~clk;

    wire picorv_fetch;
    wire [31:0] picorv_address;
    wire picorv_trap;
    picorv32_cpu_adapter u_picorv32 (
        .clk(clk), .rst(rst), .trap(picorv_trap),
        .awready(1'b0), .wready(1'b0), .bvalid(1'b0),
        .arvalid(picorv_fetch), .arready(1'b0), .araddr(picorv_address),
        .rvalid(1'b0), .rdata(32'h00000013)
    );

    wire serv_fetch;
    wire [31:0] serv_address;
    serv_cpu_adapter u_serv (
        .clk(clk), .rst(rst),
        .ibus_addr(serv_address), .ibus_cyc(serv_fetch),
        .ibus_rdata(32'h00000013), .ibus_ack(1'b0),
        .dbus_rdata(32'b0), .dbus_ack(1'b0)
    );

    integer picorv_count=0, serv_count=0;
    always @(posedge clk) if (!rst) begin
        if (picorv_fetch) picorv_count <= picorv_count + 1;
        if (serv_fetch) serv_count <= serv_count + 1;
    end
    initial begin
        repeat (10) @(negedge clk);
        rst=0;
        repeat (900) @(posedge clk);
        if (picorv_count < 1 || serv_count < 1)
            $fatal(1,"FAIL CPU interface activity pico=%0d serv=%0d",picorv_count,serv_count);
        $display("PASS: heterogeneous_cpu_tb picorv32_axi and serv_wishbone requested instructions");
        $finish;
    end
endmodule
