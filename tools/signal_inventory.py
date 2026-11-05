#!/usr/bin/env python3
"""Extract *declared* physical signal ports and group logical interfaces.

For the current SoC, the flattened soc_noc ANSI port list gives real RTL
signal names, widths, directions, and source lines. It is NOT proof of
internal connectivity. Optional slang-report JSON supports arbitrary
elaborated hierarchies; slang-netlist dependency paths are separate evidence.

This is a protocol-neutral view, not a new bus or NoC implementation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HEADER = re.compile(
    r"^\s*(input|output|inout)\s+(?:wire|logic|reg)\s+"
    r"(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s+)?"
    r"([A-Za-z_][A-Za-z_0-9]*)\s*,?\s*$"
)
AXI_FIELDS = {
    "aw": {"id", "addr", "len", "size", "burst", "lock", "cache", "prot",
           "qos", "region", "user", "atop", "valid", "ready"},
    "w": {"data", "strb", "last", "user", "valid", "ready"},
    "b": {"id", "resp", "user", "valid", "ready"},
    "ar": {"id", "addr", "len", "size", "burst", "lock", "cache", "prot",
           "qos", "region", "user", "valid", "ready"},
    "r": {"id", "data", "resp", "last", "user", "valid", "ready"},
}
PORT_MARK = re.compile(r"^(?P<role>[ms])_(?P<endpoint>[A-Za-z0-9_]+)_(?P<signal>[A-Za-z0-9_]+)$")
CLOCK = re.compile(r"^(?:clk|clk_i|clock|clock_i|aclk|.*_clk|.*_clk_i|.*_clock)$", re.I)
RESET = re.compile(r"^(?:rst|rst_n|rst_i|rst_ni|reset|reset_n|aresetn|.*_rst_n|.*_reset_n|.*_reset_ni)$", re.I)


def infer_protocol(signal: str) -> dict:
    """Name-based *grouping* only; never claim an actual wire from a name."""
    lower = signal.lower()
    if CLOCK.fullmatch(lower):
        return {"protocol": "clock", "interface": "clock", "channel": "CLOCK",
                "logical_signal": lower, "confidence": "name_inference"}
    if RESET.fullmatch(lower):
        return {"protocol": "reset", "interface": "reset", "channel": "RESET",
                "logical_signal": lower, "confidence": "name_inference"}

    # Respect distinctive protocol prefixes first. Plain txdata/rxdata is
    # ambiguous between Ethernet and PCIe and must not be guessed.
    m = re.fullmatch(r"(?:(?:s|m)_)?axis_(rq|rc|cq|cc)_(?:t)?(.+)", lower)
    if m:
        return {"protocol": "pcie", "interface": "pcie_" + m.group(1),
                "channel": m.group(1).upper(), "logical_signal": m.group(2),
                "confidence": "name_inference"}
    if lower.startswith(("pcie_", "pipe_")):
        ch = "PIPE" if lower.startswith("pipe_") else "PCIe"
        return {"protocol": "pcie", "interface": "pcie", "channel": ch,
                "logical_signal": lower, "confidence": "name_inference"}
    if lower.startswith("dfi_"):
        field = lower[4:]
        ch = ("READ" if field.startswith(("rddata", "rdvalid", "rden"))
              else "WRITE" if field.startswith(("wrdata", "wren"))
              else "TRAINING" if any(k in field for k in ("upd", "train"))
              else "COMMAND")
        return {"protocol": "dfi", "interface": "dfi", "channel": ch,
                "logical_signal": field, "confidence": "name_inference"}
    for prefix in ("gmii_", "rgmii_", "xgmii_", "mii_", "ethernet_", "eth_"):
        if lower.startswith(prefix):
            return {"protocol": "ethernet", "interface": prefix[:-1], "channel": "LINK",
                    "logical_signal": lower[len(prefix):], "confidence": "name_inference"}

    # AXI4(-Lite) classic AW/W/B/AR/R channels. This also matches qualified
    # names such as m_axi_awaddr, axi4_lite_arready, and flat awaddr.
    for channel in ("aw", "ar", "w", "b", "r"):
        for field in AXI_FIELDS[channel]:
            tail = channel + field
            if lower == tail or lower.endswith("_" + tail):
                prefix = lower[:-len(tail)].rstrip("_")
                return {"protocol": "axi4", "interface": prefix or "axi",
                        "channel": channel.upper(), "logical_signal": field,
                        "confidence": "name_inference"}
            split_tail = channel + "_" + field
            if lower == split_tail or lower.endswith("_" + split_tail):
                prefix = lower[:-len(split_tail)].rstrip("_")
                return {"protocol": "axi4", "interface": prefix or "axi",
                        "channel": channel.upper(), "logical_signal": field,
                        "confidence": "name_inference"}
    if re.search(r"(?:^|_)axis_?t(?:data|valid|ready|last|user|keep|strb)$", lower):
        return {"protocol": "axi_stream", "interface": lower.split("_t")[0],
                "channel": "STREAM", "logical_signal": lower,
                "confidence": "name_inference"}
    m = re.fullmatch(r"(.*?)(?:_)?(req|rsp|ready|valid)$", lower)
    if m and m.group(1):
        return {"protocol": "generic", "interface": m.group(1),
                "channel": "HANDSHAKE", "logical_signal": m.group(2),
                "confidence": "name_inference"}
    return {"protocol": "discrete", "interface": lower, "channel": "OTHER",
            "logical_signal": lower, "confidence": "unclassified"}


def source_ports(source: Path, root: Path) -> list[dict]:
    """Read the deliberately simple generated ANSI header, not arbitrary SV."""
    data = source.read_text().splitlines()
    inside = False
    found = []
    for number, line in enumerate(data, 1):
        if not inside:
            if re.search(r"^\s*module\s+[A-Za-z_][A-Za-z_0-9]*\s*\(", line):
                inside = True
            continue
        if line.strip() == ");":
            break
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        match = HEADER.fullmatch(line)
        if not match:
            raise ValueError(f"unsupported generated ANSI port declaration at {source}:{number}: {line[:100]}")
        direction, high, low, name = match.groups()
        width = abs(int(high) - int(low)) + 1 if high is not None else 1
        found.append({"name": name, "direction": direction, "width": width,
                      "location": source.relative_to(root).as_posix() + f":{number}:1",
                      "evidence": "generated_rtl_port_declaration"})
    if not inside or not found:
        raise ValueError(f"no generated port declarations found in {source}")
    return found


def report_ports(rows: list[dict]) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError("slang-report ports must be a JSON list")
    ports = []
    for item in rows:
        if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                or not isinstance(item.get("width"), int)
                or item["width"] <= 0
                or item.get("direction") not in ("In", "Out", "InOut")):
            raise ValueError("unexpected slang-report port entry")
        ports.append({"name": item["name"],
                      "direction": {"In": "input", "Out": "output", "InOut": "inout"}[item["direction"]],
                      "width": item["width"], "location": item.get("location", ""),
                      "evidence": "elaborated_slang_report_port"})
    return ports


def alias_match(name: str, aliases: list[tuple[str, str]]) -> tuple[str, str, str]:
    for prefix, original in aliases:
        for role in ("m", "s"):
            marker = role + "_" + prefix + "_"
            if name.startswith(marker):
                return original, name[len(marker):], role
    return "", name, ""


def build(root: Path = ROOT, *, slang_ports: Path | None = None,
          bus_top: Path | None = None, topology: Path | None = None) -> dict:
    root = root.resolve()
    graph_path = topology or root / "gen/diagrams/noc-topology.json"
    graph = json.loads(graph_path.read_text())
    if graph.get("schema_version") != 1:
        raise ValueError("unsupported declared topology schema")
    names = [node["name"] for node in graph["instances"]]
    if len(set(names)) != len(names):
        raise ValueError("duplicate endpoint names in topology")
    aliases = sorted(((name.replace(".", "_"), name) for name in names),
                     key=lambda entry: (-len(entry[0]), entry[0]))
    source = bus_top or root / "gen/supernoc/soc_noc.sv"
    if slang_ports:
        raw = json.loads(slang_ports.read_text())
        ports = report_ports(raw)
        source_kind = "elaborated_slang_report"
    else:
        ports = source_ports(source, root)
        source_kind = "generated_rtl_declarations"
    # Automatically match generated flattened ports to graph endpoints by the
    # longest full endpoint identity. Never hardcode compute/memory/PCIe.
    endpoints: dict[str, dict] = {}
    unbound = []
    for port in ports:
        endpoint, signal, role = alias_match(port["name"], aliases)
        if not endpoint and slang_ports and "." in port["name"]:
            # A future unfamiliar module type still appears by its *actual*
            # elaborated instance path, not by a guessed generated alias.
            endpoint, signal = port["name"].rsplit(".", 1)
        group = infer_protocol(signal)
        row = {**port, **group, "logical_name": signal, "flattened_role": role}
        if endpoint:
            ep = endpoints.setdefault(endpoint, {"name": endpoint, "protocols": {},
                                                    "signals": []})
            ep["signals"].append(row)
            key = group["protocol"] + ":" + group["interface"]
            logical = ep["protocols"].setdefault(key, {
                "protocol": group["protocol"], "interface": group["interface"],
                "channels": {}})
            logical["channels"].setdefault(group["channel"], []).append(row)
        else:
            unbound.append(row)
    for ep in endpoints.values():
        ep["signals"].sort(key=lambda p:p["name"])
        for group in ep["protocols"].values():
            for members in group["channels"].values():
                members.sort(key=lambda p:p["name"])

    actual_links = []
    for edge in graph["connections"]:
        a, b = edge["from"]["instance"], edge["to"]["instance"]
        if a not in names or b not in names:
            raise ValueError(f"unknown declared connection {a} -> {b}")
        signals = edge.get("signals", [])
        # The high-level generator uses AXI4 or Floo request+response summary
        # signals. They are NOT the exact physical wires or bit-level paths.
        actual_links.append({
            "id": edge.get("id"), "from": edge["from"], "to": edge["to"],
            "link_type": edge.get("type", ""), "status": edge.get("status", ""),
            "declared_signals": signals,
            "source_port_names": [p["name"] for p in endpoints.get(a, {}).get("signals", [])],
            "target_port_names": [p["name"] for p in endpoints.get(b, {}).get("signals", [])],
            "connection_evidence": "generator_declared_not_slang_traced"
        })
    return {"schema_version": 1,
            "source": source_kind,
            "limits": {"physical_port_declarations": True, "bit_level_wiring_proven": False,
                       "unnamed_generate_routes_inferred": False},
            "counts": {"ports": len(ports), "mapped": sum(len(x["signals"]) for x in endpoints.values()),
                       "unbound": len(unbound), "endpoints": len(endpoints)},
            "endpoints": endpoints, "unbound_ports": unbound,
            "declared_connections": actual_links}


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--slang-ports", type=Path, help="slang-report --ports --format json")
    cli.add_argument("--output", type=Path)
    options = cli.parse_args()
    data = build(options.root, slang_ports=options.slang_ports)
    text = json.dumps(data, indent=2) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
