#!/usr/bin/env python3
"""Source-attested direct supernoc_tb ↔ soc_noc port-bit boundary contract.

This checks *elaborated static port bindings*, including clock and reset, on
the real Bender-selected supernoc RTL. It is not a proof of paths through
FlooNoC routers, transactions, timing, CDC, physical interfaces or PHY.
No source-only name match can satisfy the gate without real graph edges.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from signal_paths import enumerate_ports, read_graph

ROOT = Path(__file__).resolve().parents[1]
TOP = "supernoc_tb"
CHILD = "soc_noc"
INSTANCE = "u_noc"
SELECTED_SOURCES = ("gen/supernoc/supernoc_tb.sv", "gen/supernoc/soc_noc.sv")
DECL = re.compile(r"^\s*(input|output)\s+logic(?:\s+\[(\d+):(\d+)\])?\s+([A-Za-z_]\w*)\s*,?\s*$")
BIND = re.compile(r"^\s*\.([A-Za-z_]\w*)\(([A-Za-z_]\w*)\)\s*,?\s*$")


class SupernocConnectivityError(ValueError):
    pass


def _ports(text: str, module: str) -> dict[str, tuple[str, int]]:
    start = re.search(r"\bmodule\s+" + re.escape(module) + r"\s*\(", text)
    if not start:
        raise SupernocConnectivityError(f"missing module {module}")
    end = text.find(");", start.end())
    if end < 0:
        raise SupernocConnectivityError(f"unterminated module declaration {module}")
    result: dict[str, tuple[str, int]] = {}
    for line in text[start.end():end].splitlines():
        match = DECL.fullmatch(line.strip())
        if not match:
            raise SupernocConnectivityError(f"{module}: unsupported port declaration {line!r}")
        direction, left, right, name = match.groups()
        width = abs(int(left) - int(right)) + 1 if left is not None else 1
        if name in result or width < 1:
            raise SupernocConnectivityError(f"{module}: duplicate or empty port {name}")
        result[name] = (direction, width)
    return result


def _binding(text: str) -> dict[str, str]:
    needle = re.search(r"\bsoc_noc\s+u_noc\s*\(", text)
    if not needle:
        raise SupernocConnectivityError("supernoc_tb lacks exact soc_noc u_noc instance")
    if re.search(r"\bsoc_noc\s+u_noc\s*\(", text[needle.end():]):
        raise SupernocConnectivityError("ambiguous duplicate soc_noc instance")
    end = text.find(");", needle.end())
    if end < 0:
        raise SupernocConnectivityError("unterminated soc_noc binding")
    mapping = {}
    for line in text[needle.end():end].splitlines():
        match = BIND.fullmatch(line.strip())
        if not match:
            raise SupernocConnectivityError(f"non-direct or unsupported u_noc binding {line!r}")
        port, signal = match.groups()
        if port in mapping:
            raise SupernocConnectivityError(f"duplicate soc_noc binding {port}")
        mapping[port] = signal
    return mapping


def expected_contract(wrapper: str, core: str) -> dict[str, tuple[str, int]]:
    outer = _ports(wrapper, TOP)
    inner = _ports(core, CHILD)
    binding = _binding(wrapper)
    if set(outer) != set(inner) or set(binding) != set(inner):
        raise SupernocConnectivityError("supernoc wrapper and core full port inventories diverge")
    if len(outer) < 500:
        raise SupernocConnectivityError("incomplete supernoc source port inventory")
    for pin, (direction, width) in inner.items():
        if binding[pin] != pin or outer[pin] != (direction, width):
            raise SupernocConnectivityError(f"{pin}: RTL binding direction/width/name mismatch")
    for pin in ("clk_i", "rst_ni",
                "m_compute0_local_data_cpu_awid",
                "m_ethernet0_local_data_packet_dma_awvalid",
                "m_pcie0_local_data_host_awvalid",
                "s_memory0_local_data_target_crossbar_awvalid"):
        if pin not in outer:
            raise SupernocConnectivityError(f"missing required real NoC boundary {pin}")
    return outer


def _bits(node: dict, label: str) -> set[int]:
    bounds = node.get("bounds")
    if (not isinstance(bounds, list) or len(bounds) != 2
            or any(type(bit) is not int or bit < 0 for bit in bounds)):
        raise SupernocConnectivityError(f"{label}: invalid elaborated bit bounds")
    return set(range(min(bounds), max(bounds) + 1))


def _group(port_nodes: dict[str, list[dict]], path: str, width: int) -> list[dict]:
    group = port_nodes.get(path)
    if not group:
        raise SupernocConnectivityError(f"missing elaborated supernoc port {path}")
    observed = set().union(*(_bits(node, path) for node in group))
    expected = set(range(width))
    if observed != expected:
        raise SupernocConnectivityError(f"{path}: wrong elaborated port width "
                                        f"(missing {sorted(expected-observed)[:8]}, "
                                        f"extra {sorted(observed-expected)[:8]})")
    return group


def audit(netlist: Path, meta_file: Path, root: Path = ROOT) -> dict:
    root = root.resolve()
    metadata = json.loads(meta_file.read_text())
    hashes = metadata.get("selected_source_sha256")
    if (metadata.get("profile") != "supernoc" or metadata.get("top") != TOP
            or metadata.get("mode") != "netlist"
            or metadata.get("evidence") != "elaborated_slang_netlist_inputs_attested"
            or not isinstance(metadata.get("plan_sha256"), str)
            or len(metadata["plan_sha256"]) != 64
            or not isinstance(hashes, dict)):
        raise SupernocConnectivityError("foreign/unsigned supernoc selected RTL export")
    for path in SELECTED_SOURCES:
        file = root / path
        if not file.is_file() or hashes.get(path) != hashlib.sha256(file.read_bytes()).hexdigest():
            raise SupernocConnectivityError(f"{path}: unselected/changed source")
    actual_hash = hashlib.sha256(netlist.read_bytes()).hexdigest()
    if metadata.get("output_sha256") != actual_hash:
        raise SupernocConnectivityError("real supernoc netlist byte hash mismatch")
    expected = expected_contract((root / SELECTED_SOURCES[0]).read_text(),
                                 (root / SELECTED_SOURCES[1]).read_text())
    _, nodes, adjacency = read_graph(netlist)
    ports = {}
    for port in enumerate_ports(nodes):
        ports.setdefault(port["path"], []).append(port)
    results = []
    for pin, (direction, width) in expected.items():
        top_path = f"{TOP}.{pin}"
        inner_path = f"{TOP}.{INSTANCE}.{pin}"
        outer = _group(ports, top_path, width)
        inner = _group(ports, inner_path, width)
        if direction == "input":
            source, sink = outer, inner
        else:
            source, sink = inner, outer
        # Direction is the module's port direction. At an input-to-input
        # wrapper boundary both ends are 'In' in the elaboration.
        actual_direction = "In" if direction == "input" else "Out"
        if any(p["direction"] != actual_direction for p in outer + inner):
            raise SupernocConnectivityError(f"{pin}: actual port direction mismatch")
        targets = {p["id"]: p for p in sink}
        reached: dict[int, set[int]] = {p["id"]: set() for p in sink}
        proof = set()
        for src in source:
            required = _bits(src, pin)
            observed = set()
            for edge in adjacency[src["id"]]:
                dst = targets.get(edge["target"])
                if dst is None:
                    continue
                edge_bits = _bits(edge, pin + ".edge")
                if not edge_bits <= required or not edge_bits <= _bits(dst, pin):
                    raise SupernocConnectivityError(f"{pin}: misrouted/oversized elaborated bit edge")
                observed.update(edge_bits)
                reached[dst["id"]].update(edge_bits)
                proof.add((src["id"], dst["id"], min(edge_bits), max(edge_bits)))
            if observed != required:
                raise SupernocConnectivityError(
                    f"{pin}: source node {src['id']} has missing directed bits "
                    f"{sorted(required-observed)[:8]}")
        for dst in sink:
            missing = _bits(dst, pin) - reached[dst["id"]]
            if missing:
                raise SupernocConnectivityError(
                    f"{pin}: destination replica {dst['id']} missing bits {sorted(missing)[:8]}")
        results.append({"port": pin, "direction": direction, "width": width,
                        "from": top_path if direction == "input" else inner_path,
                        "to": inner_path if direction == "input" else top_path,
                        "source_nodes": [p["id"] for p in source],
                        "sink_nodes": [p["id"] for p in sink],
                        "directed_bit_witnesses": [list(p) for p in sorted(proof)]})
    return {
        "schema_version": 1,
        "source_profile": "supernoc",
        "selected_plan_sha256": metadata["plan_sha256"],
        "selected_source_sha256": {p: hashes[p] for p in SELECTED_SOURCES},
        "netlist_sha256": actual_hash,
        "checked_ports": len(results),
        "checked_port_bits": sum(r["width"] for r in results),
        "clk_rst_wiring_checked": True,
        "ethernet_and_pcie_reserved_boundary_wiring_checked": True,
        "evidence": "compiler_elaborated_direct_supernoc_wrapper_to_soc_noc_port_bindings",
        "runtime_transactions_checked": False,
        "floo_internal_routes_checked": False,
        "real_packet_engine_attachment_checked": False,
        "checks": results,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--netlist", required=True, type=Path)
    cli.add_argument("--meta", required=True, type=Path)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    result = audit(args.netlist, args.meta, args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"CONNECT: {result['checked_ports']} supernoc-boundary ports / "
          f"{result['checked_port_bits']} port bits with real directed edge proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
