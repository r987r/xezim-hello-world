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
            "       .fc_initialized_o       (fc_initialized_o),\n",
            "       .fc_initialized_o       (fc_initialized_o),\n"+
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
            "       .cfg_function_number_o(cfg_function_number_o),\n",
            "       .cfg_function_number_o(cfg_function_number_o),\n"+
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
    print("OpenPCIe BAR overlay installed in actual internal receiver (NOT BAR proof)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    args = parser.parse_args()
    apply(args.checkout)
