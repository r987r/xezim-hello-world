`timescale 1ns/1ps
// Smallest real CPU2 execution gate: one SERV, one memory, four RV32I words.
// This intentionally preloads its RAM: it is an isolated CPU/IP test, NOT a
// cold-boot test. See dv/boot/boot_tb.sv for ROM -> flash -> blank SRAM boot.
module serv_minimal_tb;
    reg clk = 0;
    reg rst = 1;
    always #5 clk = ~clk;
    initial begin repeat (8) @(negedge clk); rst = 0; end

    wire [31:0] i_addr, d_addr, d_data, i_data, d_rdata;
    wire i_cyc, i_ack, d_cyc, d_ack, d_we;
    wire [3:0] d_sel;
    serv_cpu_adapter #(.RESET_PC(32'h11000000)) u_serv (
        .clk(clk), .rst(rst),
        .ibus_addr(i_addr), .ibus_cyc(i_cyc), .ibus_rdata(i_data), .ibus_ack(i_ack),
        .dbus_addr(d_addr), .dbus_data(d_data), .dbus_select(d_sel),
        .dbus_write(d_we), .dbus_cyc(d_cyc), .dbus_rdata(d_rdata), .dbus_ack(d_ack)
    );

    reg [31:0] mem [0:1023];
    initial begin
        for (integer j=0; j<1024; j=j+1) mem[j] = 0;
        mem[0] = 32'h110002b7; // LUI t0,0x11000
        mem[1] = 32'h06600313; // ADDI t1,zero,0x66
        mem[2] = 32'h1062a023; // SW t1,0x100(t0)
        mem[3] = 32'h0000006f; // JAL zero,0
    end

    // Upstream SERV's servant_ram registers read data and acknowledgment.
    // An asynchronous, combinational instruction read was not a valid stand-in.
    reg i_ack_q = 0, d_ack_q = 0;
    reg [31:0] i_data_q = 0, d_data_q = 0;
    assign i_ack = i_ack_q;
    assign d_ack = d_ack_q;
    assign i_data = i_data_q;
    assign d_rdata = d_data_q;
    integer instruction_count = 0;
    always @(posedge clk) begin
        if (rst) begin
            i_ack_q <= 0;
            d_ack_q <= 0;
        end else begin
            i_ack_q <= i_cyc && !i_ack_q;
            d_ack_q <= d_cyc && !d_ack_q;
            if (i_cyc && i_addr >= 32'h11000000 && i_addr < 32'h11001000)
                i_data_q <= mem[(i_addr-32'h11000000)>>2];
            else i_data_q <= 0;
            if (d_cyc && d_addr >= 32'h11000000 && d_addr < 32'h11001000)
                d_data_q <= mem[(d_addr-32'h11000000)>>2];
            else d_data_q <= 0;
            if (i_cyc && i_ack) begin
                instruction_count <= instruction_count + 1;
                $display("SERV FETCH pc=%h opcode=%h", i_addr, i_data);
            end
            if (d_cyc && d_ack) begin
                $display("SERV DATA addr=%h wr=%b data=%h strobe=%h", d_addr, d_we, d_data, d_sel);
                if (d_we && d_addr === 32'h11000100 && d_data === 32'h66 &&
                    d_sel === 4'hf && instruction_count >= 3) begin
                    $display("PASS: serv_minimal_tb; executed three RV32I instructions");
                    $finish;
                end else $fatal(1, "SERV FAIL: incorrect memory transaction");
            end
        end
    end
    initial begin #30000; $fatal(1, "SERV FAIL: timeout, fetches=%0d", instruction_count); end
endmodule
