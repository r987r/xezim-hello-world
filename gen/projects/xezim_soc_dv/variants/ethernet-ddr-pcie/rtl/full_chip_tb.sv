`timescale 1ns/1ps
// One boot/coordination checker shared by both simulators.
module full_chip_tb (
  input logic [3:0] probe_awid,
  input logic [63:0] probe_awaddr,
  input logic [7:0] probe_awlen,
  input logic [2:0] probe_awsize,
  input logic [1:0] probe_awburst,
  input logic probe_awlock,
  input logic [3:0] probe_awcache,
  input logic [2:0] probe_awprot,
  input logic [3:0] probe_awqos,
  input logic [3:0] probe_awregion,
  input logic probe_awvalid,
  output logic probe_awready,
  input logic [63:0] probe_wdata,
  input logic [7:0] probe_wstrb,
  input logic probe_wlast,
  input logic probe_wvalid,
  output logic probe_wready,
  output logic [3:0] probe_bid,
  output logic [1:0] probe_bresp,
  output logic probe_bvalid,
  input logic probe_bready,
  input logic [3:0] probe_arid,
  input logic [63:0] probe_araddr,
  input logic [7:0] probe_arlen,
  input logic [2:0] probe_arsize,
  input logic [1:0] probe_arburst,
  input logic probe_arlock,
  input logic [3:0] probe_arcache,
  input logic [2:0] probe_arprot,
  input logic [3:0] probe_arqos,
  input logic [3:0] probe_arregion,
  input logic probe_arvalid,
  output logic probe_arready,
  output logic [3:0] probe_rid,
  output logic [63:0] probe_rdata,
  output logic [1:0] probe_rresp,
  output logic probe_rlast,
  output logic probe_rvalid,
  input logic probe_rready,
  input logic cfgprobe_awid,
  input logic [31:0] cfgprobe_awaddr,
  input logic [7:0] cfgprobe_awlen,
  input logic [2:0] cfgprobe_awsize,
  input logic [1:0] cfgprobe_awburst,
  input logic cfgprobe_awlock,
  input logic [3:0] cfgprobe_awcache,
  input logic [2:0] cfgprobe_awprot,
  input logic [3:0] cfgprobe_awqos,
  input logic [3:0] cfgprobe_awregion,
  input logic cfgprobe_awvalid,
  output logic cfgprobe_awready,
  input logic [31:0] cfgprobe_wdata,
  input logic [3:0] cfgprobe_wstrb,
  input logic cfgprobe_wlast,
  input logic cfgprobe_wvalid,
  output logic cfgprobe_wready,
  output logic cfgprobe_bid,
  output logic [1:0] cfgprobe_bresp,
  output logic cfgprobe_bvalid,
  input logic cfgprobe_bready,
  input logic cfgprobe_arid,
  input logic [31:0] cfgprobe_araddr,
  input logic [7:0] cfgprobe_arlen,
  input logic [2:0] cfgprobe_arsize,
  input logic [1:0] cfgprobe_arburst,
  input logic cfgprobe_arlock,
  input logic [3:0] cfgprobe_arcache,
  input logic [2:0] cfgprobe_arprot,
  input logic [3:0] cfgprobe_arqos,
  input logic [3:0] cfgprobe_arregion,
  input logic cfgprobe_arvalid,
  output logic cfgprobe_arready,
  output logic cfgprobe_rid,
  output logic [31:0] cfgprobe_rdata,
  output logic [1:0] cfgprobe_rresp,
  output logic cfgprobe_rlast,
  output logic cfgprobe_rvalid,
  input logic cfgprobe_rready,
  input logic [64-1:0] rx_req_tlp_data,
  input logic [128-1:0] rx_req_tlp_hdr,
  input logic [1-1:0] rx_req_tlp_valid,
  input logic [1-1:0] rx_req_tlp_sop,
  input logic [1-1:0] rx_req_tlp_eop,
  output logic rx_req_tlp_ready,
  output logic [64-1:0] tx_cpl_tlp_data,
  output logic [2-1:0] tx_cpl_tlp_strb,
  output logic [128-1:0] tx_cpl_tlp_hdr,
  output logic [1-1:0] tx_cpl_tlp_valid,
  output logic [1-1:0] tx_cpl_tlp_sop,
  output logic [1-1:0] tx_cpl_tlp_eop,
  input logic tx_cpl_tlp_ready,
  input logic [15:0] completer_id,
  input logic [2:0] max_payload_size,
  output logic status_error_cor,
  output logic status_error_uncor
);
  localparam integer N = 2, MAX_WORDS = 94;
  localparam [N*32-1:0] BASES = {32'h11000000, 32'h10000000};
  localparam [N*32-1:0] WORDS = {32'd21, 32'd94};
  localparam [31:0] MAILBOX = 32'h10000400;
  localparam integer DONE_OFFSET = 36;
  reg clk = 0, rst_n = 0;
  reg gmii_rx_clk = 0, gmii_tx_clk = 0;
  reg gmii_rx_rst = 1, gmii_tx_rst = 1;
  reg [7:0] gmii_rxd = 0;
  reg gmii_rx_dv = 0, gmii_rx_er = 0;
  wire [7:0] gmii_txd;
  wire gmii_tx_en, gmii_tx_er, eth_irq, eth_drop, eth_bad_fcs, eth_tx_failed;
  reg ddr_init_mode = 1, ddr_negative_mode = 0;
  wire rst = ~rst_n;
`ifndef COCOTB_SIM
  always #5 clk = ~clk;
  initial begin repeat (10) @(negedge clk); rst_n = 1; end
`endif
  reg [N-1:0] hold_mask = 0;
  initial if ($test$plusargs("HOLD_SECONDARY")) hold_mask[1] = 1;
  wire [N-1:0] released, fetch_valid, sram_valid, sram_write;
  wire [N*32-1:0] fetch_addr;
  wire [N*64-1:0] sram_addr, sram_data;
  wire [N*8-1:0] sram_strb;
  wire [31:0] rom_reads, flash_reads;
  wire [31:0] pcie_sram_write_count, pcie_sram_read_count;
  wire [63:0] pcie_sram_last_write_addr, pcie_sram_last_read_addr;
`ifdef COCOTB_SIM
  localparam bit ProbeEnable = 1;
`else
  localparam bit ProbeEnable = 0;
`endif
  soc_top #(.ProbeEnable(1'b0), .DmaEnable(1'b1)) dut (.clk_i(clk), .rst_ni(rst_n), .hold_mask_i(hold_mask),
    .released_o(released), .fetch_valid_o(fetch_valid), .fetch_addr_o(fetch_addr),
    .sram_valid_o(sram_valid), .sram_write_o(sram_write), .sram_addr_o(sram_addr),
    .sram_data_o(sram_data), .sram_strb_o(sram_strb), .rom_reads_o(rom_reads), .flash_reads_o(flash_reads),
    .dma_irq_o(), .dma_irq_pending_o(),
    .ddr_init_mode_i(ddr_init_mode),
    .ddr_negative_mode_i(ddr_negative_mode),
    .probe_awid(probe_awid),
    .probe_awaddr(probe_awaddr),
    .probe_awlen(probe_awlen),
    .probe_awsize(probe_awsize),
    .probe_awburst(probe_awburst),
    .probe_awlock(probe_awlock),
    .probe_awcache(probe_awcache),
    .probe_awprot(probe_awprot),
    .probe_awqos(probe_awqos),
    .probe_awregion(probe_awregion),
    .probe_awvalid(probe_awvalid),
    .probe_awready(probe_awready),
    .probe_wdata(probe_wdata),
    .probe_wstrb(probe_wstrb),
    .probe_wlast(probe_wlast),
    .probe_wvalid(probe_wvalid),
    .probe_wready(probe_wready),
    .probe_bid(probe_bid),
    .probe_bresp(probe_bresp),
    .probe_bvalid(probe_bvalid),
    .probe_bready(probe_bready),
    .probe_arid(probe_arid),
    .probe_araddr(probe_araddr),
    .probe_arlen(probe_arlen),
    .probe_arsize(probe_arsize),
    .probe_arburst(probe_arburst),
    .probe_arlock(probe_arlock),
    .probe_arcache(probe_arcache),
    .probe_arprot(probe_arprot),
    .probe_arqos(probe_arqos),
    .probe_arregion(probe_arregion),
    .probe_arvalid(probe_arvalid),
    .probe_arready(probe_arready),
    .probe_rid(probe_rid),
    .probe_rdata(probe_rdata),
    .probe_rresp(probe_rresp),
    .probe_rlast(probe_rlast),
    .probe_rvalid(probe_rvalid),
    .probe_rready(probe_rready),
    .cfgprobe_awid(cfgprobe_awid),
    .cfgprobe_awaddr(cfgprobe_awaddr),
    .cfgprobe_awlen(cfgprobe_awlen),
    .cfgprobe_awsize(cfgprobe_awsize),
    .cfgprobe_awburst(cfgprobe_awburst),
    .cfgprobe_awlock(cfgprobe_awlock),
    .cfgprobe_awcache(cfgprobe_awcache),
    .cfgprobe_awprot(cfgprobe_awprot),
    .cfgprobe_awqos(cfgprobe_awqos),
    .cfgprobe_awregion(cfgprobe_awregion),
    .cfgprobe_awvalid(cfgprobe_awvalid),
    .cfgprobe_awready(cfgprobe_awready),
    .cfgprobe_wdata(cfgprobe_wdata),
    .cfgprobe_wstrb(cfgprobe_wstrb),
    .cfgprobe_wlast(cfgprobe_wlast),
    .cfgprobe_wvalid(cfgprobe_wvalid),
    .cfgprobe_wready(cfgprobe_wready),
    .cfgprobe_bid(cfgprobe_bid),
    .cfgprobe_bresp(cfgprobe_bresp),
    .cfgprobe_bvalid(cfgprobe_bvalid),
    .cfgprobe_bready(cfgprobe_bready),
    .cfgprobe_arid(cfgprobe_arid),
    .cfgprobe_araddr(cfgprobe_araddr),
    .cfgprobe_arlen(cfgprobe_arlen),
    .cfgprobe_arsize(cfgprobe_arsize),
    .cfgprobe_arburst(cfgprobe_arburst),
    .cfgprobe_arlock(cfgprobe_arlock),
    .cfgprobe_arcache(cfgprobe_arcache),
    .cfgprobe_arprot(cfgprobe_arprot),
    .cfgprobe_arqos(cfgprobe_arqos),
    .cfgprobe_arregion(cfgprobe_arregion),
    .cfgprobe_arvalid(cfgprobe_arvalid),
    .cfgprobe_arready(cfgprobe_arready),
    .cfgprobe_rid(cfgprobe_rid),
    .cfgprobe_rdata(cfgprobe_rdata),
    .cfgprobe_rresp(cfgprobe_rresp),
    .cfgprobe_rlast(cfgprobe_rlast),
    .cfgprobe_rvalid(cfgprobe_rvalid),
    .cfgprobe_rready(cfgprobe_rready),
    .rx_req_tlp_data(rx_req_tlp_data),
    .rx_req_tlp_hdr(rx_req_tlp_hdr),
    .rx_req_tlp_valid(rx_req_tlp_valid),
    .rx_req_tlp_sop(rx_req_tlp_sop),
    .rx_req_tlp_eop(rx_req_tlp_eop),
    .rx_req_tlp_ready(rx_req_tlp_ready),
    .tx_cpl_tlp_data(tx_cpl_tlp_data),
    .tx_cpl_tlp_strb(tx_cpl_tlp_strb),
    .tx_cpl_tlp_hdr(tx_cpl_tlp_hdr),
    .tx_cpl_tlp_valid(tx_cpl_tlp_valid),
    .tx_cpl_tlp_sop(tx_cpl_tlp_sop),
    .tx_cpl_tlp_eop(tx_cpl_tlp_eop),
    .tx_cpl_tlp_ready(tx_cpl_tlp_ready),
    .completer_id(completer_id),
    .max_payload_size(max_payload_size),
    .status_error_cor(status_error_cor),
    .status_error_uncor(status_error_uncor),
    .gmii_rx_clk,
    .gmii_rx_rst,
    .gmii_tx_clk,
    .gmii_tx_rst,
    .gmii_rxd,
    .gmii_rx_dv,
    .gmii_rx_er,
    .gmii_txd,
    .gmii_tx_en,
    .gmii_tx_er,
    .eth_irq_o(eth_irq),
    .eth_drop_o(eth_drop),
    .eth_bad_fcs_o(eth_bad_fcs),
    .eth_tx_failed_o(eth_tx_failed),
    .pcie_sram_write_count(pcie_sram_write_count),
    .pcie_sram_read_count(pcie_sram_read_count),
    .pcie_sram_last_write_addr(pcie_sram_last_write_addr),
    .pcie_sram_last_read_addr(pcie_sram_last_read_addr));
  reg [31:0] expected [0:N*MAX_WORDS-1];
  reg [MAX_WORDS-1:0] copied [0:N-1];
  reg [N-1:0] init_mask = 0, hello_mask = 0, check_mask = 0, app_fetch = 0;
  reg init_complete = 0, run_complete = 0, check_complete = 0, pass_flag = 0;
  always @(posedge clk) if (rst_n && ddr_negative_mode && (!pass_flag || ddr_init_mode)) $fatal(1, "DDR negative test takeover before CPU CHECK/DFII init");
  reg [31:0] cpu_dma_evidence = 0;
  reg cpu_dma_success = 0;
  reg [191:0] cpu_dma_addresses = 0;
  reg [5:0] cpu_dma_address_seen = 0;
  reg [N-1:0] previous_release = 0;
  integer phase = 0, previous_phase = 0, cycles = 0, stalled = 0;
  integer i, lane, index, core, off;
  reg [31:0] address, value;
  reg copied_all;
  initial begin
    $readmemh("gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/rtl/compute0.hex", expected, 0*MAX_WORDS, 0*MAX_WORDS+93);
    copied[0] = '0;
    $readmemh("gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/rtl/compute1.hex", expected, 1*MAX_WORDS, 1*MAX_WORDS+20);
    copied[1] = '0;
  end
  always @(posedge clk) if (rst_n) begin
    cycles <= cycles + 1;
    if (cycles > 2500000) $fatal(1, "FAIL fullchip overall boot timeout");
    copied_all = 1;
    for (i=0; i<N; i=i+1)
      for (index=0; index<WORDS[i*32 +: 32]; index=index+1) if (!copied[i][index]) copied_all = 0;
    for (i=0; i<N; i=i+1) begin
      if (fetch_valid[i]) begin
        if (!released[i]) $fatal(1, "FAIL fullchip fetch while CPU held in reset");
        if (fetch_addr[i*32 +: 32] >= BASES[i*32 +: 32] && fetch_addr[i*32 +: 32] < BASES[i*32 +: 32] + WORDS[i*32 +: 32]*4) app_fetch[i] <= 1;
      end
      if (i>0 && released[i] && !previous_release[i] && !copied_all)
        $fatal(1, "FAIL fullchip CPU released before bus-driven firmware copies");
      if (sram_valid[i] && sram_write[i]) begin
        for (lane=0; lane<2; lane=lane+1) begin
          if (sram_strb[i*8 + lane*4 +: 4] == 4'hf) begin
            address = (sram_addr[i*64 +: 32] & 32'hfffffff8) + lane*4;
            value = sram_data[i*64 + lane*32 +: 32];
            if (address >= BASES[i*32 +: 32] && address < BASES[i*32 +: 32] + WORDS[i*32 +: 32]*4) begin
              index = (address - BASES[i*32 +: 32])/4;
              if (value !== expected[i*MAX_WORDS+index]) $fatal(1, "FAIL fullchip copied firmware mismatch CPU=%0d word=%0d", i, index);
              copied[i][index] <= 1;
            end
            if (i==0) begin
              for (integer k=0; k<6; k=k+1) begin
                if (address==MAILBOX+68+k*4) begin
                  cpu_dma_addresses[k*32 +: 32] <= value;
                  cpu_dma_address_seen[k] <= 1;
                end
              end
            end
            if (i==0 && address==MAILBOX+64) begin
              cpu_dma_evidence <= value;
              if (value==32'he700600d) cpu_dma_success <= 1;
              $display("CPU C DMA evidence 0x%08x",value);
            end
            if (i==0 && address >= MAILBOX && address <= MAILBOX + DONE_OFFSET) begin
              off = address - MAILBOX;
              if (off==0 && value!=0) begin
                if (value==2) begin
                  if (&init_mask !== 1'b1) $fatal(1, "FAIL fullchip run before all CPUs initialized");
                  init_complete <= 1;
                  $display("SOC_FLOW_V1|%0d|init|cpu0|firmware_init|pass", $time);
                  $display("SOC_FLOW_V1|%0d|run|cpu0|firmware_run|start", $time);
                  $display("PHASE init complete: all CPUs ready");
                end else if (value==3) begin
                  if (&hello_mask !== 1'b1) $fatal(1, "FAIL fullchip check before all CPU greetings");
                  run_complete <= 1;
                  $display("SOC_FLOW_V1|%0d|run|cpu0|firmware_run|pass", $time);
                  $display("SOC_FLOW_V1|%0d|check|cpu0|firmware_check|start", $time);
                  $display("PHASE run complete: all CPUs greeted");
                end else $fatal(1, "FAIL fullchip unsupported phase");
                phase <= value;
              end
              for (core=0; core<N; core=core+1) begin
                if (off==4+16*core && value==1) begin init_mask[core] <= 1;
                  if (core==0) $display("SOC_FLOW_V1|%0d|init|cpu0|firmware_init|start", $time);
                end
                if (off==8+16*core && value!=0) begin
                  if (phase!=2 || value!=32'h550+core) $fatal(1, "FAIL fullchip wrong-phase CPU greeting");
                  hello_mask[core] <= 1;
                  $display("hello world from CPU%0d (firmware mailbox)", core);
                end
                if (off==12+16*core && value==1) begin
                  if (phase!=3) $fatal(1, "FAIL fullchip check acknowledgement out of phase");
                  check_mask[core] <= 1;
                end
              end
              if (off==DONE_OFFSET && value==32'h600d) begin
                if (&check_mask !== 1'b1 || &app_fetch !== 1'b1 || !copied_all || rom_reads==0 || flash_reads==0)
                  $fatal(1, "FAIL fullchip incomplete CPU execution/coordination");
                if (!cpu_dma_success) $fatal(1, "FAIL fullchip CPU C hook evidence missing");
                check_complete <= 1;
                pass_flag <= 1;
                $display("SOC_FLOW_V1|%0d|check|cpu0|firmware_check|pass", $time);
                $display("PHASE check complete: coordinator observed all peer checks");
                $display("PASS fullchip: %0d real CPUs, shared NoCs, cold boot, init/run/check", N);
`ifndef COCOTB_SIM
                $finish;
`endif
              end
            end
          end
        end
      end
    end
    previous_release <= released;
    if (init_mask[0] && !pass_flag) begin
      if (phase != previous_phase) stalled <= 0; else stalled <= stalled + 1;
      previous_phase <= phase;
      if (stalled > 2300000) begin
        if (!init_complete) $fatal(1, "FAIL fullchip missing init acknowledgement mask=%h", init_mask);
        else $fatal(1, "FAIL fullchip coordination phase timeout phase=%0d", phase);
      end
    end
  end
endmodule
