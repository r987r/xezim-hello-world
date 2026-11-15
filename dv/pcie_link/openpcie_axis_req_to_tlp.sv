// Source-owned verification-only wire-format shim. OpenPCIe exposes 32-bit
// PCIe wire-order DWORDs; verilog-pcie bridge accepts a 128-bit canonical
// TLP header plus 64-bit payload. This intentionally supports ONLY 3DW,
// one-DW Memory Read/Write requests; all other packets fail closed.
module openpcie_axis_req_to_tlp (
  input logic clk_i, rst_i,
  input logic [31:0] s_data_i,
  input logic [3:0] s_keep_i,
  input logic s_valid_i, s_last_i,
  output logic s_ready_o,
  output logic [63:0] tlp_data_o,
  output logic [127:0] tlp_hdr_o,
  output logic tlp_valid_o, tlp_sop_o, tlp_eop_o,
  input logic tlp_ready_i,
  output logic [31:0] accepted_count_o,
  output logic [31:0] emitted_count_o
);
  typedef enum logic [2:0] {DW0,DW1,DW2,DATA,EMIT} state_t;
  state_t state_r;
  logic [31:0] header0_r, header1_r, header2_r, payload_r;
  logic is_write_r;
  function automatic [31:0] wire_to_canonical(input logic [31:0] x);
    wire_to_canonical = {x[7:0],x[15:8],x[23:16],x[31:24]};
  endfunction
  assign s_ready_o = state_r != EMIT;
  assign tlp_valid_o = state_r == EMIT;
  assign tlp_sop_o = tlp_valid_o;
  assign tlp_eop_o = tlp_valid_o;
  assign tlp_hdr_o = {header0_r, header1_r, header2_r, 32'b0};
  assign tlp_data_o = {32'b0, payload_r};
  always_ff @(posedge clk_i) begin
    if (rst_i) begin
      state_r <= DW0;
      header0_r <= '0;
      header1_r <= '0;
      header2_r <= '0;
      payload_r <= '0;
      is_write_r <= 0;
      accepted_count_o <= 0;
      emitted_count_o <= 0;
    end else begin
      if (s_valid_i && s_ready_o) begin
        if (s_keep_i != 4'hf) $fatal(1, "PCIe request has partial DWORD keep");
        case (state_r)
          DW0: begin
            // Invert OpenPCIe's byte presentation before decoding PCIe Fmt/Type.
            if (wire_to_canonical(s_data_i)[28:24] != 5'h00 ||
                wire_to_canonical(s_data_i)[29] != 1'b0 ||
                wire_to_canonical(s_data_i)[30] && wire_to_canonical(s_data_i)[31])
              $fatal(1, "unsupported non-Memory/4DW TLP request");
            if (wire_to_canonical(s_data_i)[9:0] != 10'd1)
              $fatal(1, "only one-DW memory requests supported");
            if (s_last_i) $fatal(1,"truncated TLP DW0");
            header0_r <= wire_to_canonical(s_data_i);
            is_write_r <= wire_to_canonical(s_data_i)[30];
            state_r <= DW1;
          end
          DW1: begin
            if (s_last_i) $fatal(1,"truncated TLP DW1");
            header1_r <= wire_to_canonical(s_data_i);
            state_r <= DW2;
          end
          DW2: begin
            header2_r <= wire_to_canonical(s_data_i);
            if (!is_write_r) begin
              if (!s_last_i) $fatal(1,"memory read unexpectedly carries data");
              payload_r <= '0;
              state_r <= EMIT;
            end else begin
              if (s_last_i) $fatal(1,"memory write missing payload");
              state_r <= DATA;
            end
          end
          DATA: begin
            if (!s_last_i) $fatal(1,"one-DW write missing EOP");
            payload_r <= s_data_i;
            state_r <= EMIT;
          end
          default: $fatal(1,"accepted AXIS beat while request pending");
        endcase
        accepted_count_o <= accepted_count_o + 1;
      end
      if (tlp_valid_o && tlp_ready_i) begin
        emitted_count_o <= emitted_count_o + 1;
        state_r <= DW0;
      end
    end
  end
endmodule
