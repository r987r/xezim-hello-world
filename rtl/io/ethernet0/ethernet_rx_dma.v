/*
 * Ethernet0 RX: descriptor-checked packet AXIS-to-AXI write bridge.
 *
 * Packet source must hold a COMPLETE verified frame and supply its actual
 * byte length before presenting the descriptor. The upstream unmodified
 * verilog-axi axi_dma_wr performs all AXI write bursts and B-response tracking.
 * There is no standalone descriptor-ring fetch, policy matcher, staging
 * SRAM, completion-memory writer or NoC in this block.
 *
 * Ownership: this is a *data* AXI initiator. The control plane supplies a
 * prevalidated descriptor; it never trusts an Ethernet header as an address.
 */
`timescale 1ns/1ps
`default_nettype none
module ethernet_rx_dma #(
    parameter integer AXI_ADDR_WIDTH = 64,
    parameter integer AXI_DATA_WIDTH = 64,
    parameter integer AXI_ID_WIDTH = 4,
    parameter integer LEN_WIDTH = 16,
    parameter [AXI_ADDR_WIDTH-1:0] REGION_BASE = 0,
    parameter [AXI_ADDR_WIDTH-1:0] REGION_BYTES = 65536,
    // Optional second DMA aperture; must match descriptor fetch region #1.
    parameter [AXI_ADDR_WIDTH-1:0] ALT_REGION_BASE = 0,
    parameter [AXI_ADDR_WIDTH-1:0] ALT_REGION_BYTES = 0
) (
    input  wire clk,
    input  wire rst,
    input  wire desc_valid,
    output wire desc_ready,
    input  wire [AXI_ADDR_WIDTH-1:0] desc_dst_addr,
    input  wire [LEN_WIDTH-1:0] desc_length,
    input  wire [LEN_WIDTH-1:0] desc_capacity,
    input  wire [7:0] desc_tag,
    output reg  status_valid,
    output reg  status_ok,
    output reg  [3:0] status_error,
    output reg  [7:0] status_tag,
    output reg  [LEN_WIDTH-1:0] status_length,

    input  wire [AXI_DATA_WIDTH-1:0] s_axis_tdata,
    input  wire [AXI_DATA_WIDTH/8-1:0] s_axis_tkeep,
    input  wire s_axis_tvalid,
    output wire s_axis_tready,
    input  wire s_axis_tlast,
    input  wire s_axis_tuser,

    output wire [AXI_ID_WIDTH-1:0] m_axi_awid,
    output wire [AXI_ADDR_WIDTH-1:0] m_axi_awaddr,
    output wire [7:0] m_axi_awlen,
    output wire [2:0] m_axi_awsize,
    output wire [1:0] m_axi_awburst,
    output wire m_axi_awlock,
    output wire [3:0] m_axi_awcache,
    output wire [2:0] m_axi_awprot,
    output wire m_axi_awvalid,
    input  wire m_axi_awready,
    output wire [AXI_DATA_WIDTH-1:0] m_axi_wdata,
    output wire [AXI_DATA_WIDTH/8-1:0] m_axi_wstrb,
    output wire m_axi_wlast,
    output wire m_axi_wvalid,
    input  wire m_axi_wready,
    input  wire [AXI_ID_WIDTH-1:0] m_axi_bid,
    input  wire [1:0] m_axi_bresp,
    input  wire m_axi_bvalid,
    output wire m_axi_bready
);
    localparam [3:0] ERR_BAD_DESC = 4'h8;
    localparam [3:0] ERR_LENGTH = 4'h9;
    localparam [3:0] ERR_FRAME = 4'ha;

    // Only one active frame. A full-frame buffer must precede this adapter.
    localparam [1:0] IDLE=0, SEND=1, WAIT_B=2;
    reg [1:0] state=IDLE;
    reg [LEN_WIDTH-1:0] expected_len=0;
    reg [7:0] active_tag=0;
    reg bad_stream=0;
    wire dma_desc_ready;
    wire [LEN_WIDTH-1:0] dma_status_len;
    wire [7:0] dma_status_tag;
    wire [3:0] dma_status_error;
    wire dma_status_valid;
    wire dma_data_ready;
    wire dma_desc_valid;

    wire primary_range = (desc_dst_addr >= REGION_BASE) &&
        (REGION_BYTES >= desc_length) &&
        (desc_dst_addr - REGION_BASE <= REGION_BYTES - desc_length);
    wire alt_range = ALT_REGION_BYTES != 0 &&
        desc_dst_addr >= ALT_REGION_BASE &&
        ALT_REGION_BYTES >= desc_length &&
        (desc_dst_addr - ALT_REGION_BASE <= ALT_REGION_BYTES - desc_length);
    wire valid_range = (desc_length != 0) &&
        (desc_length <= desc_capacity) && (primary_range || alt_range) &&
        // Upstream verilog-axi is configured for word-aligned addresses.
        ((desc_dst_addr & (AXI_DATA_WIDTH/8-1)) == 0);
    assign desc_ready = state == IDLE && (valid_range ? dma_desc_ready : 1'b1);
    assign dma_desc_valid = desc_valid && state == IDLE && valid_range;
    assign s_axis_tready = state == SEND && dma_data_ready;

    wire transfer_last = s_axis_tvalid && s_axis_tready && s_axis_tlast;
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            expected_len <= 0;
            active_tag <= 0;
            status_valid <= 0;
            status_ok <= 0;
            status_error <= 0;
            status_tag <= 0;
            status_length <= 0;
            bad_stream <= 0;
        end else begin
            status_valid <= 0;
            case (state)
                IDLE: begin
                    if (desc_valid && desc_ready) begin
                        active_tag <= desc_tag;
                        expected_len <= desc_length;
                        bad_stream <= 0;
                        if (!valid_range) begin
                            status_valid <= 1;
                            status_ok <= 0;
                            status_error <= ERR_BAD_DESC;
                            status_tag <= desc_tag;
                            status_length <= 0;
                        end else begin
                            state <= SEND;
                        end
                    end
                end
                SEND: begin
                    if (s_axis_tvalid && s_axis_tready && s_axis_tuser)
                        bad_stream <= 1;
                    if (transfer_last)
                        state <= WAIT_B;
                end
                WAIT_B: begin
                    if (dma_status_valid) begin
                        status_valid <= 1;
                        status_tag <= active_tag;
                        status_length <= dma_status_len;
                        status_ok <= (dma_status_error == 0) &&
                                     (dma_status_len == expected_len) &&
                                     (dma_status_tag == active_tag) &&
                                     !bad_stream;
                        status_error <= (dma_status_error != 0) ?
                                        dma_status_error :
                                        (dma_status_len != expected_len ||
                                         dma_status_tag != active_tag) ? ERR_LENGTH :
                                        bad_stream ? ERR_FRAME : 4'd0;
                        state <= IDLE;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end

    // This is the upstream RTL IP pinned by config/ip.lock.yaml.
    axi_dma_wr #(
        .AXI_DATA_WIDTH(AXI_DATA_WIDTH),
        .AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
        .AXI_ID_WIDTH(AXI_ID_WIDTH),
        .AXI_MAX_BURST_LEN(16),
        .AXIS_DATA_WIDTH(AXI_DATA_WIDTH),
        .AXIS_KEEP_ENABLE(1),
        .AXIS_LAST_ENABLE(1),
        .AXIS_USER_ENABLE(1),
        .AXIS_USER_WIDTH(1),
        .LEN_WIDTH(LEN_WIDTH),
        .TAG_WIDTH(8),
        .ENABLE_SG(0),
        .ENABLE_UNALIGNED(0)
    ) u_dma (
        .clk(clk), .rst(rst),
        .s_axis_write_desc_addr(desc_dst_addr),
        .s_axis_write_desc_len(desc_length),
        .s_axis_write_desc_tag(desc_tag),
        .s_axis_write_desc_valid(dma_desc_valid),
        .s_axis_write_desc_ready(dma_desc_ready),
        .m_axis_write_desc_status_len(dma_status_len),
        .m_axis_write_desc_status_tag(dma_status_tag),
        .m_axis_write_desc_status_id(),
        .m_axis_write_desc_status_dest(),
        .m_axis_write_desc_status_user(),
        .m_axis_write_desc_status_error(dma_status_error),
        .m_axis_write_desc_status_valid(dma_status_valid),
        .s_axis_write_data_tdata(s_axis_tdata),
        .s_axis_write_data_tkeep(s_axis_tkeep),
        .s_axis_write_data_tvalid(s_axis_tvalid && state == SEND),
        .s_axis_write_data_tready(dma_data_ready),
        .s_axis_write_data_tlast(s_axis_tlast),
        .s_axis_write_data_tid(8'd0),
        .s_axis_write_data_tdest(8'd0),
        .s_axis_write_data_tuser(s_axis_tuser),
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
        .enable(1'b1),
        .abort(1'b0)
    );
endmodule
`default_nettype wire
