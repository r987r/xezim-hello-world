`timescale 1ns/1ps
// Reusable AXI4 master: writes and reads deterministic INCR bursts to every
// configured memory target. The expected data comes from a separate function,
// not from peeking into the RAM model.
module axi_master_bfm #(
    parameter integer MASTER_INDEX = 0,
    parameter integer N_TARGETS = 2,
    parameter integer ADDR_BITS = 64,
    parameter integer DATA_BITS = 64,
    parameter integer ID_BITS = 4,
    parameter integer BURST_BEATS = 4,
    parameter [N_TARGETS-1:0] ENABLED_TARGETS = {N_TARGETS{1'b1}},
    parameter [N_TARGETS*ADDR_BITS-1:0] TARGET_BASES = '0
) (
    input  wire                     clk,
    input  wire                     rst,
    output reg                      done,
    output reg [ID_BITS-1:0]       awid,
    output reg [ADDR_BITS-1:0]     awaddr,
    output reg [7:0]               awlen,
    output reg [2:0]               awsize,
    output reg [1:0]               awburst,
    output reg                     awlock,
    output reg [3:0]               awcache,
    output reg [2:0]               awprot,
    output reg [3:0]               awqos,
    output reg                     awvalid,
    input  wire                    awready,
    output reg [DATA_BITS-1:0]     wdata,
    output reg [(DATA_BITS/8)-1:0] wstrb,
    output reg                     wlast,
    output reg                     wvalid,
    input  wire                    wready,
    input  wire [ID_BITS-1:0]      bid,
    input  wire [1:0]              bresp,
    input  wire                    bvalid,
    output reg                     bready,
    output reg [ID_BITS-1:0]       arid,
    output reg [ADDR_BITS-1:0]     araddr,
    output reg [7:0]               arlen,
    output reg [2:0]               arsize,
    output reg [1:0]               arburst,
    output reg                     arlock,
    output reg [3:0]               arcache,
    output reg [2:0]               arprot,
    output reg [3:0]               arqos,
    output reg                     arvalid,
    input  wire                    arready,
    input  wire [ID_BITS-1:0]      rid,
    input  wire [DATA_BITS-1:0]    rdata,
    input  wire [1:0]              rresp,
    input  wire                    rlast,
    input  wire                    rvalid,
    output reg                     rready
);
    localparam [ID_BITS-1:0] TRANSACTION_ID = ID_BITS'(3);
    localparam [2:0] BEAT_SIZE = $clog2(DATA_BITS/8);

    function automatic [DATA_BITS-1:0] expected_data(input integer target, input integer beat);
        expected_data = DATA_BITS'(64'hc0de0000_00000000 ^
                                    (64'(MASTER_INDEX) << 32) ^
                                    (64'(target) << 16) ^
                                    64'(beat * 13 + 7));
    endfunction

    task automatic send_write(input [ADDR_BITS-1:0] addr, input integer target);
        integer beat;
        begin
            @(negedge clk);
            awid = TRANSACTION_ID;
            awaddr = addr;
            awlen = 8'(BURST_BEATS - 1);
            awsize = BEAT_SIZE;
            awburst = 2'b01;
            awvalid = 1;
            do @(posedge clk); while (awready !== 1'b1);
            @(negedge clk);
            awvalid = 0;

            for (beat = 0; beat < BURST_BEATS; beat = beat + 1) begin
                wdata = expected_data(target, beat);
                wstrb = '1;
                wlast = (beat == BURST_BEATS - 1);
                wvalid = 1;
                do @(posedge clk); while (wready !== 1'b1);
                @(negedge clk);
                wvalid = 0;
            end
            bready = 1;
            do @(posedge clk); while (bvalid !== 1'b1);
            if (bresp !== 2'b00 || bid !== TRANSACTION_ID)
                $fatal(1, "FAIL AXI write response: master=%0d target=%0d bid=%h resp=%h", MASTER_INDEX, target, bid, bresp);
            @(negedge clk);
            bready = 0;
        end
    endtask

    task automatic check_read(input [ADDR_BITS-1:0] addr, input integer target);
        integer beat;
        reg [DATA_BITS-1:0] expected;
        begin
            @(negedge clk);
            arid = TRANSACTION_ID;
            araddr = addr;
            arlen = 8'(BURST_BEATS - 1);
            arsize = BEAT_SIZE;
            arburst = 2'b01;
            arvalid = 1;
            do @(posedge clk); while (arready !== 1'b1);
            @(negedge clk);
            arvalid = 0;
            rready = 1;
            for (beat = 0; beat < BURST_BEATS; beat = beat + 1) begin
                do @(posedge clk); while (rvalid !== 1'b1);
                expected = expected_data(target, beat);
                if ($test$plusargs("INJECT_BAD_EXPECTED") && MASTER_INDEX == 0 && target == 0 && beat == 0)
                    expected = expected ^ DATA_BITS'(1);
                if (rdata !== expected || rid !== TRANSACTION_ID || rresp !== 2'b00 ||
                    rlast !== (beat == BURST_BEATS - 1))
                    $fatal(1, "FAIL AXI read: master=%0d target=%0d beat=%0d got=%h expected=%h rid=%h resp=%h last=%b", MASTER_INDEX, target, beat, rdata, expected, rid, rresp, rlast);
                @(negedge clk);
            end
            rready = 0;
        end
    endtask

    integer target;
    reg [ADDR_BITS-1:0] addr;
    initial begin
        done = 0;
        awid = 0; awaddr = 0; awlen = 0; awsize = 0; awburst = 0;
        awlock = 0; awcache = 0; awprot = 0; awqos = 0; awvalid = 0;
        wdata = 0; wstrb = 0; wlast = 0; wvalid = 0; bready = 0;
        arid = 0; araddr = 0; arlen = 0; arsize = 0; arburst = 0;
        arlock = 0; arcache = 0; arprot = 0; arqos = 0; arvalid = 0; rready = 0;
        wait (!rst);
        repeat (3) @(negedge clk);
        for (target = 0; target < N_TARGETS; target = target + 1) if (ENABLED_TARGETS[target]) begin
            // Unique location per master avoids a false pass from racing writes.
            addr = TARGET_BASES[target*ADDR_BITS +: ADDR_BITS] + ADDR_BITS'(256 + MASTER_INDEX*256);
            send_write(addr, target);
            check_read(addr, target);
            $display("COVER AXI master=%0d target=%0d burst_beats=%0d", MASTER_INDEX, target, BURST_BEATS);
        end
        done = 1;
    end
endmodule
