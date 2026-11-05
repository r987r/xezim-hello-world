"""Fail-closed source-truth audit for Ethernet0 generated FlooNoCs and chip diagrams.

Reads the SINGLE canonical SoC configuration, generated FlooGen manifests and
single diagram-gen topology. An endpoint drawn as an attached MAC/queue/CSR is
an error until real RTL is instantiated in gen/chip/soc_top.sv. This is not a
substitute for dynamic packet tests, parsed RTL connectivity or regenerating gen/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import yaml


class EthernetTopologyError(ValueError):
    pass


def require(condition: bool, message: str):
    if not condition:
        raise EthernetTopologyError(message)


def read_json(path: Path):
    require(path.is_file(), f"missing generated source: {path}")
    return json.loads(path.read_text())


def address_window(cfg: dict, name: str, plane: str):
    windows = [r for r in cfg["address_map"][plane] if r["name"] == name]
    require(len(windows) == 1, f"expected exactly one {plane} address window {name}")
    window = windows[0]
    return int(window["base"], 0), int(window["size"], 0)


def audit(root: Path, *, device: str = "ethernet0") -> dict:
    root = Path(root)
    cfg_path = root / "config/soc.yaml"
    require(cfg_path.is_file(), "missing canonical config/soc.yaml")
    cfg = yaml.safe_load(cfg_path.read_text())
    peripheral = [p for p in cfg["subsystems"] if p["name"] == device]
    require(len(peripheral) == 1 and peripheral[0]["type"] == "peripheral",
            f"single {device} peripheral declaration required")
    require(peripheral[0].get("ip") == "ethernet_queue_mac",
            "unexpected Ethernet0 IP without reviewed diagram/RTL contract")
    data_base, data_size = address_window(cfg, device + ".sram", "data")
    csr_base, csr_size = address_window(cfg, device + ".ctrl", "config")
    require(data_size > 0 and csr_size > 0 and not(data_base % 4096) and
            not(csr_base % 4096), "Ethernet0 windows must be nonempty and page aligned")
    require(device in cfg["networks"]["global_config"]["reachable_subsystems"],
            "Ethernet0 missing global config reachability")
    nmanifest = read_json(root / "gen/noc/floonoc/manifest.json")
    graph = read_json(root / "gen/diagrams/graphs.json")["noc_hierarchy"]
    topo = read_json(root / "gen/diagrams/noc-topology.json")
    chip = read_json(root / "gen/chip/manifest.json")
    require(topo.get("source_of_truth") and "config/soc.yaml" in topo["source_of_truth"],
            "diagram is not labeled as generated from SoC YAML")
    require(graph["source"] and graph.get("status"),
            "diagram graph needs provenance and status")
    nets = (device + "_local_data", device + "_local_config")
    expected_endpoints = {
        "data": {"packet_dma", "global_in", "sram", "global_out"},
        "config": {"management", "global_in", "controller_regs", "global_out"},
    }
    for network, plane in zip(nets, ("data", "config")):
        entry = nmanifest["networks"].get(network)
        assert_entry = entry is not None
        require(assert_entry, f"{network} missing generated RTL manifest")
        require(entry["plane"] == plane and entry["status"] ==
                "real_upstream_structural_RTL", f"{network} incorrect NoC provenance")
        diagram_entry = graph["networks"].get(network)
        require(diagram_entry is not None, f"{network} absent from canonical graph")
        require(diagram_entry["config"] == entry["config"] and
                diagram_entry["top"] == entry["top"] and
                diagram_entry["routers"] == entry["routers"] and
                diagram_entry["endpoints"] == entry["endpoint_count"] and
                diagram_entry["plane"] == plane,
                f"{network} graph does not match FlooGen source")
        top = root / "gen/noc/floonoc" / entry["top"]
        conf = root / "gen/noc/floonoc" / entry["config"]
        require(top.is_file() and conf.is_file(), f"{network} generated top/config missing")
        require(re.search(r"\bmodule\s+" + re.escape(entry["top_module"]) + r"\b",
                          top.read_text()) is not None,
                f"{network} RTL module does not match generated manifest")
        y = yaml.safe_load(conf.read_text())
        endpoint_names = {e["name"] for e in y["endpoints"]}
        require(endpoint_names == expected_endpoints[plane],
                f"{network} endpoints must match reviewed generic peripheral contract")
        require(len(endpoint_names) == entry["endpoint_count"],
                f"{network} endpoint count differs from generated manifest")
        group = [g for g in topo["groups"] if g["name"] == network]
        require(len(group) == 1 and group[0]["info"]["source"] == entry["top"] and
                group[0]["info"]["status"] == "generated_structural",
                f"{network} topology group is stale/duplicated")
        actual = {i["name"] for i in topo["instances"]}
        require({network + "." + e for e in endpoint_names} <= actual,
                f"{network} FlooGen endpoint missing in topology")
    peripheral_records = [x for x in chip["peripheral_subsystems"] if x["name"] == device]
    require(len(peripheral_records) == 1,
            "Ethernet0 missing or duplicated in actual generated chip manifest")
    record = peripheral_records[0]
    require(record["local_data_noc"] == nets[0] and
            record["local_config_noc"] == nets[1],
            "Ethernet0 chip instance uses different NoCs from diagram")
    require(record["rtl_attachment"] in {"reserved_idle", "instantiated"} and
            record["csr_attachment"] in {"explicit_axi_error", "connected"},
            "unknown/implicit Ethernet0 physical attachment status")
    connections = topo["connections"]
    def link(src: str, dst: str):
        matches = [c for c in connections if
                   c["from"]["instance"] == src and c["to"]["instance"] == dst]
        require(len(matches) == 1, f"missing/ambiguous single link: {src} -> {dst}")
        return matches[0]
    structural = [
        (nets[0] + ".global_out", "global_data." + device),
        ("global_data." + device + "_sram", nets[0] + ".global_in"),
        (nets[1] + ".global_out", "global_config." + device),
        ("global_config." + device + "_regs", nets[1] + ".global_in"),
    ]
    for src, dst in structural:
        connection = link(src, dst)
        require(connection["type"] == "axi_interconnect" and
                connection["status"] == "wired_boot_configuration",
                f"structural NoC link not proven: {src} -> {dst}")
    packet = link(device + ".ip", nets[0] + ".packet_dma")
    mgmt = link(device + ".ip", nets[1] + ".management")
    rtl_top = root / "gen/chip/soc_top.sv"
    require(rtl_top.is_file(), "missing generated chip RTL")
    chip_rtl = rtl_top.read_text()
    if record["rtl_attachment"] == "reserved_idle":
        require(packet["status"] == "planned_integration" and
                packet["type"] == "planned_interconnect",
                "reserved Ethernet0 MAC/DMA incorrectly drawn as a wired connection")
        require(not re.search(r"\bethernet_rx_queue_engine\s*(?:#\s*\(|\w+\s*\()",
                              chip_rtl),
                "real Ethernet RX engine instantiated but chip manifest says reserved")
    else:
        require(packet["status"] == "wired_boot_configuration" and
                packet["type"] == "axi_interconnect",
                "real Ethernet RTL attachment missing matching diagram connection")
        require("ethernet_rx_queue_engine" in chip_rtl,
                "manifest claims active Ethernet but no real RX RTL instance in chip")
    if record["csr_attachment"] == "explicit_axi_error":
        require(mgmt["status"] == "planned_integration" and
                mgmt["type"] == "planned_interconnect",
                "unattached Ethernet management incorrectly shown as live")
    else:
        require(mgmt["status"] == "wired_boot_configuration" and
                mgmt["type"] == "axi_interconnect",
                "live Ethernet queue CSR missing from diagram")
    require(csr_base == 0x40050000 and data_base == 0x13000000,
            "Ethernet0 address windows changed without reviewed integration update")
    return {
        "device": device,
        "generated_networks": list(nets),
        "data_window": [data_base, data_size],
        "config_window": [csr_base, csr_size],
        "packet_attachment": record["rtl_attachment"],
        "config_attachment": record["csr_attachment"],
        "live_packet_data_path": record["rtl_attachment"] == "instantiated" and
            record["csr_attachment"] == "connected",
        "structural_global_links": len(structural),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(audit(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
