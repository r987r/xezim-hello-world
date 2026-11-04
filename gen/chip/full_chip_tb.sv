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
  input logic probe_rready
);
  localparam integer N = 2, MAX_WORDS = 53;
  localparam [N*32-1:0] BASES = {32'h11000000, 32'h10000000};
  localparam [N*32-1:0] WORDS = {32'd21, 32'd53};
  localparam [31:0] MAILBOX = 32'h10000400;
  localparam integer DONE_OFFSET = 36;
  reg clk = 0, rst_n = 0;
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
`ifdef COCOTB_SIM
  localparam bit ProbeEnable = 1;
`else
  localparam bit ProbeEnable = 0;
`endif
  soc_top #(.ProbeEnable(ProbeEnable)) dut (.clk_i(clk), .rst_ni(rst_n), .hold_mask_i(hold_mask),
    .released_o(released), .fetch_valid_o(fetch_valid), .fetch_addr_o(fetch_addr),
    .sram_valid_o(sram_valid), .sram_write_o(sram_write), .sram_addr_o(sram_addr),
    .sram_data_o(sram_data), .sram_strb_o(sram_strb), .rom_reads_o(rom_reads), .flash_reads_o(flash_reads),
    .dma_irq_o(), .dma_irq_pending_o(),
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
    .cfgprobe_awid('0),
    .cfgprobe_awaddr('0),
    .cfgprobe_awlen('0),
    .cfgprobe_awsize('0),
    .cfgprobe_awburst('0),
    .cfgprobe_awlock('0),
    .cfgprobe_awcache('0),
    .cfgprobe_awprot('0),
    .cfgprobe_awqos('0),
    .cfgprobe_awregion('0),
    .cfgprobe_awvalid('0),
    .cfgprobe_awready(),
    .cfgprobe_wdata('0),
    .cfgprobe_wstrb('0),
    .cfgprobe_wlast('0),
    .cfgprobe_wvalid('0),
    .cfgprobe_wready(),
    .cfgprobe_bid(),
    .cfgprobe_bresp(),
    .cfgprobe_bvalid(),
    .cfgprobe_bready('0),
    .cfgprobe_arid('0),
    .cfgprobe_araddr('0),
    .cfgprobe_arlen('0),
    .cfgprobe_arsize('0),
    .cfgprobe_arburst('0),
    .cfgprobe_arlock('0),
    .cfgprobe_arcache('0),
    .cfgprobe_arprot('0),
    .cfgprobe_arqos('0),
    .cfgprobe_arregion('0),
    .cfgprobe_arvalid('0),
    .cfgprobe_arready(),
    .cfgprobe_rid(),
    .cfgprobe_rdata(),
    .cfgprobe_rresp(),
    .cfgprobe_rlast(),
    .cfgprobe_rvalid(),
    .cfgprobe_rready('0));
  reg [31:0] expected [0:N*MAX_WORDS-1];
  reg [MAX_WORDS-1:0] copied [0:N-1];
  reg [N-1:0] init_mask = 0, hello_mask = 0, check_mask = 0, app_fetch = 0;
  reg init_complete = 0, run_complete = 0, check_complete = 0, pass_flag = 0;
  reg [N-1:0] previous_release = 0;
  integer phase = 0, previous_phase = 0, cycles = 0, stalled = 0;
  integer i, lane, index, core, off;
  reg [31:0] address, value;
  reg copied_all;
  initial begin
    $readmemh("gen/chip/compute0.hex", expected, 0*MAX_WORDS, 0*MAX_WORDS+52);
    copied[0] = '0;
    $readmemh("gen/chip/compute1.hex", expected, 1*MAX_WORDS, 1*MAX_WORDS+20);
    copied[1] = '0;
  end
  always @(posedge clk) if (rst_n) begin
    cycles <= cycles + 1;
    if (cycles > 80000) $fatal(1, "FAIL fullchip overall boot timeout");
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
            if (i==0 && address >= MAILBOX && address <= MAILBOX + DONE_OFFSET) begin
              off = address - MAILBOX;
              if (off==0 && value!=0) begin
                if (value==2) begin
                  if (&init_mask !== 1'b1) $fatal(1, "FAIL fullchip run before all CPUs initialized");
                  init_complete <= 1;
                  $display("PHASE init complete: all CPUs ready");
                end else if (value==3) begin
                  if (&hello_mask !== 1'b1) $fatal(1, "FAIL fullchip check before all CPU greetings");
                  run_complete <= 1;
                  $display("PHASE run complete: all CPUs greeted");
                end else $fatal(1, "FAIL fullchip unsupported phase");
                phase <= value;
              end
              for (core=0; core<N; core=core+1) begin
                if (off==4+16*core && value==1) init_mask[core] <= 1;
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
                check_complete <= 1;
                pass_flag <= 1;
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
      if (stalled > 6000) begin
        if (!init_complete) $fatal(1, "FAIL fullchip missing init acknowledgement mask=%h", init_mask);
        else $fatal(1, "FAIL fullchip coordination phase timeout phase=%0d", phase);
      end
    end
  end
endmodule
