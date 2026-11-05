// Physical SoC AXI address/burst checker for the opt-in LiteDRAM backend.
// Isolated helper: NO AXI handshake, response or DDR init logic in this module.
// The future protocol adapter MUST use fault_o to return legal DECERR, not
// silently hang/rewrite addresses or forward illegal requests.
module ddr_litedram_axi_aperture_guard #(
    parameter int unsigned LOCAL_ADDR_WIDTH = 32,
    parameter logic [63:0] BASE = 64'h0000_0001_4000_0000,
    parameter logic [63:0] ARCH_BYTES = 64'h0000_0000_4000_0000,
    parameter logic [63:0] MODEL_BYTES = 64'h0000_0000_0200_0000
) (
    input  logic [63:0] phys_addr_i,
    input  logic [7:0]  axlen_i,
    input  logic [2:0]  axsize_i,
    input  logic [1:0]  axburst_i,
    input  logic [5:0]  atop_i,
    output logic [LOCAL_ADDR_WIDTH-1:0] local_addr_o,
    output logic        allow_o,
    output logic [2:0]  fault_o
);
    localparam logic [2:0] FAULT_NONE = 3'd0;
    localparam logic [2:0] FAULT_ATOMIC = 3'd1;
    localparam logic [2:0] FAULT_BURST = 3'd2;
    localparam logic [2:0] FAULT_ARCH_WINDOW = 3'd3;
    localparam logic [2:0] FAULT_MODEL_WINDOW = 3'd4;
    localparam logic [2:0] FAULT_4K = 3'd5;
    localparam logic [2:0] FAULT_LOCAL_ADDR = 3'd6;

    logic [64:0] byte_count;
    logic [64:0] end_exclusive;
    logic [64:0] offset;
    logic [64:0] arch_end;
    logic [64:0] model_end;

    always_comb begin
        byte_count = (65'(axlen_i) + 65'd1) << axsize_i;
        end_exclusive = {1'b0, phys_addr_i} + byte_count;
        offset = {1'b0, phys_addr_i} - {1'b0, BASE};
        arch_end = {1'b0, BASE} + {1'b0, ARCH_BYTES};
        model_end = {1'b0, BASE} + {1'b0, MODEL_BYTES};
        allow_o = 1'b0;
        local_addr_o = '0;
        fault_o = FAULT_NONE;

        if (atop_i != 0) begin
            fault_o = FAULT_ATOMIC;
        end else if (axburst_i != 2'b01 || axsize_i > 3'd3) begin
            fault_o = FAULT_BURST;
        end else if (phys_addr_i < BASE || end_exclusive > arch_end ||
                     end_exclusive[64]) begin
            fault_o = FAULT_ARCH_WINDOW;
        end else if (end_exclusive > model_end) begin
            fault_o = FAULT_MODEL_WINDOW;
        end else if (phys_addr_i[63:12] != (end_exclusive - 65'd1) >> 12) begin
            fault_o = FAULT_4K;
        end else if (offset[64:LOCAL_ADDR_WIDTH] != '0 ||
                     (offset + byte_count) > (65'd1 << LOCAL_ADDR_WIDTH)) begin
            fault_o = FAULT_LOCAL_ADDR;
        end else begin
            local_addr_o = offset[LOCAL_ADDR_WIDTH-1:0];
            allow_o = 1'b1;
        end
    end

    initial begin
        assert (LOCAL_ADDR_WIDTH >= 1 && LOCAL_ADDR_WIDTH <= 32)
            else $fatal(1, "invalid LiteDRAM local address width");
        assert (MODEL_BYTES > 0 && MODEL_BYTES <= ARCH_BYTES)
            else $fatal(1, "modeled storage cannot exceed DDR aperture");
        assert ((MODEL_BYTES & (MODEL_BYTES-64'd1)) == 0)
            else $fatal(1, "DDR model capacity must be power of two");
    end
endmodule
