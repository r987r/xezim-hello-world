// Xezim 0.11.3 known bug reproducer (NOT a passing simulator test).
// IEEE SystemVerilog indexed port [31:2] must preserve bit labels [6:2].
// Icarus Verilog 12.0 passes; Xezim 0.11.3 fails the direct part-select.
// Run with: xezim -s port_slice_repro dv/simulator/port_slice_repro.sv
// And: iverilog -g2012 -s port_slice_repro -o /tmp/repro.vvp ... && vvp ...
module port_slice_decode(input wire [31:2] instruction, output wire [4:0] opcode);
    assign opcode = instruction[6:2];
endmodule
module port_slice_repro;
    reg [31:0] instruction = 32'h110002b7; // LUI x5,0x11000
    wire [31:2] named_slice = instruction[31:2];
    wire [4:0] direct_opcode, named_opcode;
    port_slice_decode u_direct(.instruction(instruction[31:2]), .opcode(direct_opcode));
    port_slice_decode u_named(.instruction(named_slice), .opcode(named_opcode));
    initial begin
        #1;
        $display("PORT SLICE direct=%b named=%b expected=01101", direct_opcode, named_opcode);
        if (direct_opcode !== 5'b01101 || named_opcode !== 5'b01101)
            $fatal(1, "port part-select mapping regression");
        $finish;
    end
endmodule
