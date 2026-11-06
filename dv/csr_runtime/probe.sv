// Test-only real elaborated hierarchy proof. This is NOT a SoC CSR device.
// The full SoC's PeakRDL reset RTL and Config NoC are separately tested in #86.
module csr_runtime_probe (
  input logic clk, rst_n, enable,
  output logic [31:0] observed
);
  logic [31:0] state_q;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) state_q <= 32'h00000000;
    else if (enable) state_q <= state_q + 32'd2;
  end
  assign observed = state_q;
endmodule

module csr_runtime_tb (
  input logic clk, rst_n, enable,
  output logic [31:0] observed
);
  csr_runtime_probe u_probe(
    .clk(clk), .rst_n(rst_n), .enable(enable), .observed(observed)
  );
endmodule
