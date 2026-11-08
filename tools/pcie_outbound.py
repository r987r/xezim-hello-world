"""Pinned PCIe requester with CPU-owned descriptor CSR on real Config NoC.

Only PCIe TLP pins may leave the full-chip top. Descriptor valid/ready/status
are internal nets between requester RTL and the real memory-mapped controller.
"""
import re

OUTBOUND_PORTS = [
    "output logic [127:0] tx_rd_req_tlp_hdr",
    "output logic [4:0] tx_rd_req_tlp_seq",
    "output logic tx_rd_req_tlp_valid",
    "output logic tx_rd_req_tlp_sop",
    "output logic tx_rd_req_tlp_eop",
    "input logic tx_rd_req_tlp_ready",
    "output logic [63:0] tx_wr_req_tlp_data",
    "output logic [1:0] tx_wr_req_tlp_strb",
    "output logic [127:0] tx_wr_req_tlp_hdr",
    "output logic [4:0] tx_wr_req_tlp_seq",
    "output logic tx_wr_req_tlp_valid",
    "output logic tx_wr_req_tlp_sop",
    "output logic tx_wr_req_tlp_eop",
    "input logic tx_wr_req_tlp_ready",
    "input logic [63:0] rx_cpl_tlp_data",
    "input logic [127:0] rx_cpl_tlp_hdr",
    "input logic [3:0] rx_cpl_tlp_error",
    "input logic rx_cpl_tlp_valid",
    "input logic rx_cpl_tlp_sop",
    "input logic rx_cpl_tlp_eop",
    "output logic rx_cpl_tlp_ready",
    "input logic [63:0] s_axis_read_desc_pcie_addr",
    "input logic [15:0] s_axis_read_desc_ram_addr",
    "input logic [15:0] s_axis_read_desc_len",
    "input logic [7:0] s_axis_read_desc_tag",
    "input logic s_axis_read_desc_valid",
    "output logic s_axis_read_desc_ready",
    "output logic [7:0] m_axis_read_desc_status_tag",
    "output logic [3:0] m_axis_read_desc_status_error",
    "output logic m_axis_read_desc_status_valid",
    "input logic [63:0] s_axis_write_desc_pcie_addr",
    "input logic [15:0] s_axis_write_desc_ram_addr",
    "input logic [15:0] s_axis_write_desc_len",
    "input logic [7:0] s_axis_write_desc_tag",
    "input logic s_axis_write_desc_valid",
    "output logic s_axis_write_desc_ready",
    "output logic [7:0] m_axis_write_desc_status_tag",
    "output logic [3:0] m_axis_write_desc_status_error",
    "output logic m_axis_write_desc_status_valid",
]

RAM_WIRES = {
    "ram_rd_cmd_sel": 4,
    "ram_rd_cmd_addr": 24,
    "ram_rd_cmd_valid": 2,
    "ram_rd_cmd_ready": 2,
    "ram_rd_resp_data": 128,
    "ram_rd_resp_valid": 2,
    "ram_rd_resp_ready": 2,
    "ram_wr_cmd_sel": 4,
    "ram_wr_cmd_be": 16,
    "ram_wr_cmd_addr": 24,
    "ram_wr_cmd_data": 128,
    "ram_wr_cmd_valid": 2,
    "ram_wr_cmd_ready": 2,
    "ram_wr_done": 2,
}


def top_ports():
    return ["  " + port + "," for port in OUTBOUND_PORTS
            if 's_axis_' not in port and 'm_axis_' not in port]


def instance_ports():
    return [".{0}({0})".format(re.search(r"([a-z][a-z0-9_]*)$", p).group(1))
            for p in OUTBOUND_PORTS if 's_axis_' not in p and 'm_axis_' not in p]


def csr_ports():
    """Only internal descriptor/return-status wires, never the TLP pins."""
    return {re.search(r"([a-z][a-z0-9_]*)$", port).group(1):
            re.search(r"([a-z][a-z0-9_]*)$", port).group(1)
            for port in OUTBOUND_PORTS
            if 's_axis_' in port or 'm_axis_' in port}


def sram_ports():
    return {key: key for key in RAM_WIRES}


def requester_lines():
    lines = [
        "// PCIe requester alongside the independent host-to-device bridge.",
        "// No custom TLP serialization; upstream dma_if_pcie owns all requester TLPs.",
        *[f"  logic [{width-1}:0] {name};" for name, width in RAM_WIRES.items()],
        *[f"  logic {port.split('logic ',1)[1]};" for port in OUTBOUND_PORTS
          if 's_axis_' in port or 'm_axis_' in port],
        "  logic pcie_requester_error_cor, pcie_requester_error_uncor;",
    ]
    c = [
        ".clk(clk_i)", ".rst(~rst_ni)",
        *[f".{port_name}({port_name})" for port_name in
          ("rx_cpl_tlp_data", "rx_cpl_tlp_hdr", "rx_cpl_tlp_error",
           "rx_cpl_tlp_valid", "rx_cpl_tlp_sop", "rx_cpl_tlp_eop",
           "rx_cpl_tlp_ready", "tx_rd_req_tlp_hdr", "tx_rd_req_tlp_seq",
           "tx_rd_req_tlp_valid", "tx_rd_req_tlp_sop", "tx_rd_req_tlp_eop",
           "tx_rd_req_tlp_ready", "tx_wr_req_tlp_data", "tx_wr_req_tlp_strb",
           "tx_wr_req_tlp_hdr", "tx_wr_req_tlp_seq", "tx_wr_req_tlp_valid",
           "tx_wr_req_tlp_sop", "tx_wr_req_tlp_eop", "tx_wr_req_tlp_ready",
           "s_axis_read_desc_pcie_addr", "s_axis_read_desc_ram_addr",
           "s_axis_read_desc_len", "s_axis_read_desc_tag",
           "s_axis_read_desc_valid", "s_axis_read_desc_ready",
           "m_axis_read_desc_status_tag", "m_axis_read_desc_status_error",
           "m_axis_read_desc_status_valid",
           "s_axis_write_desc_pcie_addr", "s_axis_write_desc_ram_addr",
           "s_axis_write_desc_len", "s_axis_write_desc_tag",
           "s_axis_write_desc_valid", "s_axis_write_desc_ready",
           "m_axis_write_desc_status_tag", "m_axis_write_desc_status_error",
           "m_axis_write_desc_status_valid")],
        ".s_axis_read_desc_ram_sel(2'b0)",
        ".s_axis_write_desc_ram_sel(2'b0)",
        ".s_axis_write_desc_imm(32'b0)",
        ".s_axis_write_desc_imm_en(1'b0)",
        ".s_axis_rd_req_tx_seq_num(5'b0)",
        ".s_axis_rd_req_tx_seq_num_valid(1'b0)",
        ".s_axis_wr_req_tx_seq_num(5'b0)",
        ".s_axis_wr_req_tx_seq_num_valid(1'b0)",
        *[f".{name}({name})" for name in RAM_WIRES],
        ".read_enable(1'b1)", ".write_enable(1'b1)",
        ".ext_tag_enable(1'b0)", ".rcb_128b(1'b0)",
        ".requester_id(completer_id)",
        ".max_read_request_size(3'b0)",
        ".max_payload_size(max_payload_size)",
        ".status_rd_busy()", ".status_wr_busy()",
        ".status_error_cor(pcie_requester_error_cor)",
        ".status_error_uncor(pcie_requester_error_uncor)",
    ]
    lines += [
        "  dma_if_pcie #(",
        "    .TLP_DATA_WIDTH(64), .TLP_STRB_WIDTH(2), .TLP_HDR_WIDTH(128),",
        "    .TLP_SEG_COUNT(1), .RAM_SEL_WIDTH(2), .RAM_ADDR_WIDTH(16),",
        "    .RAM_SEG_COUNT(2), .RAM_SEG_DATA_WIDTH(64), .RAM_SEG_BE_WIDTH(8),",
        "    .RAM_SEG_ADDR_WIDTH(12), .PCIE_TAG_COUNT(32),",
        "    .READ_OP_TABLE_SIZE(8), .WRITE_OP_TABLE_SIZE(8),",
        "    .READ_TX_LIMIT(4), .WRITE_TX_LIMIT(4),",
        "    .TX_SEQ_NUM_ENABLE(0), .LEN_WIDTH(16), .TAG_WIDTH(8)",
        "  ) u_pcie_requester (",
        "    " + ",\n    ".join(c),
        "  );",
    ]
    return "\n".join(lines)
