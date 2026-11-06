/*
 * Ethernet0 TX: bounded AXI-to-AXI-Stream memory reader using unmodified
 * upstream verilog-axi axi_dma_rd. Completes only after final AXIS beat
 * is ACCEPTED plus upstream AXI read status, not at descriptor submission.
 * A subsequent GMII TX wire-completion gate is required in the NIC.
 */
`timescale 1ns/1ps
`default_nettype none
module ethernet_tx_dma #(
    parameter integer AXI_ADDR_WIDTH=64,
    parameter integer AXI_DATA_WIDTH=64,
    parameter integer AXI_ID_WIDTH=4,
    parameter integer LEN_WIDTH=16,
    parameter [AXI_ADDR_WIDTH-1:0] REGION_BASE=0,
    parameter [AXI_ADDR_WIDTH-1:0] REGION_BYTES=65536,
    // Optional DDR window, disabled unless the full-chip generator opts in.
    parameter [AXI_ADDR_WIDTH-1:0] ALT_REGION_BASE=0,
    parameter [AXI_ADDR_WIDTH-1:0] ALT_REGION_BYTES=0
) (
    input wire clk, rst,
    input wire desc_valid,
    output wire desc_ready,
    input wire [AXI_ADDR_WIDTH-1:0] desc_src_addr,
    input wire [LEN_WIDTH-1:0] desc_length,
    input wire [LEN_WIDTH-1:0] desc_capacity,
    input wire [7:0] desc_tag,
    output reg status_valid,
    output reg status_ok,
    output reg [3:0] status_error,
    output reg [7:0] status_tag,

    output wire [AXI_DATA_WIDTH-1:0] m_axis_tdata,
    output wire [AXI_DATA_WIDTH/8-1:0] m_axis_tkeep,
    output wire m_axis_tvalid,
    input wire m_axis_tready,
    output wire m_axis_tlast,
    output wire m_axis_tuser,

    output wire [AXI_ID_WIDTH-1:0] m_axi_arid,
    output wire [AXI_ADDR_WIDTH-1:0] m_axi_araddr,
    output wire [7:0] m_axi_arlen,
    output wire [2:0] m_axi_arsize,
    output wire [1:0] m_axi_arburst,
    output wire m_axi_arlock,
    output wire [3:0] m_axi_arcache,
    output wire [2:0] m_axi_arprot,
    output wire m_axi_arvalid,
    input wire m_axi_arready,
    input wire [AXI_ID_WIDTH-1:0] m_axi_rid,
    input wire [AXI_DATA_WIDTH-1:0] m_axi_rdata,
    input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast,
    input wire m_axi_rvalid,
    output wire m_axi_rready
);
    localparam [3:0] ERR_BAD_DESC=4'h8, ERR_AXI_DATA=4'ha,
                     ERR_BAD_TAG=4'h9;
    reg busy=0, seen_last=0, seen_status=0, bad_axis=0;
    reg [7:0] active_tag=0;
    reg [3:0] latched_error=0;
    wire dma_desc_ready, dma_status_valid;
    wire [7:0] dma_status_tag;
    wire [3:0] dma_status_error;
    wire [AXI_DATA_WIDTH-1:0] dma_tdata;
    wire [AXI_DATA_WIDTH/8-1:0] dma_tkeep;
    wire dma_tvalid,dma_tready,dma_tlast,dma_tuser;

    wire primary_range = desc_src_addr >= REGION_BASE &&
        REGION_BYTES >= desc_length &&
        (desc_src_addr-REGION_BASE) <= (REGION_BYTES-desc_length);
    wire alt_range = ALT_REGION_BYTES != 0 &&
        desc_src_addr >= ALT_REGION_BASE &&
        ALT_REGION_BYTES >= desc_length &&
        (desc_src_addr-ALT_REGION_BASE) <= (ALT_REGION_BYTES-desc_length);
    wire valid_range = desc_length != 0 && desc_length <= desc_capacity &&
        (primary_range || alt_range) &&
        ((desc_src_addr & (AXI_DATA_WIDTH/8-1)) == 0);
    assign desc_ready = !busy && (valid_range ? dma_desc_ready : 1'b1);
    wire dma_desc_valid = desc_valid && !busy && valid_range;
    assign m_axis_tdata = dma_tdata;
    assign m_axis_tkeep = dma_tkeep;
    assign m_axis_tvalid = dma_tvalid && busy;
    assign m_axis_tlast = dma_tlast;
    assign m_axis_tuser = dma_tuser;
    assign dma_tready = busy && m_axis_tready;
    wire stream_last = m_axis_tvalid && m_axis_tready && m_axis_tlast;
    wire done_now = busy && (seen_status || dma_status_valid) &&
                    (seen_last || stream_last);

    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; seen_last <= 0; seen_status <= 0;
            bad_axis <= 0; latched_error <= 0; active_tag <= 0;
            status_valid <= 0; status_ok <= 0; status_error <= 0;
            status_tag <= 0;
        end else begin
            status_valid <= 0;
            if (desc_valid && desc_ready) begin
                active_tag <= desc_tag;
                if (!valid_range) begin
                    status_valid <= 1;
                    status_ok <= 0;
                    status_error <= ERR_BAD_DESC;
                    status_tag <= desc_tag;
                end else begin
                    busy <= 1;
                    seen_last <= 0;
                    seen_status <= 0;
                    bad_axis <= 0;
                    latched_error <= 0;
                end
            end
            if (busy) begin
                if (dma_status_valid) begin
                    seen_status <= 1;
                    latched_error <= (dma_status_tag != active_tag) ?
                                     ERR_BAD_TAG : dma_status_error;
                end
                if (m_axis_tvalid && m_axis_tready && dma_tuser)
                    bad_axis <= 1;
                if (stream_last) seen_last <= 1;
                if (done_now) begin
                    busy <= 0;
                    status_valid <= 1;
                    status_tag <= active_tag;
                    status_ok <= ((dma_status_valid ?
                                   ((dma_status_tag != active_tag) ?
                                      ERR_BAD_TAG : dma_status_error) :
                                   latched_error) == 0) &&
                                  !(bad_axis || (dma_tuser && stream_last));
                    status_error <= (dma_status_valid ?
                                    ((dma_status_tag != active_tag) ?
                                       ERR_BAD_TAG : dma_status_error) :
                                    latched_error) != 0 ?
                                    (dma_status_valid ?
                                     ((dma_status_tag != active_tag) ?
                                      ERR_BAD_TAG : dma_status_error) :
                                     latched_error) :
                                    (bad_axis || (dma_tuser && stream_last)) ?
                                      ERR_AXI_DATA : 0;
                end
            end
        end
    end

    axi_dma_rd #(
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
        .s_axis_read_desc_addr(desc_src_addr),
        .s_axis_read_desc_len(desc_length),
        .s_axis_read_desc_tag(desc_tag),
        .s_axis_read_desc_id(8'd0),
        .s_axis_read_desc_dest(8'd0),
        .s_axis_read_desc_user(1'b0),
        .s_axis_read_desc_valid(dma_desc_valid),
        .s_axis_read_desc_ready(dma_desc_ready),
        .m_axis_read_desc_status_tag(dma_status_tag),
        .m_axis_read_desc_status_error(dma_status_error),
        .m_axis_read_desc_status_valid(dma_status_valid),
        .m_axis_read_data_tdata(dma_tdata),
        .m_axis_read_data_tkeep(dma_tkeep),
        .m_axis_read_data_tvalid(dma_tvalid),
        .m_axis_read_data_tready(dma_tready),
        .m_axis_read_data_tlast(dma_tlast),
        .m_axis_read_data_tid(),
        .m_axis_read_data_tdest(),
        .m_axis_read_data_tuser(dma_tuser),
        .m_axi_arid(m_axi_arid), .m_axi_araddr(m_axi_araddr),
        .m_axi_arlen(m_axi_arlen), .m_axi_arsize(m_axi_arsize),
        .m_axi_arburst(m_axi_arburst), .m_axi_arlock(m_axi_arlock),
        .m_axi_arcache(m_axi_arcache), .m_axi_arprot(m_axi_arprot),
        .m_axi_arvalid(m_axi_arvalid), .m_axi_arready(m_axi_arready),
        .m_axi_rid(m_axi_rid), .m_axi_rdata(m_axi_rdata),
        .m_axi_rresp(m_axi_rresp), .m_axi_rlast(m_axi_rlast),
        .m_axi_rvalid(m_axi_rvalid), .m_axi_rready(m_axi_rready),
        .enable(1'b1)
    );
endmodule
`default_nettype wire
