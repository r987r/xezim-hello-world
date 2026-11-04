// Generated from config/soc.yaml; do not edit.
package boot_config_pkg;
    localparam logic [31:0] BOOTROM_BASE = 32'h00000000;
    localparam logic [31:0] FLASH_BASE = 32'h20000000;
    localparam logic [31:0] SRAM0_BASE = 32'h10000000;
    localparam logic [31:0] SRAM1_BASE = 32'h11000000;
    localparam logic [31:0] RESET_CTRL_BASE = 32'h40020000;
    localparam integer SRAM_BYTES = 16384;
    localparam integer PROGRAM_WORDS = 4;
    localparam integer FLASH_SLOT_WORDS = 64;
endpackage
