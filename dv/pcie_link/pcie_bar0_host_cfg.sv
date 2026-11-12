// Host-visible PCIe Type-0 BAR0 semantics at the pinned OpenPCIe AXI-Lite
// configuration register bus. The original SystemRDL-generated register block
// still handles all OTHER configuration fields. Only BAR0 (0x10) sizing,
// assignment and COMMAND.MemorySpaceEnable (0x04[1]) are overlaid here.
//
// Local device BAR aperture comes exclusively from the committed PRE-LINK
// register block; the Root Complex assigns the different PCI bus address.
// This module observes real config-bus handshakes; never forces LTSSM/L0.
`timescale 1ns/1ps
module pcie_bar0_host_cfg (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        device_bar_committed_i,
  input  logic [31:0] device_bar_aperture_i,
  input  logic        awvalid_i,
  input  logic        awready_i,
  input  logic [8:0]  awaddr_i,
  input  logic        wvalid_i,
  input  logic        wready_i,
  input  logic [31:0] wdata_i,
  input  logic [3:0]  wstrb_i,
  input  logic        arvalid_i,
  input  logic        arready_i,
  input  logic [8:0]  araddr_i,
  input  logic [31:0] rdata_from_rdl_i,
  output logic [31:0] rdata_to_host_o,
  output logic [31:0] host_bar0_bus_base_o,
  output logic        host_memory_enable_o,
  output logic        bar0_probe_o,
  output logic        cfg_violation_o
);
  localparam logic [8:0] COMMAND_OFFSET = 9'h004;
  localparam logic [8:0] BAR0_OFFSET = 9'h010;

  logic aw_pending, w_pending;
  logic [8:0] aw_addr_q;
  logic [31:0] w_data_q;
  logic [3:0] w_strb_q;
  logic [31:0] host_base_q;
  logic mse_q, probe_q;
  logic read_bar_q, read_command_q;
  logic [31:0] bar_read_q, command_mse_read_q;
  wire [31:0] size_mask = ~(device_bar_aperture_i - 32'd1) &
                            32'hffff_fff0;
  assign host_bar0_bus_base_o = host_base_q;
  assign host_memory_enable_o = mse_q;
  assign bar0_probe_o = probe_q;

  always_comb begin
    rdata_to_host_o = rdata_from_rdl_i;
    if (read_bar_q)
      rdata_to_host_o = bar_read_q;
    else if (read_command_q)
      rdata_to_host_o = (rdata_from_rdl_i & 32'hffff_fffd) |
                        command_mse_read_q;
  end

  // Passive, bounded diagnostics from the real internal PCIe configuration
  // AXI-Lite path. These never drive the overlay or fabricate completions.
  // Each event identifies which handshake actually occurred, allowing the
  // root cause of a zero BAR sizing response to be distinguished from an
  // unaccepted write or a readback mux timing error.
`ifndef SYNTHESIS
  integer cfg_probe_log_count = 0;
  always @(posedge clk_i) if (rst_ni && cfg_probe_log_count < 40) begin
    if ((awvalid_i && awready_i) || (wvalid_i && wready_i) ||
        (arvalid_i && arready_i)) begin
      $display("PCIE_EP_BAR_CFG_AXI: AW=%b W=%b AR=%b awaddr=%h araddr=%h wdata=%h committed=%b pending_aw=%b pending_w=%b probe=%b mask=%h hostbase=%h readbar=%b rdldata=%h hostdata=%h at %0t",
               awvalid_i && awready_i, wvalid_i && wready_i,
               arvalid_i && arready_i, awaddr_i, araddr_i, wdata_i,
               device_bar_committed_i, aw_pending, w_pending, probe_q,
               size_mask, host_base_q, read_bar_q, rdata_from_rdl_i,
               rdata_to_host_o, $time);
      cfg_probe_log_count <= cfg_probe_log_count + 1;
    end
  end
`endif

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      aw_pending <= 1'b0;
      w_pending <= 1'b0;
      aw_addr_q <= '0;
      w_data_q <= '0;
      w_strb_q <= '0;
      host_base_q <= '0;
      mse_q <= 1'b0;
      probe_q <= 1'b0;
      read_bar_q <= 1'b0;
      read_command_q <= 1'b0;
      bar_read_q <= '0;
      command_mse_read_q <= '0;
      cfg_violation_o <= 1'b0;
    end else begin
      // AXI-Lite AW and W are independent. Pair them; do not infer a write
      // from TVALID without the corresponding READY acceptance.
      if (awvalid_i && awready_i) begin
        if (aw_pending) cfg_violation_o <= 1'b1;
        else begin
          aw_addr_q <= awaddr_i;
          aw_pending <= 1'b1;
        end
      end
      if (wvalid_i && wready_i) begin
        if (w_pending) cfg_violation_o <= 1'b1;
        else begin
          w_data_q <= wdata_i;
          w_strb_q <= wstrb_i;
          w_pending <= 1'b1;
        end
      end
      if (aw_pending && w_pending) begin
        aw_pending <= 1'b0;
        w_pending <= 1'b0;
        if (aw_addr_q == BAR0_OFFSET) begin
          if (!device_bar_committed_i || mse_q || w_strb_q != 4'hf)
            cfg_violation_o <= 1'b1;
          else if (w_data_q == 32'hffff_ffff) begin
            // The RC writes all ones, then reads the BAR aperture mask.
            probe_q <= 1'b1;
          end else begin
            host_base_q <= w_data_q & size_mask;
            probe_q <= 1'b0;
          end
        end else if (aw_addr_q == COMMAND_OFFSET && w_strb_q[0]) begin
          if (!device_bar_committed_i && w_data_q[1])
            cfg_violation_o <= 1'b1;
          else
            mse_q <= w_data_q[1];
        end
      end

      // Snapshot the overlay value at the *accepted* configuration read:
      // it stays stable if the original generated reg block stalls RREADY.
      if (arvalid_i && arready_i) begin
        read_bar_q <= (araddr_i == BAR0_OFFSET);
        read_command_q <= (araddr_i == COMMAND_OFFSET);
        if (araddr_i == BAR0_OFFSET)
          bar_read_q <= device_bar_committed_i ?
                        (probe_q ? size_mask : host_base_q) : 32'd0;
        if (araddr_i == COMMAND_OFFSET)
          command_mse_read_q <= {30'b0,mse_q,1'b0};
      end
    end
  end
endmodule
