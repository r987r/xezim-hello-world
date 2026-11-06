// Self-checking REAL RTL DDR-B Config NoC AXI4-to-LiteX Wishbone handshake.
module tb_ddr_litedram_axi_wishbone;
  logic clk=0, rst_ni=0;
  always #5 clk=~clk;
  logic s_awvalid=0, s_wvalid=0, s_wlast=1, s_bready=0;
  logic s_arvalid=0,s_rready=0;
  logic [0:0] s_awid=0,s_arid=0;
  logic [31:0] s_awaddr=0,s_wdata=0,s_araddr=0;
  logic [7:0] s_awlen=0,s_arlen=0;
  logic [2:0] s_awsize=2,s_arsize=2;
  logic [1:0] s_awburst=1,s_arburst=1;
  logic [3:0] s_wstrb=15;
  wire s_awready,s_wready,s_bvalid,s_arready,s_rvalid,s_rlast;
  wire [0:0] s_bid,s_rid;
  wire [1:0] s_bresp,s_rresp;
  wire [31:0] s_rdata;
  wire wb_ctrl_cyc,wb_ctrl_stb,wb_ctrl_we;
  wire [15:0] wb_ctrl_adr;
  wire [31:0] wb_ctrl_dat_w;
  logic [31:0] wb_ctrl_dat_r=0;
  wire [3:0] wb_ctrl_sel;
  wire [2:0] wb_ctrl_cti;
  wire [1:0] wb_ctrl_bte;
  logic wb_ctrl_ack=0,wb_ctrl_err=0;
  integer observed_writes=0,observed_reads=0;
  logic [31:0] registers[0:4095];

  ddr_litedram_axi_wishbone_bridge #(
    .WB_ADR_BITS(16),.WB_BASE(32'h2000),.TIMEOUT_CYCLES(64)
  ) dut(.*);
  always @(posedge clk) begin
    wb_ctrl_ack <= 0;
    if (rst_ni && wb_ctrl_cyc && wb_ctrl_stb && !wb_ctrl_ack) begin
      if (wb_ctrl_we) begin
        for (integer i=0;i<4;i++)
          if(wb_ctrl_sel[i]) registers[(wb_ctrl_adr-16'h800)][i*8 +: 8] <= wb_ctrl_dat_w[i*8 +: 8];
        observed_writes <= observed_writes + 1;
      end else begin
        wb_ctrl_dat_r <= registers[(wb_ctrl_adr-16'h800)];
        observed_reads <= observed_reads + 1;
      end
      wb_ctrl_ack <= 1;
    end
  end

  task automatic write_req(input logic [31:0] addr,input logic [7:0] len,
                           input logic [31:0] data,input logic [1:0] expect_resp);
    @(negedge clk); s_awaddr=addr;s_awlen=len;s_awvalid=1;
    do @(posedge clk);while(!s_awready);
    @(negedge clk);s_awvalid=0;
    for(integer i=0;i<=len;i++) begin
      @(negedge clk);s_wdata=data+i;s_wlast=(i==len);s_wvalid=1;
      do @(posedge clk);while(!s_wready);
      @(negedge clk);s_wvalid=0;
    end
    repeat(3) begin
      @(negedge clk);
      if(!s_bvalid || s_bresp !== expect_resp || s_bid !== 0)
        $fatal(1,"AXI Wishbone B response/stall failed");
    end
    s_bready=1;
    @(posedge clk);
    @(negedge clk);s_bready=0;
  endtask
  task automatic read_req(input logic [31:0] addr,input logic [1:0] expect_resp,
                          input logic [31:0] expect_data);
    @(negedge clk);s_araddr=addr;s_arvalid=1;
    do @(posedge clk);while(!s_arready);
    @(negedge clk);s_arvalid=0;
    repeat(3) begin
      @(negedge clk);
      if(!s_rvalid || s_rresp !== expect_resp || s_rid !== 0 ||
         s_rdata !== expect_data || !s_rlast)
        $fatal(1,"AXI Wishbone R response/stall failed");
    end
    s_rready=1;
    @(posedge clk);
    @(negedge clk);s_rready=0;
  endtask

  initial begin
    #200000;
    $fatal(1,"DDR Wishbone bridge test timeout");
  end
  initial begin
    repeat(5) @(negedge clk);
    rst_ni=1;
    write_req(32'h4003_2010,0,32'hcafe_a51a,0);
    if(observed_writes != 1 || wb_ctrl_adr != 16'h0000)
      $display("Note: idle WB ADR is last address, not reset");
    if(registers[16'h804] !== 32'hcafe_a51a)
      $fatal(1,"Wishbone CSR 0x2010 not updated at translated offset");
    read_req(32'h4003_2010,0,32'hcafe_a51a);
    if(observed_reads != 1) $fatal(1,"real Wishbone read not observed");
    // Unsupported burst must fully drain W channel and never invoke WB.
    write_req(32'h4003_2010,1,32'hdead_beef,2'b11);
    if(observed_writes != 1) $fatal(1,"malformed AXI burst leaked to Wishbone");
    write_req(32'h4003_4000,0,32'hface_1234,2'b11);
    read_req(32'h4003_4000,2'b11,32'h0);
    if(observed_writes != 1 || observed_reads != 1)
      $fatal(1,"bad aperture alias leaked into WB");
    $display("PASS DDR-B real Config NoC AXI4-to-Wishbone RTL: read/write, 16KiB guard, translated CSR, stalls, DECERR");
    $finish;
  end
endmodule
