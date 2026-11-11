`timescale 1ns/1ps
// Experimental independent RC <-> original endpoint RTL bench.
// This harness NEVER sets link_up_o or LTSSM state. Do not claim L0 from compile.
module test #(
  parameter bit PARTNER_PRESENT = 1'b1,
  parameter integer MAX_PIPE_CYCLES = 100000
);
  logic symbol_clk = 0;
  logic pipe_clk = 0;
  logic core_clk = 0;
  always #2 symbol_clk = ~symbol_clk; // Gen1 250 MHz
  always #8 pipe_clk = ~pipe_clk;     // 32-bit Gen1: 62.5 MHz
  always #5 core_clk = ~core_clk;     // Endpoint core CLK_RATE=100 MHz
  logic nreset = 0;
  initial begin
    repeat (16) @(negedge pipe_clk);
    nreset = 1;
  end
  wire [31:0] host_txdata, host_rxdata, ep_txdata, ep_rxdata;
  wire [3:0] host_txdatak, host_rxdatak, ep_txdatak, ep_rxdatak;
  wire host_txelecidle, host_rxelecidle;
  wire ep_txdata_valid, ep_txelecidle, ep_rxdata_valid, ep_rxelecidle;
  wire ep_txdetectrx, phy_phystatus;
  wire [2:0] phy_rxstatus;
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
  pcieVHostPipex1 #(.NodeNum(0), .EndPoint(0), .DataWidth(32)) host (
    .pcieclk(symbol_clk), .pclk(pipe_clk), .nreset(nreset),
    .Gen2ClkSel(), .ClkOut(), .ElecIdleOut(host_txelecidle),
    .ElecIdleIn(host_rxelecidle),
    .RxData(host_rxdata), .RxDataK(host_rxdatak),
    .TxData(host_txdata), .TxDataK(host_txdatak)
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
  pcie_phy_top #(.CLK_RATE(100), .MAX_NUM_LANES(1), .DATA_WIDTH(32),
                 .IS_ROOT_PORT(0), .IS_UPSTREAM(1)) ep (
    .clk_i(core_clk), .rst_i(~nreset), .en_i(nreset),
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
    .tx_elec_idle(1'b0), .phy_ready_en(nreset), .link_up_o(ep_link_up),
    .s_tlp_axis_tdata(32'b0), .s_tlp_axis_tkeep(4'b0),
    .s_tlp_axis_tvalid(1'b0), .s_tlp_axis_tlast(1'b0),
    .s_tlp_axis_tuser(5'b0), .s_tlp_axis_tready(),
    .m_tlp_axis_tdata(), .m_tlp_axis_tkeep(),
    .m_tlp_axis_tvalid(), .m_tlp_axis_tlast(),
    .m_tlp_axis_tuser(), .m_tlp_axis_tready(1'b1)
  );

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
    $display("PCIE_TRACE: timeout detect=%0d phy=%0d epTx=%0d hostTx=%0d ltssm=%h link=%b",
       detect_count, phy_status_count, ep_tx_count, rc_tx_count,
       ltssm_debug_state, ep_link_up);
    $fatal(1, "Unqualified cross-provider link: no proven L0 handshake");
  end
endmodule
