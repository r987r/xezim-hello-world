`timescale 1ns/1ps
// Two *executing* CPUs: CPU0 boots from ROM, reads flash-model program words,
// copies both applications to originally blank SRAMs, releases CPU1 via MMIO,
// then both CPUs execute SRAM instructions and write completion signatures.
module boot_tb;
    import boot_config_pkg::*;
    reg clk = 0, rst = 1;
    always #5 clk = ~clk;
    initial begin
        repeat (10) @(negedge clk);
        rst = 0;
    end
    initial begin
        #1000000;
        $fatal(1, "BOOT FAIL: timed out without BOTH CPU application signatures");
    end

    wire c0_awvalid, c0_awready, c0_wvalid, c0_wready, c0_bvalid, c0_bready;
    wire c0_arvalid, c0_arready, c0_rvalid, c0_rready, c0_trap;
    wire [31:0] c0_awaddr, c0_wdata, c0_araddr, c0_rdata;
    wire [2:0] c0_awprot, c0_arprot;
    wire [3:0] c0_wstrb;

    wire [31:0] c1_ibus_addr, c1_dbus_addr, c1_dbus_data, c1_ibus_rdata, c1_dbus_rdata;
    wire [3:0] c1_dbus_select;
    wire c1_ibus_cyc, c1_ibus_ack, c1_dbus_cyc, c1_dbus_write, c1_dbus_ack;
    wire cpu1_release;
    wire [31:0] rom_reads, flash_reads, sram0_copies, sram1_copies;
    wire [31:0] cpu0_signature, cpu1_signature, c1_fetches;

    picorv32_cpu_adapter u_primary (
        .clk(clk), .rst(rst), .trap(c0_trap),
        .awvalid(c0_awvalid), .awready(c0_awready), .awaddr(c0_awaddr), .awprot(c0_awprot),
        .wvalid(c0_wvalid), .wready(c0_wready), .wdata(c0_wdata), .wstrb(c0_wstrb),
        .bvalid(c0_bvalid), .bready(c0_bready),
        .arvalid(c0_arvalid), .arready(c0_arready), .araddr(c0_araddr), .arprot(c0_arprot),
        .rvalid(c0_rvalid), .rready(c0_rready), .rdata(c0_rdata)
    );
    serv_cpu_adapter #(.RESET_PC(SRAM1_BASE)) u_secondary (
        .clk(clk), .rst(rst || !cpu1_release),
        .ibus_addr(c1_ibus_addr), .ibus_cyc(c1_ibus_cyc),
        .ibus_rdata(c1_ibus_rdata), .ibus_ack(c1_ibus_ack),
        .dbus_addr(c1_dbus_addr), .dbus_data(c1_dbus_data),
        .dbus_select(c1_dbus_select), .dbus_write(c1_dbus_write), .dbus_cyc(c1_dbus_cyc),
        .dbus_rdata(c1_dbus_rdata), .dbus_ack(c1_dbus_ack)
    );
    boot_memory_model #(
        .BOOTROM_BASE(BOOTROM_BASE), .FLASH_BASE(FLASH_BASE),
        .SRAM0_BASE(SRAM0_BASE), .SRAM1_BASE(SRAM1_BASE),
        .RESET_CTRL_BASE(RESET_CTRL_BASE), .SRAM_BYTES(SRAM_BYTES)
    ) u_memory (
        .clk(clk), .rst(rst),
        .c0_awvalid(c0_awvalid), .c0_awready(c0_awready), .c0_awaddr(c0_awaddr),
        .c0_wvalid(c0_wvalid), .c0_wready(c0_wready), .c0_wdata(c0_wdata), .c0_wstrb(c0_wstrb),
        .c0_bvalid(c0_bvalid), .c0_bready(c0_bready),
        .c0_arvalid(c0_arvalid), .c0_arready(c0_arready), .c0_araddr(c0_araddr),
        .c0_rvalid(c0_rvalid), .c0_rready(c0_rready), .c0_rdata(c0_rdata),
        .c1_ibus_addr(c1_ibus_addr), .c1_ibus_cyc(c1_ibus_cyc),
        .c1_ibus_rdata(c1_ibus_rdata), .c1_ibus_ack(c1_ibus_ack),
        .c1_dbus_addr(c1_dbus_addr), .c1_dbus_cyc(c1_dbus_cyc),
        .c1_dbus_write(c1_dbus_write), .c1_dbus_data(c1_dbus_data),
        .c1_dbus_select(c1_dbus_select), .c1_dbus_rdata(c1_dbus_rdata), .c1_dbus_ack(c1_dbus_ack),
        .cpu1_release(cpu1_release), .rom_read_count(rom_reads),
        .flash_read_count(flash_reads), .sram0_copy_count(sram0_copies),
        .sram1_copy_count(sram1_copies), .cpu0_app_signature_count(cpu0_signature),
        .cpu1_app_signature_count(cpu1_signature), .c1_inst_count(c1_fetches)
    );

    integer cycles = 0;
    integer debug_transactions = 0;
    // Optional waveform and bus transaction trace, off for normal regressions.
    initial if ($test$plusargs("BOOT_WAVE")) begin
        $dumpfile("boot-trace.vcd");
        $dumpvars(0, boot_tb);
    end
    always @(posedge clk) if (!rst && $test$plusargs("BOOT_TRACE")) begin
        if (c1_ibus_cyc && c1_ibus_ack && debug_transactions < 160) begin
            $display("BOOT_TXN I time=%0t pc=%h instr=%h", $time, c1_ibus_addr, c1_ibus_rdata);
            debug_transactions <= debug_transactions + 1;
        end
        if (c1_dbus_cyc && c1_dbus_ack && debug_transactions < 160) begin
            $display("BOOT_TXN D time=%0t addr=%h data=%h sel=%h wr=%b", $time, c1_dbus_addr, c1_dbus_data, c1_dbus_select, c1_dbus_write);
            debug_transactions <= debug_transactions + 1;
        end
    end
    reg saw_cpu0_sram_fetch = 0;
    always @(posedge clk) if (!rst) begin
        cycles <= cycles+1;
        if (c0_arvalid && c0_arready && c0_araddr >= SRAM0_BASE && c0_araddr < SRAM0_BASE + PROGRAM_WORDS*4)
            saw_cpu0_sram_fetch <= 1;
        if (!cpu1_release && c1_ibus_ack)
            $fatal(1, "BOOT FAIL: CPU1 acknowledged instruction while held in reset");
        if (cycles == 800 || cycles == 4000)
            $display("BOOT DEBUG cycles=%0d cpu0_addr=%h ar=%b/%b r=%b/%b aw=%b/%b w=%b/%b b=%b/%b rom=%0d flash=%0d copy0=%0d copy1=%0d release=%b cpu1fetch=%0d sig0=%0d sig1=%0d", cycles,c0_araddr,c0_arvalid,c0_arready,c0_rvalid,c0_rready,c0_awvalid,c0_awready,c0_wvalid,c0_wready,c0_bvalid,c0_bready,rom_reads,flash_reads,sram0_copies,sram1_copies,cpu1_release,c1_fetches,cpu0_signature,cpu1_signature);
        if (c0_trap)
            $fatal(1, "BOOT FAIL: CPU0 trap before completion");
        if (cpu0_signature > 0 && cpu1_signature > 0) begin
            if (!cpu1_release || rom_reads < 1 || flash_reads < 2*PROGRAM_WORDS ||
                sram0_copies != PROGRAM_WORDS || sram1_copies != PROGRAM_WORDS || !saw_cpu0_sram_fetch || c1_fetches < 1)
                $fatal(1, "BOOT FAIL: incomplete actual boot traffic rom=%0d flash=%0d copy0=%0d copy1=%0d c1fetch=%0d",rom_reads,flash_reads,sram0_copies,sram1_copies,c1_fetches);
            if (u_memory.u_sram0.mem[0] !== u_memory.flash[0] ||
                u_memory.u_sram0.mem[1] !== u_memory.flash[1] ||
                u_memory.u_sram1.mem[0] !== u_memory.flash[FLASH_SLOT_WORDS] ||
                u_memory.u_sram1.mem[1] !== u_memory.flash[FLASH_SLOT_WORDS+1])
                $fatal(1, "BOOT FAIL: SRAM does not match flash image");
            $display("PASS: cpu_cold_boot SRAM0=%h SRAM1=%h flash=%h reset=%h ROM=%0d flash_reads=%0d copy0=%0d copy1=%0d CPU1 fetch=%0d cycles=%0d", SRAM0_BASE, SRAM1_BASE, FLASH_BASE, RESET_CTRL_BASE, rom_reads, flash_reads, sram0_copies, sram1_copies, c1_fetches, cycles);
            $finish;
        end
    end
endmodule
