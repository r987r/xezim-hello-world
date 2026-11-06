/*
 * Ethernet completion-ring AXI write adapter.
 *
 * Reuses pinned MIT verilog-axi axi_dma_wr. It emits the shared 32-byte
 * ethq_completion_t record as four 64-bit AXI-Stream words. Successful
 * cpl_written is pulsed ONLY after the upstream DMA confirms AXI B response.
 * No homegrown AXI write datapath, crossbar, or completion RAM.
 *
 * This module is a standalone source building block. The queue controller
 * still needs to wire its CQ slot address and packet result to req_*.
 */
`timescale 1ns/1ps
`default_nettype none

module ethernet_cq_axi_writer #(
    parameter [63:0] REGION_BASE = 0,
    parameter [63:0] REGION_BYTES = 65536,
    parameter integer AXI_ID_WIDTH = 4
) (
    input  wire clk,
    input  wire rst,
    input  wire req_valid,
    output wire req_ready,
    input  wire [63:0] req_addr,
    input  wire [31:0] req_cookie,
    input  wire [31:0] req_length,
    input  wire [31:0] req_status,
    input  wire [31:0] req_policy,
    input  wire [31:0] req_queue,
    input  wire [7:0]  req_tag,
    output reg cpl_done_valid,
    output reg cpl_written,
    output reg [3:0] cpl_error,
    output reg [7:0] cpl_tag,

    output wire [AXI_ID_WIDTH-1:0] m_axi_awid,
    output wire [63:0] m_axi_awaddr,
    output wire [7:0] m_axi_awlen,
    output wire [2:0] m_axi_awsize,
    output wire [1:0] m_axi_awburst,
    output wire m_axi_awlock,
    output wire [3:0] m_axi_awcache,
    output wire [2:0] m_axi_awprot,
    output wire m_axi_awvalid,
    input  wire m_axi_awready,
    output wire [63:0] m_axi_wdata,
    output wire [7:0] m_axi_wstrb,
    output wire m_axi_wlast,
    output wire m_axi_wvalid,
    input  wire m_axi_wready,
    input  wire [AXI_ID_WIDTH-1:0] m_axi_bid,
    input  wire [1:0] m_axi_bresp,
    input  wire m_axi_bvalid,
    output wire m_axi_bready
);
    localparam [1:0] IDLE=0, SEND=1, WAIT_B=2;
    localparam [3:0] BAD_DESC=4'h8, BAD_DMA=4'hf;
    reg [1:0] state=IDLE;
    reg [1:0] beat=0;
    reg [31:0] saved_cookie=0, saved_length=0, saved_status=0;
    reg [31:0] saved_policy=0, saved_queue=0;
    reg [7:0] saved_tag=0;
    wire valid_range = req_addr >= REGION_BASE &&
        REGION_BYTES >= 32 &&
        req_addr - REGION_BASE <= REGION_BYTES - 32 &&
        (req_addr & 64'h1f) == 0;
    wire dma_desc_ready, dma_data_ready, dma_status_valid;
    wire [3:0] dma_status_error;
    wire [19:0] dma_status_length;
    wire [7:0] dma_status_tag;
    wire dma_desc_valid = state == IDLE && req_valid && valid_range;
    assign req_ready = state == IDLE && (valid_range ? dma_desc_ready : 1'b1);
    wire dma_data_valid = state == SEND;
    wire [63:0] payload =
        beat == 0 ? {32'd0, saved_cookie} :
        beat == 1 ? {saved_status, saved_length} :
        beat == 2 ? {saved_queue, saved_policy} :
                    64'd0;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            beat <= 0;
            saved_tag <= 0;
            saved_cookie <= 0;
            saved_length <= 0;
            saved_status <= 0;
            saved_policy <= 0;
            saved_queue <= 0;
            cpl_done_valid <= 0;
            cpl_written <= 0;
            cpl_error <= 0;
            cpl_tag <= 0;
        end else begin
            cpl_done_valid <= 0;
            cpl_written <= 0;
            case (state)
                IDLE: begin
                    if (req_valid && req_ready) begin
                        cpl_tag <= req_tag;
                        if (!valid_range) begin
                            cpl_done_valid <= 1;
                            cpl_error <= BAD_DESC;
                        end else begin
                            beat <= 0;
                            saved_cookie <= req_cookie;
                            saved_length <= req_length;
                            saved_status <= req_status;
                            saved_policy <= req_policy;
                            saved_queue <= req_queue;
                            saved_tag <= req_tag;
                            state <= SEND;
                        end
                    end
                end
                SEND: begin
                    if (dma_data_valid && dma_data_ready) begin
                        if (beat == 3) state <= WAIT_B;
                        else beat <= beat+1;
                    end
                end
                WAIT_B: begin
                    if (dma_status_valid) begin
                        cpl_done_valid <= 1;
                        cpl_tag <= saved_tag;
                        if (dma_status_error != 0) cpl_error <= dma_status_error;
                        else if (dma_status_length != 32 ||
                                 dma_status_tag != saved_tag)
                            cpl_error <= BAD_DMA;
                        else begin
                            cpl_error <= 0;
                            cpl_written <= 1;
                        end
                        state <= IDLE;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end

    axi_dma_wr #(
        .AXI_DATA_WIDTH(64), .AXI_ADDR_WIDTH(64),
        .AXI_STRB_WIDTH(8), .AXI_ID_WIDTH(AXI_ID_WIDTH),
        .AXI_MAX_BURST_LEN(16),
        .AXIS_DATA_WIDTH(64), .AXIS_KEEP_ENABLE(1),
        .AXIS_KEEP_WIDTH(8), .AXIS_LAST_ENABLE(1),
        .AXIS_ID_ENABLE(0), .AXIS_DEST_ENABLE(0),
        .AXIS_USER_ENABLE(1), .AXIS_USER_WIDTH(1),
        .LEN_WIDTH(20), .TAG_WIDTH(8),
        .ENABLE_SG(0), .ENABLE_UNALIGNED(0)
    ) u_upstream_axi_dma_wr (
        .clk(clk), .rst(rst),
        .s_axis_write_desc_addr(req_addr),
        .s_axis_write_desc_len(20'd32),
        .s_axis_write_desc_tag(req_tag),
        .s_axis_write_desc_valid(dma_desc_valid),
        .s_axis_write_desc_ready(dma_desc_ready),
        .m_axis_write_desc_status_len(dma_status_length),
        .m_axis_write_desc_status_tag(dma_status_tag),
        .m_axis_write_desc_status_id(),
        .m_axis_write_desc_status_dest(),
        .m_axis_write_desc_status_user(),
        .m_axis_write_desc_status_error(dma_status_error),
        .m_axis_write_desc_status_valid(dma_status_valid),
        .s_axis_write_data_tdata(payload),
        .s_axis_write_data_tkeep(8'hff),
        .s_axis_write_data_tvalid(dma_data_valid),
        .s_axis_write_data_tready(dma_data_ready),
        .s_axis_write_data_tlast(beat == 3),
        .s_axis_write_data_tid(8'd0),
        .s_axis_write_data_tdest(8'd0),
        .s_axis_write_data_tuser(1'b0),
        .m_axi_awid(m_axi_awid),
        .m_axi_awaddr(m_axi_awaddr),
        .m_axi_awlen(m_axi_awlen),
        .m_axi_awsize(m_axi_awsize),
        .m_axi_awburst(m_axi_awburst),
        .m_axi_awlock(m_axi_awlock),
        .m_axi_awcache(m_axi_awcache),
        .m_axi_awprot(m_axi_awprot),
        .m_axi_awvalid(m_axi_awvalid),
        .m_axi_awready(m_axi_awready),
        .m_axi_wdata(m_axi_wdata),
        .m_axi_wstrb(m_axi_wstrb),
        .m_axi_wlast(m_axi_wlast),
        .m_axi_wvalid(m_axi_wvalid),
        .m_axi_wready(m_axi_wready),
        .m_axi_bid(m_axi_bid),
        .m_axi_bresp(m_axi_bresp),
        .m_axi_bvalid(m_axi_bvalid),
        .m_axi_bready(m_axi_bready),
        .enable(1'b1), .abort(1'b0)
    );
endmodule
`default_nettype wire
