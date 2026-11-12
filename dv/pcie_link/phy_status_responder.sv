`timescale 1ns/1ps
// Gen1 x1 *behavioral* PIPE receiver-detect/status responder for simulation.
// Never drives or overrides endpoint LTSSM state, link_up, or training symbols.
// Receiver presence is a separate TB-owned condition representing termination
// on the remote lane, not a link-trained flag. This is not synthesizable PHY IP.
module pcie_phy_status_responder #(
  parameter integer RESPONSE_CYCLES = 4
) (
  input  logic       clk,
  input  logic       reset_n,
  input  logic       receiver_detect,
  input  logic       remote_termination_present,
  output logic       phy_phystatus,
  output logic [2:0] phy_rxstatus
);
  localparam integer COUNT_WIDTH = $clog2(RESPONSE_CYCLES + 1);
  logic request_seen;
  logic pending;
  logic [COUNT_WIDTH-1:0] remaining;

  initial begin
    if (RESPONSE_CYCLES < 1)
      $fatal(1, "PHY response cycles must be at least one");
  end

  always_ff @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
      request_seen <= 1'b0;
      pending <= 1'b0;
      remaining <= '0;
      phy_phystatus <= 1'b0;
      phy_rxstatus <= 3'b000;
    end else begin
      // PIPE RxStatus 011 (receiver present) is only meaningful on PhyStatus.
      phy_phystatus <= 1'b0;
      phy_rxstatus <= 3'b000;
      if (!receiver_detect) begin
        request_seen <= 1'b0;
        pending <= 1'b0;
        remaining <= '0;
      end else if (!request_seen) begin
        request_seen <= 1'b1;
        // A disconnected or disabled remote device must never train by a timer.
        if (remote_termination_present) begin
          pending <= 1'b1;
          remaining <= RESPONSE_CYCLES - 1;
        end
      end else if (pending) begin
        if (remaining == 0) begin
          pending <= 1'b0;
          phy_phystatus <= 1'b1;
          phy_rxstatus <= 3'b011;
        end else begin
          remaining <= remaining - 1'b1;
        end
      end
    end
  end
endmodule
