`timescale 1ns/1ps
// Address decoder for the bootstrap local fabric. Reused for AXI-Lite AR/AW.
// One-hot targets; unmapped traffic is rejected by the bus responder.
// Address maps are parameterized and bound to the same configuration as boot.
module boot_local_decode #(
    parameter [31:0] ROM_BASE = 32'h00000000,
    parameter [31:0] FLASH_BASE = 32'h20000000,
    parameter [31:0] SRAM0_BASE = 32'h10000000,
    parameter [31:0] SRAM1_BASE = 32'h11000000,
    parameter [31:0] RESET_BASE = 32'h40020000,
    parameter integer SRAM_BYTES = 16384
)(
    input wire [31:0] addr,
    output wire [4:0] select_target
);
    // [0] ROM, [1] flash, [2] SRAM0, [3] SRAM1, [4] reset CSR
    assign select_target[0] = (addr >= ROM_BASE && addr < ROM_BASE + 4096);
    assign select_target[1] = (addr >= FLASH_BASE && addr < FLASH_BASE + 65536);
    assign select_target[2] = (addr >= SRAM0_BASE && addr < SRAM0_BASE + SRAM_BYTES);
    assign select_target[3] = (addr >= SRAM1_BASE && addr < SRAM1_BASE + SRAM_BYTES);
    assign select_target[4] = (addr == RESET_BASE);
endmodule
