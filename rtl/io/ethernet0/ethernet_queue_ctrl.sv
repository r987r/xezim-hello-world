// Ethernet0 queue-control V1: programmable RX/TX descriptor ring ownership.
// Simulation/RTL queue control only. Not a DMA engine, SRAM, AXI-Lite bridge,
// header parser, MAC, or completion-memory writer.
// All register offsets and descriptor formats are defined by eth_queue_abi.h.
module ethernet_queue_ctrl #(
    parameter integer RX_QUEUES = 1,
    parameter integer TX_QUEUES = 1,
    parameter integer POLICY_ENTRIES = 4,
    parameter integer RING_LOG2 = 4,
    parameter integer QID_WIDTH = (RX_QUEUES > TX_QUEUES ?
                         (RX_QUEUES > 1 ? $clog2(RX_QUEUES) : 1) :
                         (TX_QUEUES > 1 ? $clog2(TX_QUEUES) : 1))
) (
    input  wire                  clk,
    input  wire                  rst,

    // Minimal CSR handshake, suitable for one reviewed AXI-Lite bridge later.
    // One valid cycle is one operation; ready is combinational. Word aligned.
    input  wire                  cfg_valid,
    input  wire                  cfg_write,
    input  wire [7:0]            cfg_addr,
    input  wire [31:0]           cfg_wdata,
    input  wire [3:0]            cfg_wstrb,
    output wire                  cfg_ready,
    output logic [31:0]          cfg_rdata,
    output logic                 cfg_error,

    // Receive metadata must describe a fully buffered, FCS-checked frame.
    // Real header parsing and packet-stream gating are separate follow-ons.
    input  wire                  rx_meta_valid,
    output wire                  rx_meta_ready,
    input  wire [15:0]           rx_ethertype,
    input  wire                  rx_is_udp,
    input  wire [15:0]           rx_udp_dst_port,
    output logic                 rx_route_valid,
    output logic                 rx_route_drop,
    output logic [QID_WIDTH-1:0] rx_route_queue,
    output logic [7:0]           rx_route_policy,

    // Descriptor fetcher request; address refers to *ring entry*, not packet
    // destination. The fetcher validates the descriptor before DMA starts.
    output wire                  rx_desc_valid,
    input  wire                  rx_desc_ready,
    output wire [63:0]           rx_desc_addr,
    output wire [QID_WIDTH-1:0]  rx_desc_queue,
    output wire                  tx_desc_valid,
    input  wire                  tx_desc_ready,
    output wire [63:0]           tx_desc_addr,
    output wire [QID_WIDTH-1:0]  tx_desc_queue,

    // Commit events mean the completion record has been written to memory
    // AND the corresponding RX AXI B / TX MAC completion has been verified.
    // No completion ring DMA is implemented inside this module.
    input  wire                  rx_cpl_written,
    input  wire                  tx_cpl_written,
    output wire                  irq,
    // Queue-owned completion slots; never derive these in the DMA shim.
    output wire [63:0]           rx_cq_slot_addr,
    output wire [63:0]           tx_cq_slot_addr,
    output wire [7:0]            rx_active_policy_o
);
    localparam integer RING_DEPTH = 1 << RING_LOG2;
    localparam integer DESC_BYTES = 32;
    localparam logic [31:0] RING_MASK = RING_DEPTH - 1;
    localparam integer QMAX = RX_QUEUES > TX_QUEUES ? RX_QUEUES : TX_QUEUES;

    // Sticky error bits: multi-match, no-buffer, invalid CSR, bad completion,
    // no-rule, completion-ring full, malformed queue policy.
    localparam [31:0] ERR_MULTI = 32'h01;
    localparam [31:0] ERR_NO_BUF = 32'h02;
    localparam [31:0] ERR_CONFIG = 32'h04;
    localparam [31:0] ERR_COMPLETION = 32'h08;
    localparam [31:0] ERR_NO_MATCH = 32'h10;
    localparam [31:0] ERR_CQ_FULL = 32'h20;
    localparam [31:0] ERR_BAD_QUEUE = 32'h40;

    logic [1:0] enabled;
    logic [7:0] qsel, psel;
    logic [31:0] errors, irq_status, drop_count, multi_count;

    logic [63:0] rx_base [0:RX_QUEUES-1];
    logic [63:0] tx_base [0:TX_QUEUES-1];
    logic [63:0] rx_cq_base [0:RX_QUEUES-1];
    logic [63:0] tx_cq_base [0:TX_QUEUES-1];
    logic [31:0] rx_prod [0:RX_QUEUES-1], rx_cons [0:RX_QUEUES-1];
    logic [31:0] tx_prod [0:TX_QUEUES-1], tx_cons [0:TX_QUEUES-1];
    logic [31:0] rx_cq_prod [0:RX_QUEUES-1], rx_cq_cons [0:RX_QUEUES-1];
    logic [31:0] tx_cq_prod [0:TX_QUEUES-1], tx_cq_cons [0:TX_QUEUES-1];

    logic [15:0] policy_eth [0:POLICY_ENTRIES-1];
    logic [15:0] policy_eth_mask [0:POLICY_ENTRIES-1];
    logic [15:0] policy_udp [0:POLICY_ENTRIES-1];
    logic [15:0] policy_udp_mask [0:POLICY_ENTRIES-1];
    logic [15:0] policy_cfg [0:POLICY_ENTRIES-1];

    logic rx_fetch, rx_busy, tx_busy;
    logic [QID_WIDTH-1:0] rx_active_q, tx_active_q;
    logic [7:0] rx_active_policy;
    logic [QID_WIDTH-1:0] tx_pick;
    logic tx_pick_valid;
    integer match_count;
    logic [QID_WIDTH-1:0] matched_q;
    logic [7:0] matched_policy;
    logic matched_drop;
    logic matched_invalid;
    integer i, j;

    initial begin
        if (RX_QUEUES < 1 || RX_QUEUES > 8 ||
            TX_QUEUES < 1 || TX_QUEUES > 8 ||
            POLICY_ENTRIES < 1 || POLICY_ENTRIES > 16 ||
            RING_LOG2 < 1 || RING_LOG2 > 8 ||
            QMAX > (1 << QID_WIDTH)) begin
            $fatal(1, "unsupported Ethernet queue parameters");
        end
    end

    assign cfg_ready = 1'b1;
    assign irq = |(irq_status[1:0]);
    assign rx_cq_slot_addr = rx_cq_base[rx_active_q] +
        ({32'd0, (rx_cq_prod[rx_active_q] & RING_MASK)} * DESC_BYTES);
    assign tx_cq_slot_addr = tx_cq_base[tx_active_q] +
        ({32'd0, (tx_cq_prod[tx_active_q] & RING_MASK)} * DESC_BYTES);
    assign rx_active_policy_o = rx_active_policy;
    assign rx_meta_ready = enabled[0] && !rx_fetch && !rx_busy;
    assign rx_desc_valid = rx_fetch;
    assign rx_desc_queue = rx_active_q;
    assign rx_desc_addr = rx_base[rx_active_q] +
                     (({32'd0, (rx_cons[rx_active_q] & RING_MASK)}) * DESC_BYTES);

    // One receive and one transmit operation can be outstanding concurrently.
    // A future implementation can add an in-flight tag table without changing
    // the ring ABI. Completion counters are never advanced on mere DMA issue.
    always @* begin
        match_count = 0;
        matched_q = '0;
        matched_policy = '0;
        matched_drop = 1'b1;
        matched_invalid = 1'b0;
        for (integer k=0; k<POLICY_ENTRIES; k=k+1) begin
            if (policy_cfg[k][0] &&
                ((rx_ethertype ^ policy_eth[k]) & policy_eth_mask[k]) == 0 &&
                (!policy_cfg[k][1] ||
                    (rx_is_udp &&
                    (((rx_udp_dst_port ^ policy_udp[k]) &
                        policy_udp_mask[k]) == 0)))) begin
                match_count = match_count + 1;
                matched_q = policy_cfg[k][8 +: QID_WIDTH];
                matched_policy = k;
                matched_drop = policy_cfg[k][2];
                if ((policy_cfg[k] >> 8) >= RX_QUEUES)
                    matched_invalid = 1'b1;
            end
        end
    end

    // Fixed-priority TX descriptor selection is sufficient for one queue;
    // round-robin fairness is required before raising TX_QUEUES above one.
    always @* begin
        tx_pick_valid = 1'b0;
        tx_pick = '0;
        for (integer k=0; k<TX_QUEUES; k=k+1) begin
            if (!tx_pick_valid && enabled[1] && !tx_busy &&
                tx_base[k] != 0 && tx_prod[k] != tx_cons[k] &&
                (tx_cq_prod[k] - tx_cq_cons[k]) < RING_DEPTH) begin
                tx_pick_valid = 1'b1;
                tx_pick = k;
            end
        end
    end
    assign tx_desc_valid = tx_pick_valid;
    assign tx_desc_queue = tx_pick;
    assign tx_desc_addr = tx_base[tx_pick] +
                  (({32'd0, (tx_cons[tx_pick] & RING_MASK)}) * DESC_BYTES);

    // CSR reads are non-destructive; software must explicitly retire CQ
    // entries by advancing the appropriate completion-consumer pointer.
    always @* begin
        cfg_rdata = 32'd0;
        cfg_error = 1'b0;
        case (cfg_addr)
            8'h00: cfg_rdata = 32'h45544851; // ETHQ
            8'h04: cfg_rdata = 32'h00010000; // ABI major 1 minor 0
            8'h08: cfg_rdata = {30'd0, enabled};
            8'h0c: cfg_rdata = {8'(POLICY_ENTRIES), 8'(RING_LOG2),
                               8'(TX_QUEUES), 8'(RX_QUEUES)};
            8'h10: cfg_rdata = {24'd0, qsel};
            8'h20: if (qsel < RX_QUEUES) cfg_rdata = rx_base[qsel][31:0];
                    else cfg_error = 1;
            8'h24: if (qsel < RX_QUEUES) cfg_rdata = rx_base[qsel][63:32];
                    else cfg_error = 1;
            8'h28: if (qsel < RX_QUEUES) cfg_rdata = rx_prod[qsel];
                    else cfg_error = 1;
            8'h2c: if (qsel < RX_QUEUES) cfg_rdata = rx_cons[qsel];
                    else cfg_error = 1;
            8'h30: if (qsel < RX_QUEUES) cfg_rdata = rx_cq_base[qsel][31:0];
                    else cfg_error = 1;
            8'h34: if (qsel < RX_QUEUES) cfg_rdata = rx_cq_base[qsel][63:32];
                    else cfg_error = 1;
            8'h38: if (qsel < RX_QUEUES) cfg_rdata = rx_cq_prod[qsel];
                    else cfg_error = 1;
            8'h3c: if (qsel < RX_QUEUES) cfg_rdata = rx_cq_cons[qsel];
                    else cfg_error = 1;
            8'h40: if (qsel < TX_QUEUES) cfg_rdata = tx_base[qsel][31:0];
                    else cfg_error = 1;
            8'h44: if (qsel < TX_QUEUES) cfg_rdata = tx_base[qsel][63:32];
                    else cfg_error = 1;
            8'h48: if (qsel < TX_QUEUES) cfg_rdata = tx_prod[qsel];
                    else cfg_error = 1;
            8'h4c: if (qsel < TX_QUEUES) cfg_rdata = tx_cons[qsel];
                    else cfg_error = 1;
            8'h50: if (qsel < TX_QUEUES) cfg_rdata = tx_cq_base[qsel][31:0];
                    else cfg_error = 1;
            8'h54: if (qsel < TX_QUEUES) cfg_rdata = tx_cq_base[qsel][63:32];
                    else cfg_error = 1;
            8'h58: if (qsel < TX_QUEUES) cfg_rdata = tx_cq_prod[qsel];
                    else cfg_error = 1;
            8'h5c: if (qsel < TX_QUEUES) cfg_rdata = tx_cq_cons[qsel];
                    else cfg_error = 1;
            8'h70: cfg_rdata = {24'd0, psel};
            8'h74: if (psel < POLICY_ENTRIES) cfg_rdata = {16'd0,policy_eth[psel]};
                    else cfg_error = 1;
            8'h78: if (psel < POLICY_ENTRIES) cfg_rdata = {16'd0,policy_eth_mask[psel]};
                    else cfg_error = 1;
            8'h7c: if (psel < POLICY_ENTRIES) cfg_rdata = {16'd0,policy_udp[psel]};
                    else cfg_error = 1;
            8'h80: if (psel < POLICY_ENTRIES) cfg_rdata = {16'd0,policy_udp_mask[psel]};
                    else cfg_error = 1;
            8'h84: if (psel < POLICY_ENTRIES) cfg_rdata = {16'd0,policy_cfg[psel]};
                    else cfg_error = 1;
            8'h90: cfg_rdata = irq_status;
            8'h94: cfg_rdata = errors;
            8'h98: cfg_rdata = drop_count;
            8'h9c: cfg_rdata = multi_count;
            8'ha0: cfg_rdata = {29'd0, tx_busy, rx_busy, rx_fetch};
            default: cfg_error = 1;
        endcase
        if (cfg_addr[1:0] != 0) cfg_error = 1'b1;
        if (cfg_valid && cfg_write) begin
            if (cfg_wstrb != 4'hf ||
                cfg_addr == 8'h00 || cfg_addr == 8'h04 ||
                cfg_addr == 8'h0c || cfg_addr == 8'h2c ||
                cfg_addr == 8'h38 || cfg_addr == 8'h4c ||
                cfg_addr == 8'h58 || cfg_addr == 8'h98 ||
                cfg_addr == 8'h9c || cfg_addr == 8'ha0) cfg_error = 1;
            if ((cfg_addr == 8'h08) && ((cfg_wdata & ~32'd3) != 0))
                cfg_error = 1;
            if (cfg_addr == 8'h10 && cfg_wdata >= QMAX) cfg_error = 1;
            if (cfg_addr == 8'h70 && cfg_wdata >= POLICY_ENTRIES)
                cfg_error = 1;
            if (cfg_addr >= 8'h74 && cfg_addr <= 8'h84 &&
                (enabled != 0 || rx_fetch || rx_busy)) cfg_error = 1;
            if (cfg_addr == 8'h84 && cfg_wdata[0] &&
                (cfg_wdata >> 8) >= RX_QUEUES) cfg_error = 1;
            if (((cfg_addr >= 8'h20 && cfg_addr <= 8'h24) ||
                 (cfg_addr >= 8'h30 && cfg_addr <= 8'h34) ||
                 (cfg_addr >= 8'h40 && cfg_addr <= 8'h44) ||
                 (cfg_addr >= 8'h50 && cfg_addr <= 8'h54)) &&
                enabled != 0) cfg_error = 1;
            if (cfg_addr == 8'h28 && qsel < RX_QUEUES &&
                (cfg_wdata - rx_cons[qsel]) > RING_DEPTH) cfg_error = 1;
            if (cfg_addr == 8'h48 && qsel < TX_QUEUES &&
                (cfg_wdata - tx_cons[qsel]) > RING_DEPTH) cfg_error = 1;
            if (cfg_addr == 8'h3c && qsel < RX_QUEUES &&
                (cfg_wdata - rx_cq_cons[qsel]) >
                (rx_cq_prod[qsel] - rx_cq_cons[qsel])) cfg_error = 1;
            if (cfg_addr == 8'h5c && qsel < TX_QUEUES &&
                (cfg_wdata - tx_cq_cons[qsel]) >
                (tx_cq_prod[qsel] - tx_cq_cons[qsel])) cfg_error = 1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            enabled <= 0;
            qsel <= 0;
            psel <= 0;
            errors <= 0;
            irq_status <= 0;
            drop_count <= 0;
            multi_count <= 0;
            rx_fetch <= 0;
            rx_busy <= 0;
            tx_busy <= 0;
            rx_active_q <= '0;
            tx_active_q <= '0;
            rx_active_policy <= 0;
            rx_route_valid <= 0;
            rx_route_drop <= 1;
            rx_route_queue <= '0;
            rx_route_policy <= 0;
            for (i=0; i<RX_QUEUES; i=i+1) begin
                rx_base[i] <= 0; rx_cq_base[i] <= 0;
                rx_prod[i] <= 0; rx_cons[i] <= 0;
                rx_cq_prod[i] <= 0; rx_cq_cons[i] <= 0;
            end
            for (i=0; i<TX_QUEUES; i=i+1) begin
                tx_base[i] <= 0; tx_cq_base[i] <= 0;
                tx_prod[i] <= 0; tx_cons[i] <= 0;
                tx_cq_prod[i] <= 0; tx_cq_cons[i] <= 0;
            end
            for (j=0; j<POLICY_ENTRIES; j=j+1) begin
                policy_eth[j] <= 0; policy_eth_mask[j] <= 0;
                policy_udp[j] <= 0; policy_udp_mask[j] <= 0;
                policy_cfg[j] <= 0;
            end
        end else begin
            rx_route_valid <= 0;
            // CPU writes. Validation happens before any state is changed.
            if (cfg_valid && cfg_write) begin
                if (cfg_error) errors <= errors | ERR_CONFIG;
                else case (cfg_addr)
                    8'h08: enabled <= cfg_wdata[1:0];
                    8'h10: qsel <= cfg_wdata[7:0];
                    8'h20: rx_base[qsel][31:0] <= cfg_wdata;
                    8'h24: rx_base[qsel][63:32] <= cfg_wdata;
                    8'h28: rx_prod[qsel] <= cfg_wdata;
                    8'h30: rx_cq_base[qsel][31:0] <= cfg_wdata;
                    8'h34: rx_cq_base[qsel][63:32] <= cfg_wdata;
                    8'h3c: rx_cq_cons[qsel] <= cfg_wdata;
                    8'h40: tx_base[qsel][31:0] <= cfg_wdata;
                    8'h44: tx_base[qsel][63:32] <= cfg_wdata;
                    8'h48: tx_prod[qsel] <= cfg_wdata;
                    8'h50: tx_cq_base[qsel][31:0] <= cfg_wdata;
                    8'h54: tx_cq_base[qsel][63:32] <= cfg_wdata;
                    8'h5c: tx_cq_cons[qsel] <= cfg_wdata;
                    8'h70: psel <= cfg_wdata[7:0];
                    8'h74: policy_eth[psel] <= cfg_wdata[15:0];
                    8'h78: policy_eth_mask[psel] <= cfg_wdata[15:0];
                    8'h7c: policy_udp[psel] <= cfg_wdata[15:0];
                    8'h80: policy_udp_mask[psel] <= cfg_wdata[15:0];
                    8'h84: policy_cfg[psel] <= cfg_wdata[15:0];
                    8'h90: irq_status <= irq_status & ~cfg_wdata;
                    8'h94: errors <= errors & ~cfg_wdata;
                    default: errors <= errors | ERR_CONFIG;
                endcase
            end
            if (rx_meta_valid && rx_meta_ready) begin
                rx_route_valid <= 1'b1;
                rx_route_queue <= matched_q;
                rx_route_policy <= matched_policy;
                rx_route_drop <= 1'b1;
                if (match_count > 1) begin
                    errors <= errors | ERR_MULTI;
                    multi_count <= multi_count + 1;
                    drop_count <= drop_count + 1;
                end else if (match_count == 0) begin
                    errors <= errors | ERR_NO_MATCH;
                    drop_count <= drop_count + 1;
                end else if (matched_invalid) begin
                    errors <= errors | ERR_BAD_QUEUE;
                    drop_count <= drop_count + 1;
                end else if (matched_drop) begin
                    drop_count <= drop_count + 1;
                end else if (rx_base[matched_q] == 0 ||
                             rx_prod[matched_q] == rx_cons[matched_q]) begin
                    errors <= errors | ERR_NO_BUF;
                    drop_count <= drop_count + 1;
                end else if ((rx_cq_prod[matched_q] - rx_cq_cons[matched_q])
                                 >= RING_DEPTH) begin
                    errors <= errors | ERR_CQ_FULL;
                    drop_count <= drop_count + 1;
                end else begin
                    rx_fetch <= 1'b1;
                    rx_active_q <= matched_q;
                    rx_active_policy <= matched_policy;
                    rx_route_drop <= 1'b0;
                end
            end
            if (rx_desc_valid && rx_desc_ready) begin
                rx_cons[rx_active_q] <= rx_cons[rx_active_q] + 1;
                rx_fetch <= 0;
                rx_busy <= 1;
            end
            if (tx_desc_valid && tx_desc_ready) begin
                tx_cons[tx_pick] <= tx_cons[tx_pick] + 1;
                tx_active_q <= tx_pick;
                tx_busy <= 1;
            end
            if (rx_cpl_written) begin
                if (!rx_busy) errors <= errors | ERR_COMPLETION;
                else begin
                    rx_busy <= 0;
                    rx_cq_prod[rx_active_q] <= rx_cq_prod[rx_active_q] + 1;
                    irq_status <= irq_status | 1;
                end
            end
            if (tx_cpl_written) begin
                if (!tx_busy) errors <= errors | ERR_COMPLETION;
                else begin
                    tx_busy <= 0;
                    tx_cq_prod[tx_active_q] <= tx_cq_prod[tx_active_q] + 1;
                    irq_status <= irq_status | 2;
                end
            end
        end
    end
endmodule
