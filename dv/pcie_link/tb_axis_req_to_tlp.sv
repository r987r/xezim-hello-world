`timescale 1ns/1ps
module tb_axis_req_to_tlp;
  logic clk=0, rst=1;
  always #5 clk=~clk;
  logic [31:0] s_data=0;
  logic [3:0] s_keep=4'hf;
  logic s_valid=0,s_last=0,s_ready;
  logic [63:0] tlp_data;
  logic [127:0] tlp_hdr;
  logic tlp_valid,tlp_sop,tlp_eop,tlp_ready=0;
  logic [31:0] accepted,emitted;
  openpcie_axis_req_to_tlp dut (
    .clk_i(clk),.rst_i(rst),.s_data_i(s_data),.s_keep_i(s_keep),
    .s_valid_i(s_valid),.s_last_i(s_last),.s_ready_o(s_ready),
    .tlp_data_o(tlp_data),.tlp_hdr_o(tlp_hdr),.tlp_valid_o(tlp_valid),
    .tlp_sop_o(tlp_sop),.tlp_eop_o(tlp_eop),.tlp_ready_i(tlp_ready),
    .accepted_count_o(accepted),.emitted_count_o(emitted)
  );
  task automatic send(input logic [31:0] data,input logic last);
    @(negedge clk);
    s_data=data; s_last=last; s_valid=1;
    while (!s_ready) @(negedge clk);
    @(posedge clk);
    @(negedge clk);
    s_valid=0;
  endtask
  initial begin
    repeat(3) @(negedge clk);
    rst=0;
    send(32'h01000040,0); // wire order MWr, 3DW, len=1
    send(32'h0f060100,0); // requester, tag 6, BE=F
    send(32'h00110080,0); // BAR0 80001100
    send(32'ha5c36e91,1); // real host payload word
    repeat(4) begin
      @(negedge clk);
      if (!tlp_valid || !tlp_sop || !tlp_eop || s_ready ||
          tlp_hdr !==128'h40000001_0001060f_80001100_00000000 ||
          tlp_data !==64'h00000000_a5c36e91)
        $fatal(1,"MWr bridge contract mismatch hdr=%h data=%h valid=%b ready=%b",tlp_hdr,tlp_data,tlp_valid,s_ready);
    end
    tlp_ready=1;
    @(negedge clk);
    tlp_ready=0;
    if (emitted!=1) $fatal(1,"posted write counted incorrectly %d",emitted);
    send(32'h01000000,0); // wire order MRd, 3DW, len=1
    send(32'h0f070100,0);
    send(32'h00110080,1);
    @(negedge clk);
    if (!tlp_valid || s_ready ||
        tlp_hdr !==128'h00000001_0001070f_80001100_00000000 ||
        tlp_data !==0)
      $fatal(1,"MRd bridge contract mismatch hdr=%h data=%h",tlp_hdr,tlp_data);
    tlp_ready=1;
    @(negedge clk);
    if (emitted!=2 || accepted!=7) $fatal(1,"beat accounting failed %d/%d",emitted,accepted);
    $display("PASS: genuine OpenPCIe wire-order MWr/MRd -> verilog-pcie 128b/64b header contract, exactly 7 accepted beats, two requests");
    $finish;
  end
  initial begin
    #10000;
    $fatal(1,"bridge timed out");
  end
endmodule
