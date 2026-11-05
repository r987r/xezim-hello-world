// Standalone actual RTL handshake test for the DDR-B adapter. The pinned
// standalone LiteDRAM functional/DFI test runs in the same CI workflow.
// This test is *not* a claim of the full SoC NoC integration.
module tb_ddr_litedram_axi_bridge;
  logic clk=0, rst_ni=0, controller_ready=0;
  always #5 clk=~clk;
  logic [3:0] s_awid=0, s_arid=0;
  logic [63:0] s_awaddr=0, s_araddr=0, s_wdata=0;
  logic [7:0] s_awlen=0, s_arlen=0, s_wstrb=0;
  logic [2:0] s_awsize=3, s_arsize=3;
  logic [1:0] s_awburst=1, s_arburst=1;
  logic [5:0] s_awatop=0;
  logic s_awvalid=0, s_wvalid=0, s_wlast=0, s_bready=0;
  logic s_arvalid=0, s_rready=0;
  wire s_awready,s_wready,s_bvalid,s_arready,s_rvalid,s_rlast;
  wire [3:0] s_bid,s_rid;
  wire [1:0] s_bresp,s_rresp;
  wire [63:0] s_rdata;
  wire [3:0] m_awid,m_arid;
  wire [24:0] m_awaddr,m_araddr;
  wire [7:0] m_awlen,m_arlen;
  wire [2:0] m_awsize,m_arsize;
  wire [1:0] m_awburst,m_arburst;
  wire m_awvalid,m_wvalid,m_wlast,m_bready,m_arvalid,m_rready;
  wire [63:0] m_wdata;
  wire [7:0] m_wstrb;
  logic m_awready=0,m_wready=0,m_bvalid=0,m_arready=0,m_rvalid=0,m_rlast=0;
  logic [3:0] m_bid=0,m_rid=0;
  logic [1:0] m_bresp=0,m_rresp=0;
  logic [63:0] m_rdata=0;

  localparam logic [63:0] BASE=64'h0000_0001_4000_0000;
  ddr_litedram_axi_bridge dut (
    .clk_i(clk), .rst_ni(rst_ni), .controller_ready_i(controller_ready),
    .s_awid(s_awid),.s_awaddr(s_awaddr),.s_awlen(s_awlen),
    .s_awsize(s_awsize),.s_awburst(s_awburst),.s_awatop(s_awatop),
    .s_awvalid(s_awvalid),.s_awready(s_awready),
    .s_wdata(s_wdata),.s_wstrb(s_wstrb),.s_wlast(s_wlast),
    .s_wvalid(s_wvalid),.s_wready(s_wready),
    .s_bid(s_bid),.s_bresp(s_bresp),.s_bvalid(s_bvalid),.s_bready(s_bready),
    .s_arid(s_arid),.s_araddr(s_araddr),.s_arlen(s_arlen),
    .s_arsize(s_arsize),.s_arburst(s_arburst),.s_arvalid(s_arvalid),
    .s_arready(s_arready),.s_rid(s_rid),.s_rdata(s_rdata),
    .s_rresp(s_rresp),.s_rlast(s_rlast),.s_rvalid(s_rvalid),.s_rready(s_rready),
    .m_awid(m_awid),.m_awaddr(m_awaddr),.m_awlen(m_awlen),
    .m_awsize(m_awsize),.m_awburst(m_awburst),
    .m_awvalid(m_awvalid),.m_awready(m_awready),
    .m_wdata(m_wdata),.m_wstrb(m_wstrb),.m_wlast(m_wlast),
    .m_wvalid(m_wvalid),.m_wready(m_wready),
    .m_bid(m_bid),.m_bresp(m_bresp),.m_bvalid(m_bvalid),.m_bready(m_bready),
    .m_arid(m_arid),.m_araddr(m_araddr),.m_arlen(m_arlen),
    .m_arsize(m_arsize),.m_arburst(m_arburst),
    .m_arvalid(m_arvalid),.m_arready(m_arready),
    .m_rid(m_rid),.m_rdata(m_rdata),.m_rresp(m_rresp),
    .m_rlast(m_rlast),.m_rvalid(m_rvalid),.m_rready(m_rready)
  );

  task automatic aw(input logic [63:0] addr, input logic [7:0] len,
                    input logic [3:0] id);
    @(negedge clk);
    s_awaddr=addr;s_awlen=len;s_awid=id;s_awvalid=1;
    do @(posedge clk); while (!s_awready);
    @(negedge clk);s_awvalid=0;
  endtask
  task automatic wd(input bit last, input logic [63:0] data);
    @(negedge clk);
    s_wdata=data;s_wstrb=8'hff;s_wlast=last;s_wvalid=1;
    do @(posedge clk); while (!s_wready);
    @(negedge clk);s_wvalid=0;
  endtask
  task automatic ar(input logic [63:0] addr, input logic [7:0] len,
                    input logic [3:0] id);
    @(negedge clk);
    s_araddr=addr;s_arlen=len;s_arid=id;s_arvalid=1;
    do @(posedge clk); while (!s_arready);
    @(negedge clk);s_arvalid=0;
  endtask

  initial begin
    #200000;
    $fatal(1,"DDR bridge RTL test timed out");
  end
  initial begin
    repeat(4) @(negedge clk);
    rst_ni=1;
    @(negedge clk);
    if(s_awready || s_arready) $fatal(1,"controller init gate bypassed");
    controller_ready=1;

    // Negative write: two W beats must be consumed, no forwarded AW/W,
    // B channel DECERR must remain stable under backpressure, original ID.
    aw(BASE+64'h02000000,8'd1,4'd13);
    if(m_awvalid) $fatal(1,"invalid DDR AW forwarded");
    wd(0,64'h1111);
    wd(1,64'h2222);
    if(!s_bvalid || s_bresp!==2'b11 || s_bid!==4'd13 || m_bready)
      $fatal(1,"bad DDR write did not produce stable DECERR");
    repeat(3) begin
      @(negedge clk);
      if(!s_bvalid || s_bid!==4'd13 || s_bresp!==2'b11)
        $fatal(1,"bad write response lost while stalled");
    end
    s_bready=1;
    @(posedge clk);
    @(negedge clk);s_bready=0;

    // Positive write: no physical-address high-bit truncation, real AW/W
    // forwarding, preserving data/strobe/ID and downstream B response.
    m_awready=0;
    aw(BASE+64'h2000,8'd0,4'd14);
    if(!m_awvalid || m_awaddr!==25'h2000 || m_awid!==4'd14)
      $fatal(1,"valid DDR AW not translated/preserved");
    @(negedge clk);m_awready=1;m_wready=1;
    @(posedge clk);
    @(negedge clk);m_awready=0;
    s_wdata=64'hf00dcafe12345678;s_wstrb=8'h55;s_wlast=1;s_wvalid=1;
    #1;
    if(!m_wvalid || !s_wready || m_wdata!==s_wdata ||
       m_wstrb!==8'h55 || !m_wlast)
      $fatal(1,"DDR W beat/strobe not forwarded correctly");
    @(posedge clk);
    @(negedge clk);s_wvalid=0;m_wready=0;
    m_bid=14;m_bresp=0;m_bvalid=1;
    #1;
    if(!s_bvalid || s_bid!==4'd14 || s_bresp!==0)
      $fatal(1,"DDR B not returned from actual downstream controller");
    s_bready=1;
    @(posedge clk);
    @(negedge clk);s_bready=0;m_bvalid=0;

    // Negative read: RRESP DECERR with precisely two accepted R beats,
    // correct RLAST and RID; no AR sent to the controller.
    ar(BASE+64'h02000000,8'd1,4'd11);
    if(m_arvalid) $fatal(1,"out of aperture read forwarded");
    #1;
    if(!s_rvalid || s_rresp!==2'b11 || s_rlast || s_rid!==4'd11)
      $fatal(1,"first error R beat invalid");
    repeat(2) begin
      @(negedge clk);
      if(!s_rvalid || s_rlast) $fatal(1,"stalled error R lost");
    end
    s_rready=1;
    @(posedge clk);
    @(negedge clk);
    #1;
    if(!s_rvalid || !s_rlast || s_rid!==4'd11 || s_rresp!==2'b11)
      $fatal(1,"second error R beat must assert RLAST");
    @(posedge clk);
    @(negedge clk);s_rready=0;

    // Positive read: receive a real response from the local controller.
    m_arready=0;
    ar(BASE+64'h3000,8'd0,4'd7);
    if(!m_arvalid || m_araddr!==25'h3000 || m_arid!==4'd7)
      $fatal(1,"valid DDR AR not translated/preserved");
    @(negedge clk);m_arready=1;
    @(posedge clk);
    @(negedge clk);m_arready=0;
    m_rid=7;m_rdata=64'h1234abcdef987654;m_rresp=0;m_rlast=1;m_rvalid=1;
    #1;
    if(!s_rvalid || !s_rlast || s_rid!==4'd7 ||
       s_rdata!==64'h1234abcdef987654 || s_rresp!==0)
      $fatal(1,"local controller R response not preserved");
    s_rready=1;
    @(posedge clk);
    @(negedge clk);s_rready=0;m_rvalid=0;

    $display("PASS DDR-B actual RTL bridge: DECERR AW/W/B/AR/R, backpressure, real forwarding, 25-bit translation, preserved IDs and data");
    $finish;
  end
endmodule
