`timescale 1ns/1ps

module hello_world_tb;
    logic [7:0] a;
    logic [7:0] b;
    wire  [8:0] sum;

    hello_world dut (
        .a   (a),
        .b   (b),
        .sum (sum)
    );

    initial begin
        $display("Hello, World! Running on Xezim.");
        a = 8'd20;
        b = 8'd22;
        #1;
        if (sum !== 9'd42)
            $fatal(1, "FAIL: 20 + 22 should be 42; got %0d", sum);
        a = 8'd255;
        b = 8'd1;
        #1;
        if (sum !== 9'd256)
            $fatal(1, "FAIL: 255 + 1 should be 256; got %0d", sum);
        a = 'x;
        b = 8'd0;
        #1;
        if (sum !== 'x)
            $fatal(1, "FAIL: unknown operand did not propagate; got %b", sum);
        $display("PASS: hello_world_tb");
        $finish;
    end
endmodule
