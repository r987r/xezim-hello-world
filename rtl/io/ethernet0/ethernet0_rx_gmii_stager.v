// Standalone real GMII MAC -> dual-clock FIFO -> whole-frame header staging.
// TX is intentionally disabled here; bidirectional subsystem integration is
// a separate queue/SoC milestone. No AXI DMA or NoC is instantiated here.
`timescale 1ns/1ps
`default_nettype none
module ethernet0_rx_gmii_stager #(parameter integer TX_ENABLE=0) (
 input wire logic_clk,logic_rst,
 input wire gmii_rx_clk,gmii_rx_rst,
 input wire gmii_tx_clk,gmii_tx_rst,
 input wire [7:0] gmii_rxd,
 input wire gmii_rx_dv,gmii_rx_er,
 input wire [63:0] tx_axis_tdata,input wire [7:0] tx_axis_tkeep,
 input wire tx_axis_tvalid,output wire tx_axis_tready,
 input wire tx_axis_tlast,tx_axis_tuser,
 output wire [7:0] gmii_txd,output wire gmii_tx_en,gmii_tx_er,
 output wire tx_error_underflow,
 output wire meta_valid,input wire meta_ready,
 output wire [15:0] meta_length,meta_ethertype,
 output wire meta_is_udp,output wire [15:0] meta_udp_dst_port,
 output wire [63:0] rx_axis_tdata,output wire [7:0] rx_axis_tkeep,
 output wire rx_axis_tvalid,input wire rx_axis_tready,
 output wire rx_axis_tlast,rx_axis_tuser,
 output wire rx_error_bad_fcs,rx_error_bad_frame,
 output wire rx_fifo_overflow,rx_fifo_bad_frame,rx_fifo_good_frame,
 output wire dropped_frame_pulse,
 output wire stage_fifo_overflow
);
wire [63:0] mac_tdata;
wire [7:0] mac_tkeep;
wire mac_tvalid,mac_tready,mac_tlast,mac_tuser;
ethernet0_mac_gmii u_mac (
 .logic_clk,.logic_rst,.gmii_tx_clk,.gmii_tx_rst,
 .gmii_rx_clk,.gmii_rx_rst,
 .tx_axis_tdata(TX_ENABLE ? tx_axis_tdata : 64'd0),
 .tx_axis_tkeep(TX_ENABLE ? tx_axis_tkeep : 8'd0),
 .tx_axis_tvalid(TX_ENABLE ? tx_axis_tvalid : 1'b0),
 .tx_axis_tready(tx_axis_tready),
 .tx_axis_tlast(TX_ENABLE ? tx_axis_tlast : 1'b0),
 .tx_axis_tuser(TX_ENABLE ? tx_axis_tuser : 1'b0),
 .rx_axis_tdata(mac_tdata),.rx_axis_tkeep(mac_tkeep),
 .rx_axis_tvalid(mac_tvalid),.rx_axis_tready(mac_tready),
 .rx_axis_tlast(mac_tlast),.rx_axis_tuser(mac_tuser),
 .gmii_rxd,.gmii_rx_dv,.gmii_rx_er,
 .gmii_txd,.gmii_tx_en,.gmii_tx_er,
 .tx_enable(TX_ENABLE != 0),.rx_enable(1'b1),
 .tx_error_underflow,
 .rx_error_bad_frame(rx_error_bad_frame),
 .rx_error_bad_fcs(rx_error_bad_fcs),
 .rx_fifo_overflow(rx_fifo_overflow),
 .rx_fifo_bad_frame(rx_fifo_bad_frame),
 .rx_fifo_good_frame(rx_fifo_good_frame)
);
ethernet_rx_frame_stager u_stager (
 .clk(logic_clk),.rst(logic_rst),
 .s_axis_tdata(mac_tdata),.s_axis_tkeep(mac_tkeep),
 .s_axis_tvalid(mac_tvalid),.s_axis_tready(mac_tready),
 .s_axis_tlast(mac_tlast),.s_axis_tuser(mac_tuser),
 .meta_valid,.meta_ready,.meta_length,.meta_ethertype,
 .meta_is_udp,.meta_udp_dst_port,
 .m_axis_tdata(rx_axis_tdata),.m_axis_tkeep(rx_axis_tkeep),
 .m_axis_tvalid(rx_axis_tvalid),.m_axis_tready(rx_axis_tready),
 .m_axis_tlast(rx_axis_tlast),.m_axis_tuser(rx_axis_tuser),
 .dropped_frame_pulse,.fifo_overflow(stage_fifo_overflow)
);
endmodule
`default_nettype wire
