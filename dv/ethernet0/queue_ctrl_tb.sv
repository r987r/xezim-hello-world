
module ethernet_queue_ctrl_tb;
  reg clk=0,rst=1;
  always #5 clk=~clk;
  reg cfg_valid=0,cfg_write=0;
  reg [7:0] cfg_addr=0;
  reg [31:0] cfg_wdata=0;
  reg [3:0] cfg_wstrb=4'hf;
  wire cfg_ready,cfg_error;
  wire [31:0] cfg_rdata;
  reg rx_meta_valid=0,rx_is_udp=0;
  reg [15:0] rx_ethertype=0,rx_udp_dst_port=0;
  wire rx_meta_ready,rx_route_valid,rx_route_drop;
  wire rx_route_queue;
  wire [7:0] rx_route_policy;
  wire rx_desc_valid,tx_desc_valid;
  reg rx_desc_ready=0,tx_desc_ready=0;
  wire [63:0] rx_desc_addr,tx_desc_addr;
  wire rx_desc_queue,tx_desc_queue;
  reg rx_cpl_written=0,tx_cpl_written=0;
  wire irq;
  integer checks=0;
  ethernet_queue_ctrl dut(
    .clk,.rst,.cfg_valid,.cfg_write,.cfg_addr,.cfg_wdata,.cfg_wstrb,
    .cfg_ready,.cfg_rdata,.cfg_error,.rx_meta_valid,.rx_meta_ready,
    .rx_ethertype,.rx_is_udp,.rx_udp_dst_port,
    .rx_route_valid,.rx_route_drop,.rx_route_queue,.rx_route_policy,
    .rx_desc_valid,.rx_desc_ready,.rx_desc_addr,.rx_desc_queue,
    .tx_desc_valid,.tx_desc_ready,.tx_desc_addr,.tx_desc_queue,
    .rx_cpl_written,.tx_cpl_written,.irq
  );
  task check(input logic ok,input string why);
    begin
      if (ok !== 1'b1) begin
        $display("FAIL ethq %s at %0t",why,$time);
        $fatal(1);
      end
      checks=checks+1;
    end
  endtask
  task wr(input [7:0] addr,input [31:0] value,input logic expect_err);
    begin
      @(negedge clk);cfg_addr=addr;cfg_wdata=value;
      cfg_write=1;cfg_valid=1;
      #1;check(cfg_error==expect_err,"write response");
      @(posedge clk);#1;
      @(negedge clk);cfg_valid=0;cfg_write=0;
    end
  endtask
  task rd(input [7:0] addr,input [31:0] expected);
    begin
      @(negedge clk);cfg_addr=addr;cfg_valid=1;cfg_write=0;
      #1;
      if (cfg_error || cfg_rdata !== expected) begin
        $display("FAIL read offset=%h expected=%h actual=%h error=%b",
                 addr,expected,cfg_rdata,cfg_error);
        $fatal(1);
      end
      checks=checks+1;
      @(negedge clk);cfg_valid=0;
    end
  endtask
  task receive(input [15:0] et,input logic udp,
               input [15:0] port,input logic drop);
    begin
      @(negedge clk);check(rx_meta_ready,"metadata ready");
      rx_meta_valid=1;rx_ethertype=et;rx_is_udp=udp;rx_udp_dst_port=port;
      @(posedge clk);#1;
      check(rx_route_valid && rx_route_drop==drop,"route decision");
      check(rx_desc_valid == !drop,"no descriptor for dropped frame");
      @(negedge clk);rx_meta_valid=0;
    end
  endtask
  task consume(input [63:0] address);
    begin
      check(rx_desc_addr == address,"RX descriptor address");
      @(negedge clk);rx_desc_ready=1;
      @(posedge clk);#1;
      check(!rx_desc_valid,"RX fetched once");
      @(negedge clk);rx_desc_ready=0;rx_cpl_written=1;
      @(posedge clk);#1;check(irq,"RX completion");
      @(negedge clk);rx_cpl_written=0;
    end
  endtask
  initial begin #2000000;$fatal(1,"watchdog");end
  initial begin
    repeat(4) @(posedge clk);
    @(negedge clk);rst=0;
    rd(8'h00,32'h45544851);rd(8'h04,32'h00010000);
    rd(8'h0c,32'h04040101);
    wr(8'h20,32'h4000,0);wr(8'h24,1,0);
    wr(8'h30,32'h5000,0);wr(8'h34,1,0);
    wr(8'h40,32'h6000,0);wr(8'h44,1,0);
    wr(8'h50,32'h7000,0);wr(8'h54,1,0);
    wr(8'h74,32'h0800,0);wr(8'h78,32'hffff,0);
    wr(8'h7c,6000,0);wr(8'h80,32'hffff,0);wr(8'h84,3,0);
    wr(8'h28,2,0);wr(8'h48,1,0);wr(8'h08,3,0);
    receive(16'h0800,1,6000,0);consume(64'h100004000);
    rd(8'h2c,1);rd(8'h38,1);
    check(tx_desc_valid,"TX descriptor valid");
    check(tx_desc_addr==64'h100006000,"TX descriptor address");
    @(negedge clk);tx_desc_ready=1;
    @(posedge clk);#1;check(!tx_desc_valid,"TX request once");
    @(negedge clk);tx_desc_ready=0;tx_cpl_written=1;
    @(posedge clk);#1;
    @(negedge clk);tx_cpl_written=0;
    rd(8'h4c,1);rd(8'h58,1);
    receive(16'h0800,1,6000,0);consume(64'h100004020);
    rd(8'h2c,2);rd(8'h38,2);
    receive(16'h0800,1,6000,1);
    rd(8'h94,2);rd(8'h98,1);
    receive(16'h0806,0,0,1);
    rd(8'h94,32'h12);rd(8'h98,2);
    wr(8'h74,16'h0806,1);rd(8'h94,32'h16);
    // Recycle completion slots and roll the RX descriptor pointer through
    // one full 16-entry wrap. No buffer may be reused before software reposts.
    wr(8'h3c,2,0);
    for (integer idx=2; idx<18; idx=idx+1) begin
      wr(8'h28,idx+1,0);
      receive(16'h0800,1,6000,0);
      consume(64'h100004000 + ((idx & 15) * 32));
    end
    rd(8'h2c,18);rd(8'h38,18);
    // CQ now full with 16 unread entries, despite a preposted new buffer.
    wr(8'h28,19,0);
    receive(16'h0800,1,6000,1);
    rd(8'h94,32'h36);
    rd(8'h98,3);
    wr(8'h3c,18,0);
    wr(8'h94,32'h20,0);
    rd(8'h94,32'h16);
    wr(8'h08,0,0);
    wr(8'h70,1,0);wr(8'h74,16'h0800,0);wr(8'h78,16'hffff,0);
    wr(8'h7c,6000,0);wr(8'h80,16'hffff,0);wr(8'h84,3,0);
    wr(8'h08,1,0);
    receive(16'h0800,1,6000,1);
    rd(8'h9c,1);rd(8'h98,4);rd(8'h94,32'h17);
    wr(8'h08,0,0);wr(8'h70,1,0);
    wr(8'h84,32'h103,1);rd(8'h94,32'h17);
    @(negedge clk);rx_cpl_written=1;
    @(posedge clk);#1;
    @(negedge clk);rx_cpl_written=0;
    rd(8'h94,32'h1f);
    $display("PASS ethernet_queue_ctrl_tb checks=%0d",checks);$finish;
  end
endmodule
