"""Real PCIe TLP <-> AXI4 edge wiring reused by the opt-in full-chip generator.

This structural adapter is deliberately only pin assignment, never a router,
testbench AXI memory model, PCIe LTSSM, DMA engine or PHY. Upstream pinned
alexforencich pcie_axi_master owns PCIe TLP processing.
"""

TLP_PORTS = [
    "input logic [64-1:0] rx_req_tlp_data",
    "input logic [128-1:0] rx_req_tlp_hdr",
    "input logic [1-1:0] rx_req_tlp_valid",
    "input logic [1-1:0] rx_req_tlp_sop",
    "input logic [1-1:0] rx_req_tlp_eop",
    "output logic rx_req_tlp_ready",
    "output logic [64-1:0] tx_cpl_tlp_data",
    "output logic [2-1:0] tx_cpl_tlp_strb",
    "output logic [128-1:0] tx_cpl_tlp_hdr",
    "output logic [1-1:0] tx_cpl_tlp_valid",
    "output logic [1-1:0] tx_cpl_tlp_sop",
    "output logic [1-1:0] tx_cpl_tlp_eop",
    "input logic tx_cpl_tlp_ready",
    "input logic [15:0] completer_id",
    "input logic [2:0] max_payload_size",
    "output logic status_error_cor",
    "output logic status_error_uncor"
]

def top_ports():
    return ["  "+x+"," for x in TLP_PORTS]

def instance_ports():
    import re
    return [".{0}({0})".format(re.search(r"([a-z][a-z0-9_]*)$", p).group(1))
            for p in TLP_PORTS]

def bridge_lines(host_req: str, host_rsp: str):
    """Connect real upstream PCIe RTL to a typed generated peripheral NI."""
    return " logic [4-1:0] m_axi_awid;\n logic [64-1:0] m_axi_awaddr;\n logic [7:0] m_axi_awlen;\n logic [2:0] m_axi_awsize;\n logic [1:0] m_axi_awburst;\n logic m_axi_awlock;\n logic [3:0] m_axi_awcache;\n logic [2:0] m_axi_awprot;\n logic m_axi_awvalid;\n logic m_axi_awready;\n logic [64-1:0] m_axi_wdata;\n logic [8-1:0] m_axi_wstrb;\n logic m_axi_wlast;\n logic m_axi_wvalid;\n logic m_axi_wready;\n logic [4-1:0] m_axi_bid;\n logic [1:0] m_axi_bresp;\n logic m_axi_bvalid;\n logic m_axi_bready;\n logic [4-1:0] m_axi_arid;\n logic [64-1:0] m_axi_araddr;\n logic [7:0] m_axi_arlen;\n logic [2:0] m_axi_arsize;\n logic [1:0] m_axi_arburst;\n logic m_axi_arlock;\n logic [3:0] m_axi_arcache;\n logic [2:0] m_axi_arprot;\n logic m_axi_arvalid;\n logic m_axi_arready;\n logic [4-1:0] m_axi_rid;\n logic [64-1:0] m_axi_rdata;\n logic [1:0] m_axi_rresp;\n logic m_axi_rlast;\n logic m_axi_rvalid;\n logic m_axi_rready;\n\n  // One actual generated FlooNoC: use PCIe0's 64-bit host-initiator NI; it is an independent generated NoC.\n  floo_xezim_pcie0_local_data_noc_pkg::axi_in_req_t pcie_req;\n  floo_xezim_pcie0_local_data_noc_pkg::axi_in_rsp_t pcie_rsp;\n  floo_xezim_pcie0_local_data_noc_pkg::axi_out_req_t sram_req;\n  floo_xezim_pcie0_local_data_noc_pkg::axi_out_rsp_t sram_rsp;\n  assign pcie_req.aw.id = m_axi_awid;\n  assign pcie_req.aw.addr = m_axi_awaddr;\n  assign pcie_req.aw.len = m_axi_awlen;\n  assign pcie_req.aw.size = m_axi_awsize;\n  assign pcie_req.aw.burst = m_axi_awburst;\n  assign pcie_req.aw.lock = m_axi_awlock;\n  assign pcie_req.aw.cache = m_axi_awcache;\n  assign pcie_req.aw.prot = m_axi_awprot;\n  assign pcie_req.w.data = m_axi_wdata;\n  assign pcie_req.w.strb = m_axi_wstrb;\n  assign pcie_req.w.last = m_axi_wlast;\n  assign pcie_req.ar.id = m_axi_arid;\n  assign pcie_req.ar.addr = m_axi_araddr;\n  assign pcie_req.ar.len = m_axi_arlen;\n  assign pcie_req.ar.size = m_axi_arsize;\n  assign pcie_req.ar.burst = m_axi_arburst;\n  assign pcie_req.ar.lock = m_axi_arlock;\n  assign pcie_req.ar.cache = m_axi_arcache;\n  assign pcie_req.ar.prot = m_axi_arprot;\n  assign pcie_req.aw.qos = '0;\n  assign pcie_req.aw.region = '0;\n  assign pcie_req.aw.user = '0;\n  assign pcie_req.ar.qos = '0;\n  assign pcie_req.ar.region = '0;\n  assign pcie_req.ar.user = '0;\n  assign pcie_req.aw.atop = '0;\n  assign pcie_req.w.user = '0;\n  assign pcie_req.aw_valid = m_axi_awvalid;\n  assign pcie_req.w_valid = m_axi_wvalid;\n  assign pcie_req.ar_valid = m_axi_arvalid;\n  assign pcie_req.b_ready = m_axi_bready;\n  assign pcie_req.r_ready = m_axi_rready;\n  assign m_axi_awready = pcie_rsp.aw_ready;\n  assign m_axi_wready = pcie_rsp.w_ready;\n  assign m_axi_arready = pcie_rsp.ar_ready;\n  assign m_axi_bvalid = pcie_rsp.b_valid;\n  assign m_axi_rvalid = pcie_rsp.r_valid;\n  assign m_axi_bid = pcie_rsp.b.id;\n  assign m_axi_bresp = pcie_rsp.b.resp;\n  assign m_axi_rid = pcie_rsp.r.id;\n  assign m_axi_rdata = pcie_rsp.r.data;\n  assign m_axi_rresp = pcie_rsp.r.resp;\n  assign m_axi_rlast = pcie_rsp.r.last;\n\n  pcie_axi_master #(\n    .TLP_DATA_WIDTH(64), .TLP_STRB_WIDTH(2), .TLP_HDR_WIDTH(128),\n    .TLP_SEG_COUNT(1), .AXI_DATA_WIDTH(64), .AXI_ADDR_WIDTH(64),\n    .AXI_STRB_WIDTH(8), .AXI_ID_WIDTH(4), .AXI_MAX_BURST_LEN(256)\n  ) u_bridge (\n    .clk(clk_i),\n    .rst(~rst_ni),\n    .rx_req_tlp_data(rx_req_tlp_data),\n    .rx_req_tlp_hdr(rx_req_tlp_hdr),\n    .rx_req_tlp_valid(rx_req_tlp_valid),\n    .rx_req_tlp_sop(rx_req_tlp_sop),\n    .rx_req_tlp_eop(rx_req_tlp_eop),\n    .rx_req_tlp_ready(rx_req_tlp_ready),\n    .tx_cpl_tlp_data(tx_cpl_tlp_data),\n    .tx_cpl_tlp_strb(tx_cpl_tlp_strb),\n    .tx_cpl_tlp_hdr(tx_cpl_tlp_hdr),\n    .tx_cpl_tlp_valid(tx_cpl_tlp_valid),\n    .tx_cpl_tlp_sop(tx_cpl_tlp_sop),\n    .tx_cpl_tlp_eop(tx_cpl_tlp_eop),\n    .tx_cpl_tlp_ready(tx_cpl_tlp_ready),\n    .m_axi_awid(m_axi_awid),\n    .m_axi_awaddr(m_axi_awaddr),\n    .m_axi_awlen(m_axi_awlen),\n    .m_axi_awsize(m_axi_awsize),\n    .m_axi_awburst(m_axi_awburst),\n    .m_axi_awlock(m_axi_awlock),\n    .m_axi_awcache(m_axi_awcache),\n    .m_axi_awprot(m_axi_awprot),\n    .m_axi_awvalid(m_axi_awvalid),\n    .m_axi_awready(m_axi_awready),\n    .m_axi_wdata(m_axi_wdata),\n    .m_axi_wstrb(m_axi_wstrb),\n    .m_axi_wlast(m_axi_wlast),\n    .m_axi_wvalid(m_axi_wvalid),\n    .m_axi_wready(m_axi_wready),\n    .m_axi_bid(m_axi_bid),\n    .m_axi_bresp(m_axi_bresp),\n    .m_axi_bvalid(m_axi_bvalid),\n    .m_axi_bready(m_axi_bready),\n    .m_axi_arid(m_axi_arid),\n    .m_axi_araddr(m_axi_araddr),\n    .m_axi_arlen(m_axi_arlen),\n    .m_axi_arsize(m_axi_arsize),\n    .m_axi_arburst(m_axi_arburst),\n    .m_axi_arlock(m_axi_arlock),\n    .m_axi_arcache(m_axi_arcache),\n    .m_axi_arprot(m_axi_arprot),\n    .m_axi_arvalid(m_axi_arvalid),\n    .m_axi_arready(m_axi_arready),\n    .m_axi_rid(m_axi_rid),\n    .m_axi_rdata(m_axi_rdata),\n    .m_axi_rresp(m_axi_rresp),\n    .m_axi_rlast(m_axi_rlast),\n    .m_axi_rvalid(m_axi_rvalid),\n    .m_axi_rready(m_axi_rready),\n    .completer_id(completer_id),\n    .max_payload_size(max_payload_size),\n    .status_error_cor(status_error_cor),\n    .status_error_uncor(status_error_uncor)\n  );\n" + "\n  assign " + host_req + " = pcie_req;\n  assign pcie_rsp = " + host_rsp + ";\n"

def host_variant_config(cfg):
    """Use a bigger *only opt-in* immutable flash slot for CPU/host barriers.

    The canonical 256-byte firmware layout, SRAM sizes, running CPU images
    and generated gen/ tree are left unchanged. This is a variant profile.
    """
    from copy import deepcopy
    result = deepcopy(cfg)
    current = result["boot"]["flash_slot_stride"]
    if type(current) is not int or current <= 0 or current > 512:
        raise ValueError("unsupported PCIe host flash slot")
    mailbox = int(result["verification"]["full_chip_boot"]["mailbox_offset"], 0)
    if mailbox < 512 or mailbox % 4:
        raise ValueError("no room for isolated host boot code before mailbox")
    result["boot"]["flash_slot_stride"] = 512
    return result
