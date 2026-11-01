`timescale 1ns/1ps
// Small dependency-free simulator smoke test, used when publishing a new Xezim binary.
module hello_world_tb;
  logic [7:0] a, b;
  wire [8:0] sum = {1'b0, a} + {1'b0, b};
  initial begin
    a = 8'd20;
    b = 8'd22;
    #1;
    if (sum !== 9'd42) $fatal(1, "FAIL: smoke expected 42");
    a = 8'd255;
    b = 8'd1;
    #1;
    if (sum !== 9'd256) $fatal(1, "FAIL: smoke expected 256");
    $display("PASS: hello_world_tb");
    $finish;
  end
endmodule
