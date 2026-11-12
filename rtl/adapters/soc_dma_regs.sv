`timescale 1ns/1ps
// PULP AXI-to-AXI-Lite + axi_lite_regs own the bus protocol.
// This bounded shim commits a 64-bit descriptor head atomically into the
// upstream iDMA APB frontend after CPU/verification writes 32-bit halves.
// No custom AXI interconnect, arbitration or DMA backend is implemented here.
//
// 0x00 HEAD_LO   RW (stage only)
// 0x04 HEAD_HI   RW (stage only)
// 0x08 COMMAND   RW: bit0 submit, bit1 acknowledge pending IRQ
// 0x0c STATUS    RO: bit0 command in flight, bit1 IRQ pending,
//                   bit2 APB submission error, bit3 raw IRQ
// A second submission is blocked until the previous APB write has accepted.
// Callers must separately retire DMA jobs before reusing descriptor memory.
module soc_dma_regs #(
  parameter type axi_req_t = logic,
  parameter type axi_rsp_t = logic,
  parameter type lite_req_t = logic,
  parameter type lite_rsp_t = logic,
  parameter int unsigned AxiIdWidth = 1
) (
  input logic clk_i, rst_ni,
  input axi_req_t cfg_req_i,
  output axi_rsp_t cfg_rsp_o,
  output logic [63:0] apb_addr_o, apb_data_o,
  output logic apb_write_o, apb_select_o, apb_enable_o,
  input logic apb_ready_i, apb_error_i, irq_raw_i,
  output logic irq_pending_o
);
  lite_req_t lite_req;
  lite_rsp_t lite_rsp;
  axi_to_axi_lite #(
    .AxiAddrWidth(32), .AxiDataWidth(32), .AxiIdWidth(AxiIdWidth),
    .AxiUserWidth(1), .AxiMaxWriteTxns(2), .AxiMaxReadTxns(2),
    .full_req_t(axi_req_t), .full_resp_t(axi_rsp_t),
    .lite_req_t(lite_req_t), .lite_resp_t(lite_rsp_t)
  ) u_axi_to_lite (
    .clk_i, .rst_ni, .slv_req_i(cfg_req_i), .slv_resp_o(cfg_rsp_o),
    .mst_req_o(lite_req), .mst_resp_i(lite_rsp)
  );

  logic [15:0][7:0] regs_q, regs_d;
  logic [15:0] regs_load;
  typedef enum logic [1:0] {READY, SETUP, ACCESS, CLEAR} state_t;
  state_t state_q;
  logic [63:0] submitted_head_q;
  logic irq_pending_q, submission_error_q;

  always_comb begin
    regs_d = '0;
    regs_load = '0;
    // Read-only status bytes are updated from hardware on every cycle.
    regs_load[15:12] = 4'hf;
    regs_d[12][0] = state_q != READY;
    regs_d[12][1] = irq_pending_q;
    regs_d[12][2] = submission_error_q;
    regs_d[12][3] = irq_raw_i;
    if (state_q != READY) begin
      // Clear the accepted one-shot command and hold this register while
      // native APB is busy. A colliding AXI-Lite COMMAND write then waits
      // for READY instead of overwriting/dropping a pending chain head.
      regs_load[11:8] = 4'hf;
    end
  end

  axi_lite_regs #(
    .RegNumBytes(16), .AxiAddrWidth(32), .AxiDataWidth(32),
    .AxiReadOnly(16'hf000),
    .req_lite_t(lite_req_t), .resp_lite_t(lite_rsp_t)
  ) u_csr (
    .clk_i, .rst_ni, .axi_req_i(lite_req), .axi_resp_o(lite_rsp),
    .wr_active_o(), .rd_active_o(),
    .reg_d_i(regs_d), .reg_load_i(regs_load), .reg_q_o(regs_q)
  );

  assign apb_addr_o = '0; // upstream desc64 DESC_ADDR register
  assign apb_data_o = submitted_head_q;
  assign apb_write_o = 1'b1;
  assign apb_select_o = state_q == SETUP || state_q == ACCESS;
  assign apb_enable_o = state_q == ACCESS;
  assign irq_pending_o = irq_pending_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= READY;
      submitted_head_q <= '0;
      irq_pending_q <= 1'b0;
      submission_error_q <= 1'b0;
    end else begin
      if (irq_raw_i) irq_pending_q <= 1'b1;
      case (state_q)
        READY: begin
          if (regs_q[8][0]) begin
            submitted_head_q <= {regs_q[7], regs_q[6], regs_q[5], regs_q[4],
                                 regs_q[3], regs_q[2], regs_q[1], regs_q[0]};
            state_q <= SETUP;
          end else if (regs_q[8][1]) begin
            state_q <= CLEAR;
          end
        end
        SETUP: state_q <= ACCESS;
        ACCESS: if (apb_ready_i) begin
          if (apb_error_i) submission_error_q <= 1'b1;
          state_q <= CLEAR;
        end
        CLEAR: begin
          // Acknowledge only when software wrote the ACK bit and not
          // concurrently with a fresh hardware IRQ.
          if (regs_q[8][1] && !irq_raw_i) irq_pending_q <= 1'b0;
          state_q <= READY;
        end
        default: state_q <= READY;
      endcase
    end
  end
endmodule
