/* Ethernet0 descriptor-ring fetch, using the pinned real axi_dma_rd RTL.
 * One request / 32-byte little-endian descriptor at a time, with checked
 * ring address, buffer capacity, target aperture and reserved fields.
 * The queue controller remains responsible for owner/pointer accounting;
 * actual packet writes and completion-record writes are separate engines.
 */
`timescale 1ns/1ps
`default_nettype none
module ethernet_rx_desc_fetch #(
    parameter integer AXI_ADDR_WIDTH=64,
    parameter integer AXI_ID_WIDTH=4,
    parameter [AXI_ADDR_WIDTH-1:0] RING_BASE=64'h100,
    parameter [AXI_ADDR_WIDTH-1:0] RING_BYTES=64'h1000,
    parameter [AXI_ADDR_WIDTH-1:0] BUFFER_BASE=64'h2000,
    parameter [AXI_ADDR_WIDTH-1:0] BUFFER_BYTES=64'h8000,
    // Optional second descriptor aperture (region_id=1): modeled DDR in
    // the full-chip test. Disabled by default. Never truncate 64-bit PA.
    parameter [AXI_ADDR_WIDTH-1:0] ALT_BUFFER_BASE=0,
    parameter [AXI_ADDR_WIDTH-1:0] ALT_BUFFER_BYTES=0,
    parameter integer MAX_FRAME_BYTES=2048
) (
    input wire clk,rst,
    input wire req_valid,
    output wire req_ready,
    input wire [AXI_ADDR_WIDTH-1:0] req_ring_addr,
    input wire [15:0] req_frame_len,
    input wire [7:0] req_tag,
    output wire result_valid,
    input wire result_ready,
    output wire result_ok,
    output wire [3:0] result_error,
    output wire [AXI_ADDR_WIDTH-1:0] result_buffer_addr,
    output wire [31:0] result_capacity,
    output wire [31:0] result_cookie,
    output wire [7:0] result_tag,
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
    input wire [63:0] m_axi_rdata,
    input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast,
    input wire m_axi_rvalid,
    output wire m_axi_rready
);
localparam [1:0] IDLE=0,FETCH=1,REPORT=2;
localparam [3:0] ERR_REQ=4'h8,ERR_READ=4'h9,ERR_BUFFER=4'ha;
reg [1:0] state=IDLE;
reg [15:0] frame_len=0;
reg [7:0] active_tag=0;
reg invalid_req=0,read_bad=0,got_last=0,got_status=0;
reg [3:0] dma_error=0;
reg [2:0] beats=0;
reg [63:0] word0=0,word1=0,word2=0,word3=0;
wire dma_desc_ready,dma_status_valid;
wire [7:0] dma_status_tag;
wire [3:0] dma_status_error;
wire [63:0] dma_tdata;
wire [7:0] dma_tkeep;
wire dma_tvalid,dma_tready,dma_tlast,dma_tuser;
wire valid_req = req_frame_len>0 && req_frame_len<=MAX_FRAME_BYTES &&
                 req_ring_addr>=RING_BASE && RING_BYTES>=32 &&
                 req_ring_addr-RING_BASE<=RING_BYTES-32 &&
                 (req_ring_addr & 31)==0;
assign req_ready=(state==IDLE) && (valid_req?dma_desc_ready:1'b1);
wire desc_fire = req_valid && req_ready && valid_req;
assign dma_tready=(state==FETCH);
assign result_valid = state==REPORT;
assign result_tag = active_tag;
assign result_buffer_addr = word0;
assign result_capacity = word1[31:0];
assign result_cookie = word1[63:32];
// Descriptor word2: flags [31:0] must be zero in V1 and region_id [63:32]
// selects exactly one program-authorized window. A descriptor cannot span
// region boundaries or silently alias a high (>4GiB) DDR address to SRAM.
wire primary_buffer_ok = word2[63:32]==0 &&
    word0>=BUFFER_BASE && BUFFER_BYTES>=word1[31:0] &&
    word0-BUFFER_BASE <= BUFFER_BYTES-word1[31:0];
wire alt_buffer_ok = word2[63:32]==1 && ALT_BUFFER_BYTES!=0 &&
    word0>=ALT_BUFFER_BASE && ALT_BUFFER_BYTES>=word1[31:0] &&
    word0-ALT_BUFFER_BASE <= ALT_BUFFER_BYTES-word1[31:0];
wire buffer_ok = (primary_buffer_ok || alt_buffer_ok) &&
    (word0 & 7)==0 &&
    word1[31:0]>=frame_len && word1[31:0]<=MAX_FRAME_BYTES &&
    word2[31:0]==0 && word3==0;
assign result_ok = !invalid_req && !read_bad && got_last &&
                   got_status && dma_error==0 && beats==4 && buffer_ok;
assign result_error = invalid_req ? ERR_REQ :
                      (read_bad || !got_last || !got_status ||
                       dma_error!=0 || beats!=4) ? ERR_READ :
                      !buffer_ok ? ERR_BUFFER : 4'd0;
always @(posedge clk) begin
    if(rst) begin
        state<=IDLE;frame_len<=0;active_tag<=0;
        invalid_req<=0;read_bad<=0;got_last<=0;got_status<=0;
        dma_error<=0;beats<=0;
        word0<=0;word1<=0;word2<=0;word3<=0;
    end else case(state)
        IDLE: if(req_valid && req_ready) begin
            frame_len<=req_frame_len;
            active_tag<=req_tag;
            invalid_req<=!valid_req;
            read_bad<=0;got_last<=0;got_status<=0;
            dma_error<=0;beats<=0;
            word0<=0;word1<=0;word2<=0;word3<=0;
            state<=valid_req?FETCH:REPORT;
        end
        FETCH: begin
            if(dma_tvalid && dma_tready) begin
                if(dma_tkeep!=8'hff || dma_tuser || beats>=4 ||
                   (dma_tlast!=(beats==3)))
                    read_bad<=1;
                case(beats)
                    0: word0<=dma_tdata;
                    1: word1<=dma_tdata;
                    2: word2<=dma_tdata;
                    3: word3<=dma_tdata;
                    default: read_bad<=1;
                endcase
                beats<=beats+1;
                if(dma_tlast) got_last<=1;
            end
            if(dma_status_valid) begin
                got_status<=1;
                dma_error <= dma_status_tag==active_tag ?
                             dma_status_error : ERR_READ;
            end
            if(got_last && got_status) state<=REPORT;
        end
        REPORT: if(result_valid && result_ready) state<=IDLE;
        default: state<=IDLE;
    endcase
end

axi_dma_rd #(
    .AXI_DATA_WIDTH(64),.AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
    .AXI_ID_WIDTH(AXI_ID_WIDTH),.AXI_MAX_BURST_LEN(16),
    .AXIS_DATA_WIDTH(64),.AXIS_KEEP_ENABLE(1),
    .AXIS_LAST_ENABLE(1),.AXIS_USER_ENABLE(1),
    .LEN_WIDTH(16),.TAG_WIDTH(8),
    .ENABLE_SG(0),.ENABLE_UNALIGNED(0)
) u_desc_reader (
    .clk,.rst,
    .s_axis_read_desc_addr(req_ring_addr),
    .s_axis_read_desc_len(16'd32),
    .s_axis_read_desc_tag(req_tag),
    .s_axis_read_desc_id(8'd0),
    .s_axis_read_desc_dest(8'd0),
    .s_axis_read_desc_user(1'b0),
    .s_axis_read_desc_valid(desc_fire),
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
    .m_axi_arid(m_axi_arid),.m_axi_araddr(m_axi_araddr),
    .m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),
    .m_axi_arburst(m_axi_arburst),.m_axi_arlock(m_axi_arlock),
    .m_axi_arcache(m_axi_arcache),.m_axi_arprot(m_axi_arprot),
    .m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
    .m_axi_rid(m_axi_rid),.m_axi_rdata(m_axi_rdata),
    .m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),
    .m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready),
    .enable(1'b1)
);
endmodule
`default_nettype wire
