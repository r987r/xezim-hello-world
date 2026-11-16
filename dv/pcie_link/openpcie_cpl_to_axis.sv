// Source-owned verification shim: real verilog-pcie completion -> original
// OpenPCIe 32b wire-order AXIS. One 3DW, one-DW CplD at a time; fail closed
// for segmented/unsupported completion formats. No synthetic completions.
module openpcie_cpl_to_axis (
 input logic clk_i, rst_i,
 input logic [63:0] cpl_data_i,
 input logic [1:0] cpl_strb_i,
 input logic [127:0] cpl_hdr_i,
 input logic cpl_valid_i, cpl_sop_i, cpl_eop_i,
 output logic cpl_ready_o,
 output logic [31:0] m_data_o,
 output logic [3:0] m_keep_o,
 output logic m_valid_o, m_last_o,
 output logic [4:0] m_user_o,
 input logic m_ready_i,
 output logic [31:0] completed_count_o
);
  typedef enum logic [2:0] {IDLE,DW0,DW1,DW2,DATA} state_t;
  state_t state_r;
  logic [127:0] hdr_r;
  logic [31:0] payload_r;
  function automatic [31:0] to_wire(input logic [31:0] x);
    to_wire={x[7:0],x[15:8],x[23:16],x[31:24]};
  endfunction
  assign cpl_ready_o = state_r == IDLE;
  assign m_valid_o = state_r != IDLE;
  assign m_keep_o = 4'hf;
  assign m_user_o = '0;
  assign m_last_o = state_r == DATA;
  always_comb begin
    case(state_r)
      DW0: m_data_o = to_wire(hdr_r[127:96]);
      DW1: m_data_o = to_wire(hdr_r[95:64]);
      DW2: m_data_o = to_wire(hdr_r[63:32]);
      DATA: m_data_o = payload_r;
      default: m_data_o = '0;
    endcase
  end
  always_ff @(posedge clk_i) begin
    if(rst_i) begin
      state_r<=IDLE;
      hdr_r<='0;payload_r<='0;completed_count_o<='0;
    end else begin
      if (cpl_valid_i && cpl_ready_o) begin
        if (!cpl_sop_i || !cpl_eop_i || cpl_hdr_i[127:120]!=8'h4a ||
            cpl_hdr_i[105:96]!=10'd1 || cpl_strb_i!=2'b01)
          $fatal(1,"unsupported actual PCIe completion fmt=%h len=%d strb=%b",cpl_hdr_i[127:120],cpl_hdr_i[105:96],cpl_strb_i);
        hdr_r<=cpl_hdr_i;
        payload_r<=cpl_data_i[31:0];
        state_r<=DW0;
      end
      if (m_valid_o && m_ready_i) begin
        case (state_r)
          DW0: state_r<=DW1;
          DW1: state_r<=DW2;
          DW2: state_r<=DATA;
          DATA: begin state_r<=IDLE;completed_count_o<=completed_count_o+1; end
          default: $fatal(1,"invalid completion serializer state");
        endcase
      end
    end
  end
endmodule
