#!/usr/bin/env python3
"""Explicit pinned OpenPCIe configuration wrapper BAR0 overlay.

The original source stays outside this repo. Patch only a detached .tools
checkout at the immutable IP lock, after the selected LTSSM overlay was applied.
Generated PeakRDL register block remains unmodified; this wrapper overlays
BAR0/COMMAND read values and watches real config AXI-Lite handshakes.

This changes actual host config TLP plumbing, but L0/config-TLP tests must
still prove on-wire behavior. No success is inferred from source patching.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

UPSTREAM_BLOB = "1625d210addbedbe9627f22ddeddd51a36b7792e"
SOURCE = Path("src/pcie_cfg/pcie_cfg_wrapper.sv")
# ConfigWr0 reaches this pinned upstream decoder with its real 3-DW payload,
# but the unmodified RTL wrongly treats only 4-DW packets as having data and
# forwards a zero data bus to the AXI-Lite config handler. Preserve the
# upstream dependency as a replaceable, commit-pinned simulation-only overlay.
DECODE_SOURCE = Path("src/pcie_cfg/pcie_config_decode.sv")
DECODE_BLOB = "6e43bdfdc51109b78251c6cd302c52093fad2838"

# Original pinned source revisions. The independent LTSSM/timer patch is
# applied to pcie_phy_top.sv earlier; check its git HEAD blob, not the
# modified working-tree blob. The others must still be pristine.
HIERARCHY_BLOBS = {
    "src/pcie_phy_core/pcie_phy_top.sv": "31421eba1df71f271830d3ff72fb5aa16efa4a46",
    "src/dllp/pcie_datalink_layer.sv": "c2ffdd9d86d16498dfe1517cc61db2da1dfaedac",
    "src/dllp/dllp_receive.sv": "a64defb2d5ee74469b2cd2af08dd5b5c04461177",
}
BAR_PORTS = """    input  logic        bar0_device_committed_i,
    input  logic [31:0] bar0_device_aperture_i,
    output logic [31:0] bar0_host_bus_base_o,
    output logic        bar0_host_memory_enable_o,
    output logic        bar0_probe_o,
    output logic        bar0_cfg_violation_o,
"""
BAR_BINDINGS = """      .bar0_device_committed_i (bar0_device_committed_i),
      .bar0_device_aperture_i  (bar0_device_aperture_i),
      .bar0_host_bus_base_o    (bar0_host_bus_base_o),
      .bar0_host_memory_enable_o(bar0_host_memory_enable_o),
      .bar0_probe_o           (bar0_probe_o),
      .bar0_cfg_violation_o   (bar0_cfg_violation_o),
"""


def substitute_once(source: str, old: str, new: str, what: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"OpenPCIe config overlay drift at {what}")
    return source.replace(old, new, 1)


def overlay(source: str) -> str:
    source = substitute_once(
        source,
        "    output pcie_config_reg__out_t hwif_out\n);",
        """    output pcie_config_reg__out_t hwif_out,
    input logic bar0_device_committed_i,
    input logic [31:0] bar0_device_aperture_i,
    output logic [31:0] bar0_host_bus_base_o,
    output logic bar0_host_memory_enable_o,
    output logic bar0_probe_o,
    output logic bar0_cfg_violation_o
);""", "wrapper port list")
    source = substitute_once(
        source,
        "  //Ports\n",
        """  // Source-qualified BAR0 overlay, not a duplicate Type-0 register bank.
  logic [31:0] bar0_rdl_read_data;
  logic [31:0] bar0_host_read_data;
  pcie_bar0_host_cfg bar0_host_cfg_inst (
      .clk_i(clk_i), .rst_ni(!rst_i),
      .device_bar_committed_i(bar0_device_committed_i),
      .device_bar_aperture_i(bar0_device_aperture_i),
      .awvalid_i(s_axil_awvalid), .awready_i(s_axil_awready),
      .awaddr_i(s_axil_awaddr[8:0]),
      .wvalid_i(s_axil_wvalid), .wready_i(s_axil_wready),
      .wdata_i(s_axil_wdata), .wstrb_i(s_axil_wstrb),
      .arvalid_i(s_axil_arvalid), .arready_i(s_axil_arready),
      .araddr_i(s_axil_araddr[8:0]),
      .rdata_from_rdl_i(bar0_rdl_read_data),
      .rdata_to_host_o(bar0_host_read_data),
      .host_bar0_bus_base_o(bar0_host_bus_base_o),
      .host_memory_enable_o(bar0_host_memory_enable_o),
      .bar0_probe_o(bar0_probe_o),
      .cfg_violation_o(bar0_cfg_violation_o)
  );
  //Ports
""", "config BAR instance")
    # Both original register and host handler have s_axil_rdata connections.
    # Rewrite ONLY the original handler; leave original RDL as raw source.
    block = source.split("  pcie_config_handler #", 1)
    if len(block) != 2:
        raise ValueError("missing upstream config handler")
    before, rest = block
    rest = substitute_once(rest,
        ".s_axil_rdata         (s_axil_rdata),",
        ".s_axil_rdata         (bar0_host_read_data),",
        "handler read mux")
    # The register bank's read data is still upstream owned.
    rest = substitute_once(rest,
        ".s_axil_rdata  (s_axil_rdata),",
        ".s_axil_rdata  (bar0_rdl_read_data),",
        "RDL register bank read tap")
    return before + "  pcie_config_handler #" + rest


def overlay_decode(source: str) -> str:
    """Repair the ORIGINAL ConfigWr0 payload path; never inject host data.

    The RX skid stream actually carries the transmitted DWORD; the pinned
    decoder previously skipped it for 3-DW writes and forwarded all-zero data.
    Keep ordinary reads payload-free and preserve backpressure semantics.
    """
    source = substitute_once(
        source,
        "          D.tlp_is_3dw             = '0;\\n"
        "          D.tlp_data               = '0;\\n"
        "          D.tlp_is_sop             = '1;",
        "          D.tlp_is_3dw             = '0;\\n"
        "          D.tlp_is_pd              = '0;\\n"
        "          D.word_count             = '0;\\n"
        "          D.tlp_data               = '0;\\n"
        "          D.tlp_is_sop             = '1;",
        "decoder new-TLP state reset")
    source = substitute_once(
        source,
        "          if (tlp_dw0.byte0.Fmt inside {TLP_4DW_ND, TLP_4DW_WD}) begin",
        "          if (tlp_dw0.byte0.Fmt inside {TLP_3DW_WD, TLP_4DW_WD}) begin",
        "decoder format has-data selection")
    source = substitute_once(
        source,
        "      ST_TLP_STREAM: begin\\n"
        "        skid_axis_tready = '1;\\n"
        "        if (s_axis_tvalid) begin\\n"
        "          D.tlp_data[(3-Q.word_count)*32+:32] = tlp_byte_swapped;",
        "      ST_TLP_STREAM: begin\\n"
        "        skid_axis_tready = '1;\\n"
        "        if (skid_axis_tvalid) begin\\n"
        "          D.tlp_data[Q.word_count*32+:32] = tlp_byte_swapped;",
        "decoder capture accepted payload DWORD in low bits")
    source = substitute_once(
        source,
        "          if (s_axis_tlast) begin\\n"
        "            D.tlp_is_eop = '1;",
        "          if (skid_axis_tlast) begin\\n"
        "            D.tlp_is_eop = '1;",
        "decoder accepted final payload beat")
    source = substitute_once(
        source,
        "      ST_TLP_SEND: begin\\n"
        "        tlp_valid = '1;\\n"
        "        if (tlp_ready) begin\\n"
        "          tlp_tdata    = '0;\\n"
        "          tlp_strb     = '0;\\n"
        "          D.tlp_is_sop = '0;\\n"
        "          D.tlp_is_eop = '0;\\n"
        "          tlp_eop      = Q.tlp_is_eop;\\n"
        "          tlp_sop      = Q.tlp_is_sop;",
        "      ST_TLP_SEND: begin\\n"
        "        tlp_valid = '1;\\n"
        "        // Hold the actual accepted payload stable until the next stage\\n"
        "        // accepts it. ConfigRd0 correctly retains a zero payload.\\n"
        "        tlp_tdata = Q.tlp_data[DATA_WIDTH-1:0];\\n"
        "        tlp_strb  = Q.tlp_is_pd ? '1 : '0;\\n"
        "        tlp_eop   = Q.tlp_is_eop;\\n"
        "        tlp_sop   = Q.tlp_is_sop;\\n"
        "        if (tlp_ready) begin\\n"
        "          D.tlp_is_sop = '0;\\n"
        "          D.tlp_is_eop = '0;",
        "decoder stable payload output")
    return source


def overlay_hierarchy(path: str, source: str) -> str:
    """Connect the ONE existing internal config wrapper, never a parallel TB
    wrapper. All six BAR signals cross the true PHY→DLLP→receiver boundary.
    """
    if path.endswith("/pcie_phy_top.sv"):
        source=substitute_once(
            source,
            "    output logic                                    fc_initialized_o,\n",
            "    output logic                                    fc_initialized_o,\n"+
            BAR_PORTS, "PHY public BAR ports")
        source=substitute_once(
            source,
            "      .fc_initialized_o       (fc_initialized_o),\n",
            "      .fc_initialized_o       (fc_initialized_o),\n"+
            BAR_BINDINGS, "PHY to DLL BAR ports")
        if source.count("SIM_FAST_LINK") < 2:
            raise ValueError("upstream LTSSM patch missing before BAR hierarchy overlay")
        return source
    if path.endswith("/pcie_datalink_layer.sv"):
        source=substitute_once(
            source,
            "    output logic                  fc_initialized_o,\n",
            "    output logic                  fc_initialized_o,\n"+
            BAR_PORTS, "DLL BAR ports")
        return substitute_once(
            source,
            "      .cfg_function_number_o (cfg_function_number_o),\n",
            "      .cfg_function_number_o (cfg_function_number_o),\n"+
            BAR_BINDINGS, "DLL to RX BAR ports")
    if path.endswith("/dllp_receive.sv"):
        source=substitute_once(
            source,
            "    output logic [ 2:0] cfg_function_number_o,\n",
            "    output logic [ 2:0] cfg_function_number_o,\n"+
            BAR_PORTS, "RX BAR ports")
        return substitute_once(
            source,
            "      .cfg_function_number_o(cfg_function_number_o),\n",
            "      .cfg_function_number_o(cfg_function_number_o),\n"+
            BAR_BINDINGS, "RX to actual internal config BAR ports")
    raise ValueError(f"unrecognized upstream BAR hierarchy path: {path}")


def apply(checkout: Path) -> None:
    target = checkout / SOURCE
    if not target.is_file():
        raise ValueError(f"missing pinned OpenPCIe source: {target}")
    blob = subprocess.run(
        ["git", "-C", str(checkout), "hash-object", str(SOURCE)],
        check=True, text=True, capture_output=True).stdout.strip()
    if blob != UPSTREAM_BLOB:
        raise ValueError(f"OpenPCIe config wrapper moved; expected {UPSTREAM_BLOB}, found {blob}")
    source = target.read_text()
    changed = overlay(source)
    if changed == source:
        raise ValueError("BAR overlay did not change upstream source")
    target.write_text(changed)
    # The wrapper above is the ONE instantiated inside dllp_receive. The
    # earlier experiment mistakenly patched it while instantiating a second
    # disconnected wrapper in the TB. That path cannot prove a real BAR.
    for rel, expected_blob in HIERARCHY_BLOBS.items():
        original=subprocess.run(
            ["git","-C",str(checkout),"rev-parse",f"HEAD:{rel}"],
            check=True,text=True,capture_output=True).stdout.strip()
        if original != expected_blob:
            raise ValueError(f"OpenPCIe hierarchy source drift at {rel}")
        part=checkout/rel
        if not part.is_file() or part.is_symlink():
            raise ValueError(f"missing original PCIe hierarchy file: {rel}")
        before=part.read_text()
        after=overlay_hierarchy(rel,before)
        if before==after:
            raise ValueError(f"PCIe BAR hierarchy did not change: {rel}")
        part.write_text(after)
        print(f"OPENPCIE_BAR_HIERARCHY: {rel} real internal config path connected")
    # The genuine endpoint receiver uses this decoder for ConfigWr0 and
    # ConfigRd0; do not synthesize a fake AXI value in the testbench.
    decoder_path = checkout / DECODE_SOURCE
    if not decoder_path.is_file() or decoder_path.is_symlink():
        raise ValueError(f"missing original OpenPCIe config decoder: {DECODE_SOURCE}")
    original_decoder_blob = subprocess.run(
        ["git", "-C", str(checkout), "hash-object", str(DECODE_SOURCE)],
        check=True, text=True, capture_output=True).stdout.strip()
    if original_decoder_blob != DECODE_BLOB:
        raise ValueError(
            f"OpenPCIe config decoder drift: {original_decoder_blob} != {DECODE_BLOB}")
    before_decoder = decoder_path.read_text()
    after_decoder = overlay_decode(before_decoder)
    decoder_path.write_text(after_decoder)
    print("OPENPCIE_CFG_DECODE: real accepted 3-DW ConfigWr0 payload carried to AXI-Lite WDATA")
    print("OpenPCIe BAR overlay installed in actual internal receiver (NOT BAR proof)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    args = parser.parse_args()
    apply(args.checkout)
