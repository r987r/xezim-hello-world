`timescale 1ns/1ps
module tb_pcie_phy_status_responder;
  logic clk = 0;
  always #8 clk = ~clk;  // Gen1 32-bit PIPE: 62.5 MHz parallel clock.
  logic reset_n = 0;
  logic receiver_detect = 0;
  logic remote_termination_present = 0;
  wire phy_phystatus;
  wire [2:0] phy_rxstatus;
  int responses = 0;

  pcie_phy_status_responder #(.RESPONSE_CYCLES(3)) dut (.*);
  always @(posedge clk) begin
    // Ignore the active-low reset interval before nonblocking outputs settle.
    if (reset_n !== 1'b1) begin
      // No observation until out of reset.
    end else if (phy_phystatus) begin
      if (phy_rxstatus !== 3'b011)
        $fatal(1, "PHY receiver-detect response was not 011");
      responses <= responses + 1;
    end else if (phy_rxstatus !== 3'b000) begin
      $fatal(1, "PHY RxStatus was retained outside PhyStatus pulse");
    end
  end

  task automatic tick(input int count);
    repeat (count) @(negedge clk);
  endtask

  initial begin
    tick(2);
    reset_n = 1;
    tick(3);
    if (responses != 0) $fatal(1, "spontaneous receiver-detect response");
    receiver_detect = 1;
    tick(8);
    if (responses != 0) $fatal(1, "absent partner was accepted");
    remote_termination_present = 1;
    tick(8);
    if (responses != 0) $fatal(1, "late partner cannot bypass detect retry");
    receiver_detect = 0;
    tick(2);
    receiver_detect = 1;
    tick(5);
    if (responses != 1) $fatal(1, "real receiver-detect request did not complete");
    tick(8);
    if (responses != 1) $fatal(1, "responder issued duplicate completion");
    remote_termination_present = 0;
    receiver_detect = 0;
    tick(2);
    receiver_detect = 1;
    tick(8);
    if (responses != 1) $fatal(1, "receiver removal was ignored");
    reset_n = 0;
    receiver_detect = 0;
    tick(2);
    if (phy_phystatus || phy_rxstatus != 0) $fatal(1, "reset failed to clear PHY status");
    $display("PASS: Gen1 receiver-detect request/response, absence, retry, reset");
    $finish;
  end
endmodule
