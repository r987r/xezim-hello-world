// DDR-B, memory-only AXI4 slave-to-pinned-LiteDRAM local AXI bridge.
//
// This is NOT yet wired into the generated SoC. It intentionally implements
// one outstanding WRITE and one outstanding READ, independently, so that
// illegal requests return legal DECERR beats without truncating physical
// addresses or IDs. The generated SoC owner (#38) owns the NoC instantiation,
// clocks/reset and DFII Wishbone init path.
//
// LiteDRAM user_port_axi_0 pins are exposed as m_*; s_* are the full
// 64-bit-physical AXI4 memory target pins. Unsupported AXI ATOP/WRAP/FIXED,
// out-of-model addresses and 4-KiB-crossing bursts must never reach m_*.
// For VALID requests, this module passes through full 64-bit data, strobes,
// 4-bit IDs and all AXI response codes. No internal memory or fake PHY.
module ddr_litedram_axi_bridge #(
  parameter int unsigned LOCAL_ADDR_WIDTH = 25,
  parameter logic [63:0] BASE = 64'h0000_0001_4000_0000,
  parameter logic [63:0] ARCH_BYTES = 64'h0000_0000_4000_0000,
  parameter logic [63:0] MODEL_BYTES = 64'h0000_0000_0200_0000
) (
  input  wire clk_i,
  input  wire rst_ni,
  input  wire controller_ready_i,

  input  wire [3:0]  s_awid,
  input  wire [63:0] s_awaddr,
  input  wire [7:0]  s_awlen,
  input  wire [2:0]  s_awsize,
  input  wire [1:0]  s_awburst,
  input  wire [5:0]  s_awatop,
  input  wire        s_awvalid,
  output logic       s_awready,
  input  wire [63:0] s_wdata,
  input  wire [7:0]  s_wstrb,
  input  wire        s_wlast,
  input  wire        s_wvalid,
  output logic       s_wready,
  output logic [3:0] s_bid,
  output logic [1:0] s_bresp,
  output logic       s_bvalid,
  input  wire        s_bready,

  input  wire [3:0]  s_arid,
  input  wire [63:0] s_araddr,
  input  wire [7:0]  s_arlen,
  input  wire [2:0]  s_arsize,
  input  wire [1:0]  s_arburst,
  input  wire        s_arvalid,
  output logic       s_arready,
  output logic [3:0] s_rid,
  output logic [63:0] s_rdata,
  output logic [1:0] s_rresp,
  output logic       s_rlast,
  output logic       s_rvalid,
  input  wire        s_rready,

  output logic [3:0] m_awid,
  output logic [LOCAL_ADDR_WIDTH-1:0] m_awaddr,
  output logic [7:0] m_awlen,
  output logic [2:0] m_awsize,
  output logic [1:0] m_awburst,
  output logic       m_awvalid,
  input  wire        m_awready,
  output logic [63:0] m_wdata,
  output logic [7:0]  m_wstrb,
  output logic        m_wlast,
  output logic        m_wvalid,
  input  wire         m_wready,
  input  wire [3:0]   m_bid,
  input  wire [1:0]   m_bresp,
  input  wire         m_bvalid,
  output logic        m_bready,

  output logic [3:0] m_arid,
  output logic [LOCAL_ADDR_WIDTH-1:0] m_araddr,
  output logic [7:0] m_arlen,
  output logic [2:0] m_arsize,
  output logic [1:0] m_arburst,
  output logic       m_arvalid,
  input  wire        m_arready,
  input  wire [3:0]  m_rid,
  input  wire [63:0] m_rdata,
  input  wire [1:0]  m_rresp,
  input  wire        m_rlast,
  input  wire        m_rvalid,
  output logic       m_rready
);
  localparam logic [1:0] RESP_DECERR = 2'b11;
  localparam logic [1:0] WB_IDLE = 2'd0, WB_ADDR = 2'd1,
                         WB_DATA = 2'd2, WB_RESP = 2'd3;
  localparam logic [1:0] RB_IDLE = 2'd0, RB_ADDR = 2'd1,
                         RB_DATA = 2'd2, RB_ERR = 2'd3;

  logic [1:0] wb_state, rb_state;
  logic wb_error;
  logic [8:0] w_remaining;
  logic [8:0] r_remaining;
  logic [3:0] w_id, r_id;
  logic [LOCAL_ADDR_WIDTH-1:0] w_addr, r_addr;
  logic [7:0] w_len, r_len;
  logic [2:0] w_size, r_size;
  logic [1:0] w_burst, r_burst;

  wire [LOCAL_ADDR_WIDTH-1:0] aw_local, ar_local;
  wire aw_allow, ar_allow;

  ddr_litedram_axi_aperture_guard #(
    .LOCAL_ADDR_WIDTH(LOCAL_ADDR_WIDTH), .BASE(BASE),
    .ARCH_BYTES(ARCH_BYTES), .MODEL_BYTES(MODEL_BYTES)
  ) u_aw_guard (
    .phys_addr_i(s_awaddr), .axlen_i(s_awlen),
    .axsize_i(s_awsize), .axburst_i(s_awburst),
    .atop_i(s_awatop), .local_addr_o(aw_local),
    .allow_o(aw_allow), .fault_o()
  );
  ddr_litedram_axi_aperture_guard #(
    .LOCAL_ADDR_WIDTH(LOCAL_ADDR_WIDTH), .BASE(BASE),
    .ARCH_BYTES(ARCH_BYTES), .MODEL_BYTES(MODEL_BYTES)
  ) u_ar_guard (
    .phys_addr_i(s_araddr), .axlen_i(s_arlen),
    .axsize_i(s_arsize), .axburst_i(s_arburst),
    .atop_i(6'd0), .local_addr_o(ar_local),
    .allow_o(ar_allow), .fault_o()
  );

  always_comb begin
    s_awready = wb_state == WB_IDLE && controller_ready_i;
    m_awvalid = wb_state == WB_ADDR;
    m_awid = w_id;
    m_awaddr = w_addr;
    m_awlen = w_len;
    m_awsize = w_size;
    m_awburst = w_burst;
    m_wdata = s_wdata;
    m_wstrb = s_wstrb;
    m_wlast = s_wlast;
    m_wvalid = (wb_state == WB_DATA) && !wb_error && s_wvalid;
    s_wready = (wb_state == WB_DATA) && (wb_error || m_wready);
    s_bvalid = (wb_state == WB_RESP) && (wb_error || m_bvalid);
    s_bid = wb_error ? w_id : m_bid;
    s_bresp = wb_error ? RESP_DECERR : m_bresp;
    m_bready = (wb_state == WB_RESP) && !wb_error && s_bready;

    s_arready = rb_state == RB_IDLE && controller_ready_i;
    m_arvalid = rb_state == RB_ADDR;
    m_araddr = r_addr;
    m_arid = r_id;
    m_arlen = r_len;
    m_arsize = r_size;
    m_arburst = r_burst;
    m_rready = rb_state == RB_DATA && s_rready;
    s_rvalid = (rb_state == RB_DATA && m_rvalid) || (rb_state == RB_ERR);
    s_rid = rb_state == RB_ERR ? r_id : m_rid;
    s_rdata = rb_state == RB_ERR ? '0 : m_rdata;
    s_rresp = rb_state == RB_ERR ? RESP_DECERR : m_rresp;
    s_rlast = rb_state == RB_ERR ? (r_remaining == 9'd1) : m_rlast;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      wb_state <= WB_IDLE;
      rb_state <= RB_IDLE;
      wb_error <= 1'b0;
      w_remaining <= '0;
      r_remaining <= '0;
      w_id <= '0; r_id <= '0;
      w_addr <= '0; r_addr <= '0;
      w_len <= '0; r_len <= '0;
      w_size <= '0; r_size <= '0;
      w_burst <= '0; r_burst <= '0;
    end else begin
      case (wb_state)
        WB_IDLE: if (s_awvalid && s_awready) begin
          w_id <= s_awid;
          w_addr <= aw_local;
          w_len <= s_awlen;
          w_size <= s_awsize;
          w_burst <= s_awburst;
          w_remaining <= 9'(s_awlen) + 9'd1;
          wb_error <= !aw_allow;
          wb_state <= aw_allow ? WB_ADDR : WB_DATA;
        end
        WB_ADDR: if (m_awvalid && m_awready) wb_state <= WB_DATA;
        WB_DATA: if (s_wvalid && s_wready) begin
          if ((w_remaining == 9'd1) != s_wlast)
            $fatal(1, "DDR AXI protocol WLAST mismatch");
          if (w_remaining == 9'd1)
            wb_state <= WB_RESP;
          w_remaining <= w_remaining - 9'd1;
        end
        WB_RESP: if (s_bvalid && s_bready) wb_state <= WB_IDLE;
        default: wb_state <= WB_IDLE;
      endcase

      case (rb_state)
        RB_IDLE: if (s_arvalid && s_arready) begin
          r_id <= s_arid;
          r_addr <= ar_local;
          r_len <= s_arlen;
          r_size <= s_arsize;
          r_burst <= s_arburst;
          r_remaining <= 9'(s_arlen) + 9'd1;
          rb_state <= ar_allow ? RB_ADDR : RB_ERR;
        end
        RB_ADDR: if (m_arvalid && m_arready) rb_state <= RB_DATA;
        RB_DATA: if (s_rvalid && s_rready) begin
          if ((r_remaining == 9'd1) != m_rlast)
            $fatal(1, "LiteDRAM AXI RLAST mismatch");
          if (r_remaining == 9'd1) rb_state <= RB_IDLE;
          r_remaining <= r_remaining - 9'd1;
        end
        RB_ERR: if (s_rvalid && s_rready) begin
          if (r_remaining == 9'd1) rb_state <= RB_IDLE;
          r_remaining <= r_remaining - 9'd1;
        end
        default: rb_state <= RB_IDLE;
      endcase
    end
  end

  initial begin
    assert (LOCAL_ADDR_WIDTH == 25)
      else $fatal(1, "DDR adapter address width must match generated soc_ddr4_sim.v");
    assert (ARCH_BYTES >= MODEL_BYTES)
      else $fatal(1, "invalid DDR model aperture");
  end
endmodule
