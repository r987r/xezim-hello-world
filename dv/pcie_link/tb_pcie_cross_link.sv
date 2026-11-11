`timescale 1ns/1ps
// Experimental independent RC <-> original endpoint RTL bench.
// This harness NEVER sets link_up_o or LTSSM state. Do not claim L0 from compile.
module test #(
  // OFF by default: PCIe timer reduction must be explicit in CI.
  // This accelerates LTSSM timers only; it never drives link_up.
  parameter bit SIM_FORCE_FAST_LTSSM = 1'b0,
  parameter bit PARTNER_PRESENT = 1'b1,
  parameter integer MAX_PIPE_CYCLES = 100000
);
  logic symbol_clk = 0;
  logic pipe_clk = 0;
  logic core_clk = 0;
  always #2 symbol_clk = ~symbol_clk; // Gen1 250 MHz
  always #4 pipe_clk = ~pipe_clk;     // 16-bit Gen1: 125 MHz, upstream PHY's actual PIPE width
  always #5 core_clk = ~core_clk;     // Endpoint core CLK_RATE=100 MHz
  logic nreset = 0;
  initial begin
    if (SIM_FORCE_FAST_LTSSM)
      $display("PCIE_SIM_FORCE_FAST_LTSSM: ENABLED override=512x");
    else
      $display("PCIE_SIM_FORCE_FAST_LTSSM: DISABLED");
  end
  // Test-only CPU/Config-NoC surrogate for the standalone cross-link bench.
  // Real CPU firmware and Config NoC integration remain separate proof gates.
  logic prelink_wr = 0;
  logic [3:0] prelink_addr = '0;
  logic [31:0] prelink_wdata = '0;
  wire [31:0] prelink_rdata, bar_aperture, bar_target, bar_mask;
  wire prelink_error, bar_committed, ltssm_permitted, bar_mem_ready;
  logic noc_ready = 0;
  // From actual host configuration TLP, not a TB-assigned enable.
  pcie_endpoint_prelink_ctrl prelink (
    .clk_i(core_clk), .rst_ni(nreset), .cfg_wr_i(prelink_wr),
    .cfg_addr_i(prelink_addr), .cfg_wdata_i(prelink_wdata),
    .cfg_wstrb_i(4'hf), .cfg_rdata_o(prelink_rdata),
    .cfg_error_o(prelink_error), .phy_ready_i(nreset),
    .noc_ready_i(noc_ready), .link_up_i(ep_link_up),
    .host_mem_enable_i(host_memory_enable),
    .bar0_aperture_o(bar_aperture), .bar0_local_target_o(bar_target),
    .bar0_size_mask_o(bar_mask), .bar_config_committed_o(bar_committed),
    .ltssm_enable_o(ltssm_permitted), .bar_mem_ready_o(bar_mem_ready)
  );

  task automatic cfg_prelink(input logic [3:0] addr,
                              input logic [31:0] data);
    @(negedge core_clk);
    prelink_addr = addr; prelink_wdata = data; prelink_wr = 1'b1;
    @(negedge core_clk);
    prelink_wr = 1'b0;
  endtask

  initial begin
    repeat (16) @(negedge pipe_clk);
    nreset = 1;
    // Host may already be running its independent root-complex model.
    // Device decides which BAR capability to present before enabling LTSSM.
    repeat (4) @(negedge core_clk);
    if (ltssm_permitted || ep_link_up)
      $fatal(1, "link started before device BAR preconfiguration");
    cfg_prelink(4'h0, 32'h0000_1000);
    cfg_prelink(4'h4, 32'h1200_0000);
    cfg_prelink(4'h8, 32'h0000_0001);
    if (!bar_committed || bar_mask != 32'hffff_f000 || prelink_error)
      $fatal(1, "prelink BAR configuration commit did not succeed");
    $display("PCIE_DEVICE_PRELINK: committed BAR0 size=%h target=%h mask=%h",
             bar_aperture, bar_target, bar_mask);
    cfg_prelink(4'h8, 32'h0000_0002);
    if (!ltssm_permitted)
      $fatal(1, "device did not permit LTSSM after BAR commit");
    $display("PCIE_DEVICE_PRELINK: LTSSM enable released after BAR commit");
  end
  // Upstream endpoint reports Gen1 PIPE_WIDTH=16, so run the RC at 16 bits
  // rather than incorrectly presenting four host bytes per endpoint beat.
  // The 32-bit adapter shell is zero-extended only: the physical exchange
  // remains exactly two bytes + two K flags per 125 MHz PIPE beat.
  wire [15:0] rc_txdata16, rc_rxdata16;
  wire [1:0] rc_txdatak2, rc_rxdatak2;
  wire [31:0] host_txdata, host_rxdata, ep_txdata, ep_rxdata;
  wire [3:0] host_txdatak, host_rxdatak, ep_txdatak, ep_rxdatak;
  assign host_txdata = {16'h0, rc_txdata16};
  assign host_txdatak = {2'b00, rc_txdatak2};
  assign rc_rxdata16 = host_rxdata[15:0];
  assign rc_rxdatak2 = host_rxdatak[1:0];
  wire host_txelecidle, host_rxelecidle;
  wire ep_txdata_valid, ep_txelecidle, ep_rxdata_valid, ep_rxelecidle;
  wire ep_txdetectrx, phy_phystatus;
  wire [2:0] phy_rxstatus;
  // REAL upstream config TLP path, with source-qualified BAR overlay.
  wire [31:0] ep_rx_tlp_data, ep_cfg_cpl_data;
  wire [3:0] ep_rx_tlp_keep, ep_cfg_cpl_keep;
  wire [4:0] ep_rx_tlp_user, ep_cfg_cpl_user;
  wire ep_rx_tlp_valid, ep_rx_tlp_last, ep_rx_tlp_ready;
  wire ep_cfg_cpl_valid, ep_cfg_cpl_last, ep_cfg_cpl_ready;
  wire [31:0] bar_host_base;
  wire host_bar_probe, host_cfg_violation;
  wire host_memory_enable;
  pcie_config_reg_pkg::pcie_config_reg__in_t cfg_hwif_in;
  assign cfg_hwif_in = '{default:'0};
  pcie_cfg_wrapper #(.DATA_WIDTH(32), .KEEP_WIDTH(4), .USER_WIDTH(5))
  endpoint_cfg (
    .clk_i(core_clk), .rst_i(~nreset),
    .s_axis_tdata(ep_rx_tlp_data), .s_axis_tkeep(ep_rx_tlp_keep),
    .s_axis_tvalid(ep_rx_tlp_valid), .s_axis_tlast(ep_rx_tlp_last),
    .s_axis_tuser(ep_rx_tlp_user), .s_axis_tready(ep_rx_tlp_ready),
    .cpl_axis_tdata(ep_cfg_cpl_data), .cpl_axis_tkeep(ep_cfg_cpl_keep),
    .cpl_axis_tvalid(ep_cfg_cpl_valid), .cpl_axis_tlast(ep_cfg_cpl_last),
    .cpl_axis_tuser(ep_cfg_cpl_user), .cpl_axis_tready(ep_cfg_cpl_ready),
    // Non-configuration requests need the real NoC bridge in full-chip;
    // the isolated L0 test never qualifies BAR memory transactions.
    .m_tlp_axis_tdata(), .m_tlp_axis_tkeep(), .m_tlp_axis_tvalid(),
    .m_tlp_axis_tlast(), .m_tlp_axis_tuser(),
    .m_tlp_axis_tready(1'b0),
    .cfg_bus_number_o(), .cfg_device_number_o(), .cfg_function_number_o(),
    .hwif_in(cfg_hwif_in), .hwif_out(),
    .bar0_device_committed_i(bar_committed),
    .bar0_device_aperture_i(bar_aperture),
    .bar0_host_bus_base_o(bar_host_base),
    .bar0_host_memory_enable_o(host_memory_enable),
    .bar0_probe_o(host_bar_probe),
    .bar0_cfg_violation_o(host_cfg_violation)
  );

  wire [20:0] ltssm_debug_state;
  wire ep_link_up;
  wire [1:0] phy_powerdown;
  wire [2:0] phy_rate;
  wire [7:0] pipe_width;
  wire [4:0] ep_function;
  wire [7:0] ep_bus;
  wire [4:0] ep_device;
  wire [2:0] ep_func;
  integer detect_count = 0;
  integer phy_status_count = 0;
  integer ep_tx_count = 0;
  integer rc_tx_count = 0;
  logic endpoint_l0_reported = 1'b0;

  // Host root complex is the original pinned GPL simulation-only model.
  pcieVHostPipex1 #(.NodeNum(0), .EndPoint(0), .DataWidth(16)) host (
    .pcieclk(symbol_clk), .pclk(pipe_clk), .nreset(nreset),
    .Gen2ClkSel(), .ClkOut(), .ElecIdleOut(host_txelecidle),
    .ElecIdleIn(host_rxelecidle),
    .RxData(rc_rxdata16), .RxDataK(rc_rxdatak2),
    .TxData(rc_txdata16), .TxDataK(rc_txdatak2)
  );

  // Electrical idle and data-valid are not interchangeable.
  pcie_pipe_x1_adapter adapter (
    .reset_n(nreset),
    .ep_txdata(ep_txdata), .ep_txdatak(ep_txdatak),
    .ep_txdata_valid(ep_txdata_valid), .ep_txelecidle(ep_txelecidle),
    .ep_rxdata(ep_rxdata), .ep_rxdatak(ep_rxdatak),
    .ep_rxdata_valid(ep_rxdata_valid), .ep_rxelecidle(ep_rxelecidle),
    .host_txdata(host_txdata), .host_txdatak(host_txdatak),
    .host_txelecidle(host_txelecidle), .host_sample_valid(1'b1),
    .host_rxdata(host_rxdata), .host_rxdatak(host_rxdatak),
    .host_rxelecidle(host_rxelecidle)
  );

  // Behavioral PHY responds to a real receiver detection request; no L0 hack.
  pcie_phy_status_responder #(.RESPONSE_CYCLES(4)) phy (
    .clk(pipe_clk), .reset_n(nreset),
    .receiver_detect(ep_txdetectrx),
    .remote_termination_present(PARTNER_PRESENT),
    .phy_phystatus(phy_phystatus), .phy_rxstatus(phy_rxstatus)
  );

  // Original OpenPCIe endpoint RTL. Unused Gen2+ EQ inputs tied off.
  // Simulation-only acceleration of the original LTSSM's Detect.Quiet
  // timeout. State transitions and TS1/TS2 processing remain original RTL.
  pcie_phy_top #(.SIM_FAST_LINK(SIM_FORCE_FAST_LTSSM), .CLK_RATE(100), .MAX_NUM_LANES(1), .DATA_WIDTH(32),
                 .IS_ROOT_PORT(0), .IS_UPSTREAM(1)) ep (
    .clk_i(core_clk), .rst_i(~nreset), .en_i(ltssm_permitted),
    .pipe_rx_usr_clk_i(pipe_clk), .pipe_tx_usr_clk_i(pipe_clk),
    .fc_initialized_o(),
    .phy_txdata(ep_txdata), .phy_txdata_valid(ep_txdata_valid),
    .phy_txdatak(ep_txdatak), .phy_txstart_block(), .phy_txsync_header(),
    .phy_rxdata(ep_rxdata), .phy_rxdata_valid(ep_rxdata_valid),
    .phy_rxdatak(ep_rxdatak),
    .phy_rxstart_block(1'b0), .phy_rxsync_header(2'b00),
    .phy_txdetectrx(ep_txdetectrx), .phy_txelecidle(ep_txelecidle),
    .phy_txcompliance(), .phy_rxpolarity(),
    .phy_powerdown(phy_powerdown), .phy_rate(phy_rate),
    .phy_rxvalid(ep_rxdata_valid), .phy_phystatus(phy_phystatus),
    .phy_phystatus_rst(1'b0), .phy_rxelecidle(ep_rxelecidle),
    .phy_rxstatus(phy_rxstatus),
    .phy_txmargin(), .phy_txswing(), .phy_txdeemph(),
    .phy_txeq_ctrl(), .phy_txeq_preset(),
    .phy_txeq_coeff(), .phy_txeq_fs(6'b0), .phy_txeq_lf(6'b0),
    .phy_txeq_new_coeff(18'b0), .phy_txeq_done(1'b0),
    .phy_rxeq_ctrl(), .phy_rxeq_txpreset(),
    .phy_rxeq_preset_sel(1'b0), .phy_rxeq_new_txcoeff(18'b0),
    .phy_rxeq_adapt_done(1'b0), .phy_rxeq_done(1'b0),
    .pipe_width_o(pipe_width),
    .cfg_bus_number_o(ep_bus), .cfg_device_number_o(ep_device),
    .cfg_function_number_o(ep_func),
    .as_mac_in_detect(), .as_cdr_hold_req(),
    .ltssm_debug_state(ltssm_debug_state),
    .tx_elec_idle(1'b0), .phy_ready_en(ltssm_permitted), .link_up_o(ep_link_up),
    .s_tlp_axis_tdata(ep_cfg_cpl_data), .s_tlp_axis_tkeep(ep_cfg_cpl_keep),
    .s_tlp_axis_tvalid(ep_cfg_cpl_valid), .s_tlp_axis_tlast(ep_cfg_cpl_last),
    .s_tlp_axis_tuser(ep_cfg_cpl_user), .s_tlp_axis_tready(ep_cfg_cpl_ready),
    .m_tlp_axis_tdata(ep_rx_tlp_data), .m_tlp_axis_tkeep(ep_rx_tlp_keep),
    .m_tlp_axis_tvalid(ep_rx_tlp_valid), .m_tlp_axis_tlast(ep_rx_tlp_last),
    .m_tlp_axis_tuser(ep_rx_tlp_user), .m_tlp_axis_tready(ep_rx_tlp_ready)
  );

  // Even if L0 trains before NoC boot, do not enable inbound MMIO early.
  always @(posedge core_clk) if (nreset) begin
    if (!bar_committed && ep_link_up)
      $fatal(1, "endpoint L0 observed before BAR configuration commit");
    if (bar_mem_ready && (!noc_ready || !host_memory_enable || !ep_link_up))
      $fatal(1, "BAR memory gate accepted traffic before readiness");
  end

  logic [20:0] ltssm_previous = '0;
  integer detect_quiet_entries = 0, detect_active_entries = 0;
  integer polling_entries = 0, configuration_entries = 0;
  integer ep_ts1_count = 0, ep_ts2_count = 0;
  // Passive *testbench-only* monitors; these wires are never supplied to
  // host firmware or the endpoint state machine as decision inputs.
  always @(posedge pipe_clk) if (nreset) begin
    if (ltssm_debug_state != ltssm_previous) begin
      $display("PCIE_EP_STATE: %h -> %h at %0t", ltssm_previous, ltssm_debug_state, $time);
      if (ltssm_debug_state[19:0] == 20'h041) detect_quiet_entries <= detect_quiet_entries + 1;
      if (ltssm_debug_state[19:0] == 20'h061) detect_active_entries <= detect_active_entries + 1;
      if (ltssm_debug_state[3:0] == 4'h2) polling_entries <= polling_entries + 1;
      if (ltssm_debug_state[3:0] == 4'h3) configuration_entries <= configuration_entries + 1;
    end
    ltssm_previous <= ltssm_debug_state;
    if (ep.ts1_valid[0]) ep_ts1_count <= ep_ts1_count + 1;
    if (ep.ts2_valid[0]) ep_ts2_count <= ep_ts2_count + 1;
  end

  // Never let a mismatched host width masquerade as a protocol failure.
  // The endpoint's own lane manager chooses the PIPE width; this is an
  // independent assertion, not an input or a forced width override.
  logic width_verified = 1'b0;
  always @(posedge pipe_clk) if (nreset && ltssm_permitted &&
                                ltssm_debug_state[3:0] == 4'h2 &&
                                !width_verified) begin
    if (pipe_width !== 8'd16)
      $fatal(1, "Gen1 endpoint PIPE width %0d does not match independent RC DataWidth=16", pipe_width);
    width_verified <= 1'b1;
    $display("PCIE_PIPE_WIDTH_MATCH: RC 16-bit and EP %0d-bit PIPE @125MHz", pipe_width);
  end

  // Passive PIPE diagnostics. This observes encoded lane words on each
  // independent participant's local PIPE port; it does not control either
  // LTSSM, decode data into artificial TS, or relay software state.
  integer host_pipe_words = 0, ep_pipe_words = 0;
  integer host_pipe_samples_printed = 0, ep_pipe_samples_printed = 0;
  always @(posedge pipe_clk) if (nreset && ltssm_permitted) begin
    if (ep_rxdata_valid && !ep_rxelecidle) begin
      host_pipe_words <= host_pipe_words + 1;
      if (ltssm_debug_state[3:0] == 4'h2 && host_pipe_samples_printed < 16) begin
        $display("PCIE_PIPE_RC_TO_EP: data=%h k=%h idle=%b valid=%b at %0t",
                 ep_rxdata, ep_rxdatak, ep_rxelecidle, ep_rxdata_valid, $time);
        host_pipe_samples_printed <= host_pipe_samples_printed + 1;
      end
    end
    if (ep_txdata_valid && !ep_txelecidle) begin
      ep_pipe_words <= ep_pipe_words + 1;
      if (ltssm_debug_state[3:0] == 4'h2 && ep_pipe_samples_printed < 16) begin
        $display("PCIE_PIPE_EP_TO_RC: data=%h k=%h idle=%b valid=%b at %0t",
                 ep_txdata, ep_txdatak, ep_txelecidle, ep_txdata_valid, $time);
        ep_pipe_samples_printed <= ep_pipe_samples_printed + 1;
      end
    end
  end

  // Only observations; no manual injection or forced state.
  always @(posedge pipe_clk) if (nreset) begin
    if (ep_txdetectrx && detect_count == 0) begin
      $display("PCIE_TRACE: receiver-detect request");
      detect_count <= 1;
    end
    if (phy_phystatus) begin
      if (!PARTNER_PRESENT || phy_rxstatus != 3'b011)
        $fatal(1, "PHY status without detected partner");
      phy_status_count <= phy_status_count + 1;
      $display("PCIE_TRACE: PHY receiver present");
    end
    if (ep_txdata_valid && !ep_txelecidle) ep_tx_count <= ep_tx_count + 1;
    if (!host_txelecidle) rc_tx_count <= rc_tx_count + 1;
    if (ep_link_up && phy_status_count == 0)
      $fatal(1, "Endpoint L0 without receiver detection");
    if (ep_link_up && !endpoint_l0_reported) begin
      if (ep_tx_count == 0 || rc_tx_count == 0)
        $fatal(1, "Endpoint L0 without bidirectional PIPE activity");
      endpoint_l0_reported <= 1'b1;
      $display("PCIE_ENDPOINT_L0: original endpoint asserts link_up after receiver-detect and bidirectional PIPE traffic");
    end
  end
  // Original GPL pcievhost hardcodes test.Fatal for fatal bridge events.
  task Fatal;
    $fatal(1, "pcievhost reported a fatal root-complex error");
  endtask

  initial begin
    repeat (MAX_PIPE_CYCLES) @(posedge pipe_clk);
    $display("PCIE_TRACE: timeout detect=%0d phy=%0d epTx=%0d hostTx=%0d ltssm=%h link=%b quiet=%0d active=%0d polling=%0d cfg=%0d ts1=%0d ts2=%0d rcPipe=%0d epPipe=%0d",
       detect_count, phy_status_count, ep_tx_count, rc_tx_count,
       ltssm_debug_state, ep_link_up,
       detect_quiet_entries, detect_active_entries, polling_entries,
       configuration_entries, ep_ts1_count, ep_ts2_count,
       host_pipe_words, ep_pipe_words);
    $fatal(1, "Unqualified cross-provider link: no proven L0 handshake");
  end
endmodule
