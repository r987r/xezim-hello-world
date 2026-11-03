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
    // Real synthesizable address decoder, separate from the AXI-Lite protocol
    // responder. The selected SRAM banks are independent reusable RTL blocks.
    wire [4:0] read_sel, write_sel;
    boot_local_decode #(
        .ROM_BASE(BOOTROM_BASE), .FLASH_BASE(FLASH_BASE),
        .SRAM0_BASE(SRAM0_BASE), .SRAM1_BASE(SRAM1_BASE),
        .RESET_BASE(RESET_CTRL_BASE), .SRAM_BYTES(SRAM_BYTES)
    ) u_read_decode (.addr(c0_araddr), .select_target(read_sel));
    boot_local_decode #(
        .ROM_BASE(BOOTROM_BASE), .FLASH_BASE(FLASH_BASE),
        .SRAM0_BASE(SRAM0_BASE), .SRAM1_BASE(SRAM1_BASE),
        .RESET_BASE(RESET_CTRL_BASE), .SRAM_BYTES(SRAM_BYTES)
    ) u_write_decode (.addr(pending_awaddr), .select_target(write_sel));

    // SRAM power-up is unspecified. Only CPU0 stores initialize program words.
    reg [31:0] rom [0:1023];
    reg [31:0] flash [0:16383];
    // Distinct, reusable RTL SRAM banks. SRAM bits are NOT reset/preloaded;
    // only CPU0 memory transactions supply firmware in the cold-boot scope.
    wire [31:0] sram0_cpu0_rdata, sram1_cpu0_rdata;
    wire [31:0] sram1_cpu1_rdata;
    wire sram0_cpu0_we, sram1_cpu0_we, sram1_cpu1_we;
    wire [31:0] sram0_cpu0_waddr, sram1_cpu0_waddr;
    wire [31:0] sram0_cpu0_wdata, sram1_cpu0_wdata;
    wire [3:0] sram0_cpu0_wstrb, sram1_cpu0_wstrb;
    assign sram0_cpu0_waddr = pending_awaddr - SRAM0_BASE;
    assign sram1_cpu0_waddr = pending_awaddr - SRAM1_BASE;
    assign sram0_cpu0_wdata = pending_wdata;
    assign sram1_cpu0_wdata = pending_wdata;
    assign sram0_cpu0_wstrb = pending_wstrb;
    assign sram1_cpu0_wstrb = pending_wstrb;
    assign sram0_cpu0_we = !rst && have_aw && have_w && !c0_bvalid &&
        write_sel[2];
    assign sram1_cpu0_we = !rst && have_aw && have_w && !c0_bvalid &&
        write_sel[3];
    assign sram1_cpu1_we = !cpu1_rst && c1_dbus_cyc && c1_dbus_ack &&
        c1_dbus_write && c1_dbus_addr >= SRAM1_BASE && c1_dbus_addr < SRAM1_BASE + SRAM_BYTES;
    local_sram #(.BYTES(SRAM_BYTES)) u_sram0 (
        .clk(clk), .a_read_addr(c0_araddr - SRAM0_BASE),
        .a_rdata(sram0_cpu0_rdata), .a_we(sram0_cpu0_we),
        .a_write_addr(sram0_cpu0_waddr), .a_wdata(sram0_cpu0_wdata),
        .a_wstrb(sram0_cpu0_wstrb),
        .b_read_addr(32'b0), .b_read_en(1'b0), .b_rdata(),
        .b_we(1'b0), .b_write_addr(32'b0), .b_wdata(32'b0), .b_wstrb(4'b0)
    );
    local_sram #(.BYTES(SRAM_BYTES)) u_sram1 (
        .clk(clk), .a_read_addr(c0_araddr - SRAM1_BASE),
        .a_rdata(sram1_cpu0_rdata), .a_we(sram1_cpu0_we),
        .a_write_addr(sram1_cpu0_waddr), .a_wdata(sram1_cpu0_wdata),
        .a_wstrb(sram1_cpu0_wstrb),
        .b_read_addr(c1_ibus_cyc ? c1_ibus_addr-SRAM1_BASE : c1_dbus_addr-SRAM1_BASE),
        .b_read_en(!cpu1_rst), .b_rdata(sram1_cpu1_rdata),
        .b_we(sram1_cpu1_we), .b_write_addr(c1_dbus_addr-SRAM1_BASE),
        .b_wdata(c1_dbus_data), .b_wstrb(c1_dbus_select)
    );
    string rom_file, flash_file;
    initial begin
        for (integer n=0; n<1024; n=n+1) rom[n] = 32'h00000000;
        for (integer n=0; n<16384; n=n+1) flash[n] = 32'h00000000;
        rom_file = BOOTROM_FILE;
        flash_file = FLASH_FILE;
        if ($value$plusargs("BOOTROM_FILE=%s", rom_file)) begin end
        if ($value$plusargs("FLASH_FILE=%s", flash_file)) begin end
        $readmemh(rom_file, rom);
        $readmemh(flash_file, flash);
    end

    reg [31:0] cpu0_read_mux;
    always @* begin
        case (read_sel)
            5'b00001: cpu0_read_mux = rom[(c0_araddr - BOOTROM_BASE) >> 2];
            5'b00010: cpu0_read_mux = flash[(c0_araddr - FLASH_BASE) >> 2];
            5'b00100: cpu0_read_mux = sram0_cpu0_rdata;
            5'b01000: cpu0_read_mux = sram1_cpu0_rdata;
            5'b10000: cpu0_read_mux = {31'b0, cpu1_release};
            default: cpu0_read_mux = 32'bx; // invalid/unmapped, never masquerade as zero
        endcase
    end

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
    assign c1_ibus_rdata = sram1_cpu1_rdata;
    assign c1_dbus_ack   = c1_d_ack_q;
    assign c1_dbus_rdata = sram1_cpu1_rdata;

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
                if (read_sel == 5'b0 || (read_sel & (read_sel-1'b1)) != 5'b0)
                    $fatal(1, "BOOT: unmapped/overlapping CPU0 read %h", c0_araddr);
                c0_rdata <= cpu0_read_mux;
                c0_rvalid <= 1;
                if (c0_araddr >= BOOTROM_BASE && c0_araddr < BOOTROM_BASE + 4096)
                    rom_read_count <= rom_read_count + 1;
                if (c0_araddr >= FLASH_BASE && c0_araddr < FLASH_BASE + 65536)
                    flash_read_count <= flash_read_count + 1;
            end
            if (have_aw && have_w && !c0_bvalid) begin
                if (pending_awaddr[1:0] != 2'b00)
                    $fatal(1, "BOOT: prototype only supports aligned CPU0 stores at %h", pending_awaddr);
                if (write_sel[2]) begin
                    if (pending_awaddr < SRAM0_BASE + 16 && pending_wstrb == 4'hf)
                        sram0_copy_count <= sram0_copy_count + 1;
                    if (pending_awaddr == SRAM0_BASE + 'h100 && pending_wdata == 32'h55 && pending_wstrb == 4'hf)
                        cpu0_app_signature_count <= cpu0_app_signature_count + 1;
                end else if (write_sel[3]) begin
                    if (pending_awaddr < SRAM1_BASE + 16 && pending_wstrb == 4'hf)
                        sram1_copy_count <= sram1_copy_count + 1;
                end else if (write_sel[4]) begin
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
                if (c1_ibus_cyc && c1_dbus_cyc)
                    $fatal(1, "BOOT: concurrent SERV I/D requests require an arbiter");
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
                    if (c1_dbus_addr == SRAM1_BASE + 'h100 && c1_dbus_data == 32'h66)
                        cpu1_app_signature_count <= cpu1_app_signature_count + 1;
                end
            end
        end
    end
endmodule
