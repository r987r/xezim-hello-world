// DDR-B: real memory0 Config NoC AXI4 single-beat target to pinned LiteX Wishbone.
// No fake CSR, init_done or controller state; caller drives upstream DFII script.
// One outstanding operation; malformed AXI requests return DECERR, WB err SLVERR.
// Translation is from 0x40030000 controller aperture to generated WB byte offsets.
// Keep DATA and CONFIG NoCs independent. The WB_BASE must be derived from csr.json.
module ddr_litedram_axi_wishbone_bridge #(
  parameter int unsigned WB_ADR_BITS = 30,
  parameter logic [31:0] CFG_BASE = 32'h4003_0000,
  parameter logic [31:0] CFG_BYTES = 32'h0000_4000,
  parameter logic [31:0] WB_BASE = 32'h0000_0000,
  parameter int unsigned TIMEOUT_CYCLES = 128
) (
  input  logic clk_i, rst_ni,
  input  logic       s_awvalid,
  output logic       s_awready,
  input  logic [0:0] s_awid,
  input  logic [31:0] s_awaddr,
  input  logic [7:0] s_awlen,
  input  logic [2:0] s_awsize,
  input  logic [1:0] s_awburst,
  input  logic       s_wvalid,
  output logic       s_wready,
  input  logic [31:0] s_wdata,
  input  logic [3:0] s_wstrb,
  input  logic       s_wlast,
  output logic       s_bvalid,
  input  logic       s_bready,
  output logic [0:0] s_bid,
  output logic [1:0] s_bresp,
  input  logic       s_arvalid,
  output logic       s_arready,
  input  logic [0:0] s_arid,
  input  logic [31:0] s_araddr,
  input  logic [7:0] s_arlen,
  input  logic [2:0] s_arsize,
  input  logic [1:0] s_arburst,
  output logic       s_rvalid,
  input  logic       s_rready,
  output logic [0:0] s_rid,
  output logic [31:0] s_rdata,
  output logic [1:0] s_rresp,
  output logic       s_rlast,
  output logic                    wb_ctrl_cyc,
  output logic                    wb_ctrl_stb,
  output logic                    wb_ctrl_we,
  output logic [WB_ADR_BITS-1:0]  wb_ctrl_adr,
  output logic [31:0]             wb_ctrl_dat_w,
  input  logic [31:0]             wb_ctrl_dat_r,
  output logic [3:0]              wb_ctrl_sel,
  output logic [2:0]              wb_ctrl_cti,
  output logic [1:0]              wb_ctrl_bte,
  input  logic                    wb_ctrl_ack,
  input  logic                    wb_ctrl_err
);
  typedef enum logic [2:0] {IDLE, W_DATA, WB, B_RESP, R_RESP} state_t;
  state_t state;
  logic is_write;
  logic [0:0] txn_id;
  logic [1:0] response;
  logic [WB_ADR_BITS-1:0] word_addr;
  logic [31:0] write_data, read_data;
  logic [3:0] write_strobe;
  logic bad_request;
  logic [8:0] remaining_beats;
  logic [31:0] timeout_count;

  function automatic logic valid_access(
    input logic [31:0] address,
    input logic [7:0] length,
    input logic [2:0] size,
    input logic [1:0] burst
  );
    logic [32:0] last_byte;
    logic [32:0] mapped_end;
    begin
      last_byte = {1'b0, address} + 33'd4;
      mapped_end = {1'b0, WB_BASE} + {1'b0, CFG_BYTES};
      valid_access = length == 0 && size == 3'd2 && burst == 2'b01 &&
        address[1:0] == 0 &&
        address >= CFG_BASE && last_byte <= ({1'b0, CFG_BASE} + {1'b0, CFG_BYTES}) &&
        ({1'b0, WB_BASE} + {1'b0, address} - {1'b0, CFG_BASE} + 33'd4) <= mapped_end &&
        ({1'b0, WB_BASE} + {1'b0, address} - {1'b0, CFG_BASE} + 33'd4) <= (33'd4 << WB_ADR_BITS);
    end
  endfunction

  always_comb begin
    s_awready = state == IDLE;
    s_arready = state == IDLE && !s_awvalid;
    s_wready = state == W_DATA;
    s_bvalid = state == B_RESP;
    s_bid = txn_id;
    s_bresp = response;
    s_rvalid = state == R_RESP;
    s_rid = txn_id;
    s_rdata = read_data;
    s_rresp = response;
    s_rlast = s_rvalid;
    wb_ctrl_cyc = state == WB;
    wb_ctrl_stb = state == WB;
    wb_ctrl_we = is_write;
    wb_ctrl_adr = word_addr;
    wb_ctrl_dat_w = write_data;
    wb_ctrl_sel = write_strobe;
    wb_ctrl_cti = 3'b000; // Classic Wishbone, no implicit bursts.
    wb_ctrl_bte = 2'b00;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state <= IDLE;
      is_write <= 0;
      txn_id <= '0;
      word_addr <= '0;
      response <= 0;
      read_data <= 0;
      write_data <= 0;
      write_strobe <= 0;
      bad_request <= 0;
      remaining_beats <= 0;
      timeout_count <= 0;
    end else begin
      case (state)
        IDLE: begin
          timeout_count <= 0;
          response <= 0;
          if (s_awvalid && s_awready) begin
            is_write <= 1;
            txn_id <= s_awid;
            bad_request <= !valid_access(s_awaddr, s_awlen, s_awsize, s_awburst);
            remaining_beats <= {1'b0, s_awlen} + 9'd1;
            word_addr <= WB_ADR_BITS'((WB_BASE + (s_awaddr - CFG_BASE)) >> 2);
            state <= W_DATA;
          end else if (s_arvalid && s_arready) begin
            is_write <= 0;
            txn_id <= s_arid;
            bad_request <= !valid_access(s_araddr, s_arlen, s_arsize, s_arburst);
            word_addr <= WB_ADR_BITS'((WB_BASE + (s_araddr - CFG_BASE)) >> 2);
            if (!valid_access(s_araddr, s_arlen, s_arsize, s_arburst)) begin
              response <= 2'b11;
              read_data <= '0;
              state <= R_RESP;
            end else begin
              write_strobe <= 4'hf;
              state <= WB;
            end
          end
        end
        W_DATA: if (s_wvalid && s_wready) begin
          write_data <= s_wdata;
          write_strobe <= s_wstrb;
          if (s_wlast != (remaining_beats == 9'd1)) begin
            // Reject mismatched WLAST; it is a malformed upstream master.
            $fatal(1, "DDR CSR AXI WLAST mismatch");
          end
          remaining_beats <= remaining_beats - 9'd1;
          if (remaining_beats == 9'd1) begin
            if (bad_request) begin
              response <= 2'b11;
              state <= B_RESP;
            end else state <= WB;
          end
        end
        WB: begin
          if (wb_ctrl_ack || wb_ctrl_err) begin
            response <= wb_ctrl_err ? 2'b10 : 2'b00;
            if (!is_write) read_data <= wb_ctrl_dat_r;
            state <= is_write ? B_RESP : R_RESP;
          end else if (timeout_count == TIMEOUT_CYCLES - 1) begin
            response <= 2'b10;
            read_data <= '0;
            state <= is_write ? B_RESP : R_RESP;
          end else timeout_count <= timeout_count + 1;
        end
        B_RESP: if (s_bvalid && s_bready) state <= IDLE;
        R_RESP: if (s_rvalid && s_rready) state <= IDLE;
        default: state <= IDLE;
      endcase
    end
  end
  initial begin
    assert (WB_ADR_BITS >= 1 && WB_ADR_BITS <= 30)
      else $fatal(1, "invalid generated Wishbone address width");
    assert (CFG_BYTES == 32'h4000 && CFG_BASE[13:0] == 0)
      else $fatal(1, "DDR controller Config NoC aperture must be aligned 16KiB");
    assert (TIMEOUT_CYCLES >= 2) else $fatal(1, "Wishbone timeout too short");
  end
endmodule
