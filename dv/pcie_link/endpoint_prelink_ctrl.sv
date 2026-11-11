// SPDX-License-Identifier: MIT
// Device-local PCIe endpoint bring-up register prototype. This block is NOT
// the host-visible PCIe Type-0 BAR config register and does not assign a PCI
// bus address. A firmware/Config-NoC adapter supplies single-cycle cfg writes.
// BAR advertisement into OpenPCIe's generated config register RTL is a
// separate, explicitly unqualified integration step.
//
// BAR0_APERTURE (0x00): bytes, 4KiB..1MiB, power-of-two.
// BAR0_TARGET   (0x04): 32-bit local NoC address within selected SRAM window.
// CONTROL       (0x08): bit0 commit, bit1 request LTSSM start.
// STATUS        (0x0c): bit0 committed, bit1 LTSSM allowed,
//                       bit2 transaction ready, bit3 rejected write.
`timescale 1ns/1ps
module pcie_endpoint_prelink_ctrl #(
  parameter logic [31:0] SRAM_BASE = 32'h1200_0000,
  parameter logic [31:0] SRAM_SIZE = 32'h0010_0000
) (
  input logic clk_i,
  input logic rst_ni,
  input logic cfg_wr_i,
  input logic [3:0] cfg_addr_i,
  input logic [31:0] cfg_wdata_i,
  input logic [3:0] cfg_wstrb_i,
  output logic [31:0] cfg_rdata_o,
  output logic cfg_error_o,
  input logic phy_ready_i,
  input logic noc_ready_i,
  input logic link_up_i,
  input logic host_mem_enable_i,
  output logic [31:0] bar0_aperture_o,
  output logic [31:0] bar0_local_target_o,
  output logic [31:0] bar0_size_mask_o,
  output logic bar_config_committed_o,
  output logic ltssm_enable_o,
  output logic bar_mem_ready_o
);
  logic seen_size, seen_target;
  logic start_requested;
  logic error_latched;
  logic [31:0] size_q, target_q;
  logic size_ok, target_ok;

  assign size_ok = size_q >= 32'h1000 &&
                   size_q <= SRAM_SIZE &&
                   (size_q & (size_q - 32'd1)) == 0;
  // Expanded arithmetic prevents wraparound near the end of address space.
  assign target_ok = target_q >= SRAM_BASE &&
                     {1'b0,target_q} + {1'b0,size_q} <=
                     {1'b0,SRAM_BASE} + {1'b0,SRAM_SIZE} &&
                     (target_q & (size_q - 32'd1)) == 0;

  assign bar0_aperture_o = size_q;
  assign bar0_local_target_o = target_q;
  // PCIe 32-bit memory BAR size-mask bits; type = 32-bit non-prefetchable.
  assign bar0_size_mask_o = bar_config_committed_o ?
                            (~(size_q - 32'd1) & 32'hffff_fff0) : 32'd0;
  assign ltssm_enable_o = bar_config_committed_o &&
                          start_requested && phy_ready_i;
  // L0 does not imply that NoC memory accesses are safe yet.
  assign bar_mem_ready_o = ltssm_enable_o && link_up_i &&
                           noc_ready_i && host_mem_enable_i;
  assign cfg_error_o = error_latched;

  always_comb begin
    case (cfg_addr_i)
      4'h0: cfg_rdata_o = size_q;
      4'h4: cfg_rdata_o = target_q;
      4'h8: cfg_rdata_o = {30'b0,start_requested,bar_config_committed_o};
      4'hc: cfg_rdata_o = {28'b0,error_latched,bar_mem_ready_o,
                           ltssm_enable_o,bar_config_committed_o};
      default: cfg_rdata_o = 32'd0;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      size_q <= 32'd0;
      target_q <= 32'd0;
      seen_size <= 1'b0;
      seen_target <= 1'b0;
      start_requested <= 1'b0;
      bar_config_committed_o <= 1'b0;
      error_latched <= 1'b0;
    end else if (cfg_wr_i) begin
      if (cfg_wstrb_i != 4'hf) begin
        error_latched <= 1'b1;
      end else begin
        case (cfg_addr_i)
          4'h0: begin
            if (bar_config_committed_o) error_latched <= 1'b1;
            else begin size_q <= cfg_wdata_i; seen_size <= 1'b1; end
          end
          4'h4: begin
            if (bar_config_committed_o) error_latched <= 1'b1;
            else begin target_q <= cfg_wdata_i; seen_target <= 1'b1; end
          end
          4'h8: begin
            if (cfg_wdata_i == 32'h1) begin
              if (bar_config_committed_o || !seen_size || !seen_target ||
                  !size_ok || !target_ok)
                error_latched <= 1'b1;
              else bar_config_committed_o <= 1'b1;
            end else if (cfg_wdata_i == 32'h2) begin
              if (!bar_config_committed_o) error_latched <= 1'b1;
              else start_requested <= 1'b1;
            end else error_latched <= 1'b1;
          end
          default: error_latched <= 1'b1;
        endcase
      end
    end
  end
endmodule
