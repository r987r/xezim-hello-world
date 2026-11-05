/*
 * Ethernet0 standalone 1G GMII MAC datapath.
 *
 * All protocol/CRC/CDC FIFO RTL is pinned upstream IP; this module only wires
 * those blocks together. This is NOT the SoC NoC/DMA or external PHY.
 * Clocks: gmii_{tx,rx}_clk at 125 MHz, logic_clk normally 100 MHz.
 */
`timescale 1ns/1ps
`default_nettype none
module ethernet0_mac_gmii #(
    parameter integer TX_FIFO_DEPTH = 2048,
    parameter integer RX_FIFO_DEPTH = 2048
) (
    input  wire       logic_clk,
    input  wire       logic_rst,
    input  wire       gmii_tx_clk,
    input  wire       gmii_tx_rst,
    input  wire       gmii_rx_clk,
    input  wire       gmii_rx_rst,

    input  wire [63:0] tx_axis_tdata,
    input  wire [7:0]  tx_axis_tkeep,
    input  wire       tx_axis_tvalid,
    output wire       tx_axis_tready,
    input  wire       tx_axis_tlast,
    input  wire       tx_axis_tuser,

    output wire [63:0] rx_axis_tdata,
    output wire [7:0]  rx_axis_tkeep,
    output wire       rx_axis_tvalid,
    input  wire       rx_axis_tready,
    output wire       rx_axis_tlast,
    output wire       rx_axis_tuser,

    input  wire [7:0] gmii_rxd,
    input  wire       gmii_rx_dv,
    input  wire       gmii_rx_er,
    output wire [7:0] gmii_txd,
    output wire       gmii_tx_en,
    output wire       gmii_tx_er,

    input  wire       tx_enable,
    input  wire       rx_enable,

    output wire       tx_error_underflow,
    output wire       rx_error_bad_frame,
    output wire       rx_error_bad_fcs,
    output wire       rx_fifo_overflow,
    output wire       rx_fifo_bad_frame,
    output wire       rx_fifo_good_frame
);

wire [7:0] fifo_tx_tdata;
wire       fifo_tx_tvalid;
wire       fifo_tx_tready;
wire       fifo_tx_tlast;
wire       fifo_tx_tuser;

wire [7:0] gmii_rx_axis_tdata;
wire       gmii_rx_axis_tvalid;
wire       gmii_rx_axis_tready;
wire       gmii_rx_axis_tlast;
wire       gmii_rx_axis_tuser;

// Width-convert logic 64-bit AXIS with tkeep to 8-bit GMII MAC stream.
// Buffer complete TX frames in logic clock before handoff to MAC clock.
// This prevents intermittent underflow during normal logic-domain stalls.
axis_async_fifo_adapter #(
    .DEPTH(TX_FIFO_DEPTH),
    .S_DATA_WIDTH(64),
    .S_KEEP_ENABLE(1),
    .S_KEEP_WIDTH(8),
    .M_DATA_WIDTH(8),
    .M_KEEP_ENABLE(0),
    .M_KEEP_WIDTH(1),
    .ID_ENABLE(0),
    .DEST_ENABLE(0),
    .USER_ENABLE(1),
    .USER_WIDTH(1),
    .FRAME_FIFO(1),
    .DROP_OVERSIZE_FRAME(1),
    .DROP_BAD_FRAME(1),
    .DROP_WHEN_FULL(0)
) tx_cdc_fifo (
    .s_clk(logic_clk),
    .s_rst(logic_rst),
    .s_axis_tdata(tx_axis_tdata),
    .s_axis_tkeep(tx_axis_tkeep),
    .s_axis_tvalid(tx_axis_tvalid),
    .s_axis_tready(tx_axis_tready),
    .s_axis_tlast(tx_axis_tlast),
    .s_axis_tid(8'd0),
    .s_axis_tdest(8'd0),
    .s_axis_tuser(tx_axis_tuser),
    .m_clk(gmii_tx_clk),
    .m_rst(gmii_tx_rst),
    .m_axis_tdata(fifo_tx_tdata),
    .m_axis_tkeep(),
    .m_axis_tvalid(fifo_tx_tvalid),
    .m_axis_tready(fifo_tx_tready),
    .m_axis_tlast(fifo_tx_tlast),
    .m_axis_tid(),
    .m_axis_tdest(),
    .m_axis_tuser(fifo_tx_tuser),
    .s_pause_req(1'b0),
    .s_pause_ack(),
    .m_pause_req(1'b0),
    .m_pause_ack(),
    .s_status_depth(),
    .s_status_depth_commit(),
    .s_status_overflow(),
    .s_status_bad_frame(),
    .s_status_good_frame(),
    .m_status_depth(),
    .m_status_depth_commit(),
    .m_status_overflow(),
    .m_status_bad_frame(),
    .m_status_good_frame()
);

axis_gmii_tx #(
    .DATA_WIDTH(8),
    .ENABLE_PADDING(1),
    .MIN_FRAME_LENGTH(64),
    .PTP_TS_ENABLE(0),
    .USER_WIDTH(1)
) mac_tx (
    .clk(gmii_tx_clk),
    .rst(gmii_tx_rst),
    .s_axis_tdata(fifo_tx_tdata),
    .s_axis_tvalid(fifo_tx_tvalid),
    .s_axis_tready(fifo_tx_tready),
    .s_axis_tlast(fifo_tx_tlast),
    .s_axis_tuser(fifo_tx_tuser),
    .gmii_txd(gmii_txd),
    .gmii_tx_en(gmii_tx_en),
    .gmii_tx_er(gmii_tx_er),
    .ptp_ts(96'd0),
    .m_axis_ptp_ts(),
    .m_axis_ptp_ts_tag(),
    .m_axis_ptp_ts_valid(),
    .clk_enable(1'b1),
    .mii_select(1'b0),
    .cfg_ifg(8'd12),
    .cfg_tx_enable(tx_enable),
    .start_packet(),
    .error_underflow(tx_error_underflow)
);

axis_gmii_rx #(
    .DATA_WIDTH(8),
    .PTP_TS_ENABLE(0),
    .USER_WIDTH(1)
) mac_rx (
    .clk(gmii_rx_clk),
    .rst(gmii_rx_rst),
    .gmii_rxd(gmii_rxd),
    .gmii_rx_dv(gmii_rx_dv),
    .gmii_rx_er(gmii_rx_er),
    .m_axis_tdata(gmii_rx_axis_tdata),
    .m_axis_tvalid(gmii_rx_axis_tvalid),
    .m_axis_tlast(gmii_rx_axis_tlast),
    .m_axis_tuser(gmii_rx_axis_tuser),
    .ptp_ts(96'd0),
    .clk_enable(1'b1),
    .mii_select(1'b0),
    .cfg_rx_enable(rx_enable),
    .start_packet(),
    .error_bad_frame(rx_error_bad_frame),
    .error_bad_fcs(rx_error_bad_fcs)
);

// Width-convert 8-bit GMII stream to logic 64-bit AXIS with tkeep.
// GMII cannot be backpressured: frame FIFO must always accept source beats,
// dropping the *whole* frame on bad FCS or overflow. Never deliver a partial
// frame to memory or treat overflow as a successful RX packet.
axis_async_fifo_adapter #(
    .DEPTH(RX_FIFO_DEPTH),
    .S_DATA_WIDTH(8),
    .S_KEEP_ENABLE(0),
    .S_KEEP_WIDTH(1),
    .M_DATA_WIDTH(64),
    .M_KEEP_ENABLE(1),
    .M_KEEP_WIDTH(8),
    .ID_ENABLE(0),
    .DEST_ENABLE(0),
    .USER_ENABLE(1),
    .USER_WIDTH(1),
    .FRAME_FIFO(1),
    .DROP_OVERSIZE_FRAME(1),
    .DROP_BAD_FRAME(1),
    .DROP_WHEN_FULL(1)
) rx_cdc_fifo (
    .s_clk(gmii_rx_clk),
    .s_rst(gmii_rx_rst),
    .s_axis_tdata(gmii_rx_axis_tdata),
    .s_axis_tkeep(1'b1),
    .s_axis_tvalid(gmii_rx_axis_tvalid),
    .s_axis_tready(gmii_rx_axis_tready),
    .s_axis_tlast(gmii_rx_axis_tlast),
    .s_axis_tid(8'd0),
    .s_axis_tdest(8'd0),
    .s_axis_tuser(gmii_rx_axis_tuser),
    .m_clk(logic_clk),
    .m_rst(logic_rst),
    .m_axis_tdata(rx_axis_tdata),
    .m_axis_tkeep(rx_axis_tkeep),
    .m_axis_tvalid(rx_axis_tvalid),
    .m_axis_tready(rx_axis_tready),
    .m_axis_tlast(rx_axis_tlast),
    .m_axis_tid(),
    .m_axis_tdest(),
    .m_axis_tuser(rx_axis_tuser),
    .s_pause_req(1'b0),
    .s_pause_ack(),
    .m_pause_req(1'b0),
    .m_pause_ack(),
    .s_status_depth(),
    .s_status_depth_commit(),
    .s_status_overflow(),
    .s_status_bad_frame(),
    .s_status_good_frame(),
    .m_status_depth(),
    .m_status_depth_commit(),
    .m_status_overflow(rx_fifo_overflow),
    .m_status_bad_frame(rx_fifo_bad_frame),
    .m_status_good_frame(rx_fifo_good_frame)
);

endmodule
`default_nettype wire
