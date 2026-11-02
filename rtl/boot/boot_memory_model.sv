`timescale 1ns/1ps
// Cold-boot simulation system: immutable boot ROM + READ-ONLY flash model,
// two distinct uninitialized SRAMs, CPU0 AXI4-Lite interface, SERV I/D buses,
// and a real reset-control MMIO register. This is NOT a SPI flash controller,
// SRAM macro, or full-chip AXI NoC. See docs/boot.md.
module boot_memory_model #(
    parameter [31:0] BOOTROM_BASE = 32'h0000_0000,
    parameter [31:0] FLASH_BASE = 32'h2000_0000,
    parameter [31:0] SRAM0_BASE = 32'h1000_0000,
    parameter [31:0] SRAM1_BASE = 32'h1100_0000,
    parameter [31:0] RESET_CTRL_BASE = 32'h4002_0000,
    parameter integer SRAM_BYTES = 16384,
    parameter BOOTROM_FILE = "gen/boot/bootrom.hex",
    parameter FLASH_FILE = "gen/boot/flash.hex"
) (
    input wire clk,
    input wire rst,
    input wire c0_awvalid,
    output wire c0_awready,
    input wire [31:0] c0_awaddr,
    input wire c0_wvalid,
    output wire c0_wready,
    input wire [31:0] c0_wdata,
    input wire [3:0] c0_wstrb,
    output reg c0_bvalid,
    input wire c0_bready,
    input wire c0_arvalid,
    output wire c0_arready,
    input wire [31:0] c0_araddr,
    output reg c0_rvalid,
    input wire c0_rready,
    output reg [31:0] c0_rdata,
    input wire [31:0] c1_ibus_addr,
    input wire c1_ibus_cyc,
    output wire [31:0] c1_ibus_rdata,
    output wire c1_ibus_ack,
    input wire [31:0] c1_dbus_addr,
    input wire c1_dbus_cyc,
    input wire c1_dbus_write,
    input wire [31:0] c1_dbus_data,
    input wire [3:0] c1_dbus_select,
    output wire [31:0] c1_dbus_rdata,
    output wire c1_dbus_ack,
    output reg cpu1_release,
    output reg [31:0] rom_read_count,
    output reg [31:0] flash_read_count,
    output reg [31:0] sram0_copy_count,
    output reg [31:0] sram1_copy_count,
    output reg [31:0] cpu0_app_signature_count,
    output reg [31:0] cpu1_app_signature_count,
    output reg [31:0] c1_inst_count
);
    localparam integer SRAM_WORDS = SRAM_BYTES / 4;
    // SRAM intentionally starts with invalid RISC-V instruction (zero) and
    // no firmware image. Only CPU0 stores may initialize the program words.
    reg [31:0] rom [0:1023];
    reg [31:0] flash [0:16383];
    reg [31:0] sram0 [0:SRAM_WORDS-1];
    reg [31:0] sram1 [0:SRAM_WORDS-1];
    initial begin
        for (integer n=0; n<1024; n=n+1) rom[n] = 32'h00000000;
        for (integer n=0; n<16384; n=n+1) flash[n] = 32'h00000000;
        for (integer n=0; n<SRAM_WORDS; n=n+1) begin
            sram0[n] = 32'h00000000;
            sram1[n] = 32'h00000000;
        end
        $readmemh(BOOTROM_FILE, rom);
        $readmemh(FLASH_FILE, flash);
    end

    function automatic [31:0] read_word(input [31:0] addr);
        if (addr >= BOOTROM_BASE && addr < BOOTROM_BASE + 4096)
            read_word = rom[(addr - BOOTROM_BASE) >> 2];
        else if (addr >= FLASH_BASE && addr < FLASH_BASE + 65536)
            read_word = flash[(addr - FLASH_BASE) >> 2];
        else if (addr >= SRAM0_BASE && addr < SRAM0_BASE + SRAM_BYTES)
            read_word = sram0[(addr - SRAM0_BASE) >> 2];
        else if (addr >= SRAM1_BASE && addr < SRAM1_BASE + SRAM_BYTES)
            read_word = sram1[(addr - SRAM1_BASE) >> 2];
        else if (addr == RESET_CTRL_BASE)
            read_word = {31'b0, cpu1_release};
        else
            read_word = 32'h00000000;
    endfunction

    reg have_aw, have_w;
    reg [31:0] pending_awaddr, pending_wdata;
    reg [3:0] pending_wstrb;
    assign c0_awready = !rst && !have_aw && !c0_bvalid;
    assign c0_wready  = !rst && !have_w  && !c0_bvalid;
    assign c0_arready = !rst && !c0_rvalid;

    wire cpu1_rst = rst || !cpu1_release;
    // Registered Wishbone acknowledgments: the request and write byte enables
    // must settle before the responder acknowledges and consumes the access.
    reg c1_i_ack_q, c1_d_ack_q;
    always @(posedge clk) begin
        if (cpu1_rst) begin
            c1_i_ack_q <= 0;
            c1_d_ack_q <= 0;
        end else begin
            c1_i_ack_q <= c1_ibus_cyc && !c1_i_ack_q;
            c1_d_ack_q <= c1_dbus_cyc && !c1_d_ack_q;
        end
    end
    assign c1_ibus_ack   = c1_i_ack_q;
    // Match upstream SERV's registered Wishbone instruction/data read timing.
    reg [31:0] c1_ibus_rdata_q, c1_dbus_rdata_q;
    always @(posedge clk) begin
        c1_ibus_rdata_q <= read_word(c1_ibus_addr);
        c1_dbus_rdata_q <= read_word(c1_dbus_addr);
    end
    assign c1_ibus_rdata = c1_ibus_rdata_q;
    assign c1_dbus_ack   = c1_d_ack_q;
    assign c1_dbus_rdata = c1_dbus_rdata_q;

    always @(posedge clk) begin
        if (rst) begin
            have_aw <= 0;
            have_w <= 0;
            c0_bvalid <= 0;
            c0_rvalid <= 0;
            c0_rdata <= 0;
            cpu1_release <= 0;
            rom_read_count <= 0;
            flash_read_count <= 0;
            sram0_copy_count <= 0;
            sram1_copy_count <= 0;
            cpu0_app_signature_count <= 0;
            cpu1_app_signature_count <= 0;
            c1_inst_count <= 0;
        end else begin
            if (c0_awvalid && c0_awready) begin
                have_aw <= 1;
                pending_awaddr <= c0_awaddr;
            end
            if (c0_wvalid && c0_wready) begin
                have_w <= 1;
                pending_wdata <= c0_wdata;
                pending_wstrb <= c0_wstrb;
            end
            if (c0_bvalid && c0_bready) c0_bvalid <= 0;
            if (c0_rvalid && c0_rready) c0_rvalid <= 0;
            if (c0_arvalid && c0_arready) begin
                if (c0_araddr[1:0] != 2'b00)
                    $fatal(1, "BOOT: unaligned CPU0 read %h", c0_araddr);
                if (!((c0_araddr >= BOOTROM_BASE && c0_araddr < BOOTROM_BASE + 4096) ||
                      (c0_araddr >= FLASH_BASE && c0_araddr < FLASH_BASE + 65536) ||
                      (c0_araddr >= SRAM0_BASE && c0_araddr < SRAM0_BASE + SRAM_BYTES) ||
                      (c0_araddr >= SRAM1_BASE && c0_araddr < SRAM1_BASE + SRAM_BYTES) ||
                      c0_araddr == RESET_CTRL_BASE))
                    $fatal(1, "BOOT: unmapped CPU0 read %h (no address aliasing)", c0_araddr);
                c0_rdata <= read_word(c0_araddr);
                c0_rvalid <= 1;
                if (c0_araddr >= BOOTROM_BASE && c0_araddr < BOOTROM_BASE + 4096)
                    rom_read_count <= rom_read_count + 1;
                if (c0_araddr >= FLASH_BASE && c0_araddr < FLASH_BASE + 65536)
                    flash_read_count <= flash_read_count + 1;
            end
            if (have_aw && have_w && !c0_bvalid) begin
                if (pending_awaddr[1:0] != 2'b00 || pending_wstrb != 4'hf)
                    $fatal(1, "BOOT: prototype only supports aligned 32-bit CPU0 stores at %h", pending_awaddr);
                if (pending_awaddr >= SRAM0_BASE && pending_awaddr < SRAM0_BASE + SRAM_BYTES) begin
                    sram0[(pending_awaddr-SRAM0_BASE) >> 2] <= pending_wdata;
                    if (pending_awaddr < SRAM0_BASE + 16)
                        sram0_copy_count <= sram0_copy_count + 1;
                    if (pending_awaddr == SRAM0_BASE + 'h100 && pending_wdata == 32'h55)
                        cpu0_app_signature_count <= cpu0_app_signature_count + 1;
                end else if (pending_awaddr >= SRAM1_BASE && pending_awaddr < SRAM1_BASE + SRAM_BYTES) begin
                    sram1[(pending_awaddr-SRAM1_BASE) >> 2] <= pending_wdata;
                    if (pending_awaddr < SRAM1_BASE + 16)
                        sram1_copy_count <= sram1_copy_count + 1;
                end else if (pending_awaddr == RESET_CTRL_BASE) begin
                    if (pending_wdata != 1)
                        $fatal(1, "BOOT: unsupported reset control value %h", pending_wdata);
                    cpu1_release <= 1;
                end else
                    $fatal(1, "BOOT: unmapped or read-only CPU0 store %h", pending_awaddr);
                have_aw <= 0;
                have_w <= 0;
                c0_bvalid <= 1;
            end
            if (!cpu1_rst) begin
                if (c1_ibus_cyc && c1_ibus_ack) begin
                    if (!(c1_ibus_addr >= SRAM1_BASE && c1_ibus_addr < SRAM1_BASE + SRAM_BYTES))
                        $fatal(1, "BOOT: CPU1 fetched outside assigned SRAM %h", c1_ibus_addr);
                    c1_inst_count <= c1_inst_count + 1;
                end
                if (c1_dbus_cyc && c1_dbus_ack && c1_dbus_write) begin
                    if (!(c1_dbus_addr >= SRAM1_BASE && c1_dbus_addr < SRAM1_BASE + SRAM_BYTES))
                        $fatal(1, "BOOT: CPU1 data store outside assigned SRAM %h", c1_dbus_addr);
                    if (c1_dbus_select != 4'hf)
                        $fatal(1, "BOOT: CPU1 prototype supports full-word stores addr=%h sel=%h data=%h", c1_dbus_addr, c1_dbus_select, c1_dbus_data);
                    sram1[(c1_dbus_addr-SRAM1_BASE) >> 2] <= c1_dbus_data;
                    if (c1_dbus_addr == SRAM1_BASE + 'h100 && c1_dbus_data == 32'h66)
                        cpu1_app_signature_count <= cpu1_app_signature_count + 1;
                end
            end
        end
    end
endmodule
