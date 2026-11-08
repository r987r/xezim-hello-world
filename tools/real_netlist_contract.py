"""Qualify a real selected memory RTL netlist, not a synthetic fixture.

This is the first narrowly scoped elaborated AXI port-path gate. Other NoC,
Ethernet, PCIe and DDR variants require their own source-selected closures.
An elaborated static dependency is not protocol or transfer acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from signal_paths import read_graph, enumerate_ports


class ConnectivityEvidenceError(ValueError):
    pass


# Select exact unambiguous elaborated port suffixes under the real checked-in
# generated crossbar testbench. Never use a fabricated node/path fallback.
PAIRS = (
    # Fully named generate instance 0, never an ambiguous suffix shared
    # by the two configured initiators and two downstream memory targets.
    ("master_awvalid", ".masters[0].u_agent.awvalid", ".fabric.s_axi_awvalid", "aw"),
    ("master_wvalid", ".masters[0].u_agent.wvalid", ".fabric.s_axi_wvalid", "w"),
    ("master_bready", ".masters[0].u_agent.bready", ".fabric.s_axi_bready", "b"),
    ("master_arvalid", ".masters[0].u_agent.arvalid", ".fabric.s_axi_arvalid", "ar"),
    ("master_rready", ".masters[0].u_agent.rready", ".fabric.s_axi_rready", "r"),
    ("memory_awvalid", ".fabric.m_axi_awvalid", ".memories[0].u_mem.s_axi_awvalid", "aw"),
    ("memory_wvalid", ".fabric.m_axi_wvalid", ".memories[0].u_mem.s_axi_wvalid", "w"),
    ("memory_bready", ".fabric.m_axi_bready", ".memories[0].u_mem.s_axi_bready", "b"),
    ("memory_arvalid", ".fabric.m_axi_arvalid", ".memories[0].u_mem.s_axi_arvalid", "ar"),
    ("memory_rready", ".fabric.m_axi_rready", ".memories[0].u_mem.s_axi_rready", "r"),
)


def audit(netlist: Path, *, selected_meta: Path, source_profile: str = "memory") -> dict:
    meta = json.loads(selected_meta.read_text())
    if (meta.get("profile") != source_profile or meta.get("top") != "memory_tb"
            or meta.get("mode") != "netlist"
            or meta.get("evidence") != "elaborated_slang_netlist_inputs_attested"
            or not isinstance(meta.get("selected_source_sha256"), dict)
            or not meta["selected_source_sha256"]):
        raise ConnectivityEvidenceError("missing selected RTL netlist export provenance")
    actual_netlist_sha = hashlib.sha256(netlist.read_bytes()).hexdigest()
    if meta.get("output_sha256") != actual_netlist_sha:
        raise ConnectivityEvidenceError("original exported netlist hash mismatch")
    data, nodes, adjacency = read_graph(netlist)
    ports = enumerate_ports(nodes)
    if len(ports) < 8:
        raise ConnectivityEvidenceError("real elaborated design exposes too few ports")

    def selected_port(suffix):
        matches = {p["path"] for p in ports if p["path"].endswith(suffix)}
        if len(matches) != 1:
            raise ConnectivityEvidenceError(
                f"nonunique/missing selected RTL port suffix {suffix}: {len(matches)}")
        path = next(iter(matches))
        return path, [p for p in ports if p["path"] == path]

    def covers(port, bit):
        lo, hi = port["bounds"]
        return min(lo, hi) <= bit <= max(lo, hi)

    checks = []
    for name, source_suffix, destination_suffix, channel in PAIRS:
        src_path, src_nodes = selected_port(source_suffix)
        dst_path, dst_nodes = selected_port(destination_suffix)
        # Real memory_tb fans two masters/targets into packed crossbar
        # arrays. This first acceptance gate checks lane 0 only. Every
        # duplicate source node for that lane must contribute a real edge.
        bit = 0
        source_lane = [p for p in src_nodes if covers(p, bit)]
        dest_lane = [p for p in dst_nodes if covers(p, bit)]
        if not source_lane or not dest_lane:
            raise ConnectivityEvidenceError(f"{name}: missing selected AXI bit {bit}")
        if any(p["direction"] != "Out" for p in source_lane):
            raise ConnectivityEvidenceError(f"{name}: source is not an output port")
        if any(p["direction"] != "In" for p in dest_lane):
            raise ConnectivityEvidenceError(f"{name}: sink is not an input port")
        sink_ids = {p["id"] for p in dest_lane}
        witness = []
        for src in source_lane:
            exact = [
                e for e in adjacency[src["id"]]
                if e["target"] in sink_ids
                and isinstance(e.get("bounds"), list) and len(e["bounds"]) == 2
                and all(type(v) is int for v in e["bounds"])
                and min(e["bounds"]) <= bit <= max(e["bounds"])
            ]
            if not exact:
                raise ConnectivityEvidenceError(
                    f"{name}: no directed elaborated AXI lane {bit} edge "
                    f"for source node {src['id']}")
            witness.extend((src["id"], e["target"]) for e in exact)
        checks.append({
            "name": name, "channel": channel, "source": src_path,
            "destination": dst_path, "selected_bit": bit,
            "source_nodes": [p["id"] for p in source_lane],
            "destination_nodes": [p["id"] for p in dest_lane],
            "directed_bit_edges": [list(edge) for edge in sorted(set(witness))],
            "all_source_replicas_connected": True,
            "static_dependency_found": True,
        })
    return {"schema_version": 1, "profile": source_profile,
            "netlist_sha256": actual_netlist_sha,
            "selected_plan_sha256": meta["plan_sha256"],
            "selected_source_sha256": meta["selected_source_sha256"],
            "evidence": "actual_elaborated_static_axi_lane0_directed_edges_only",
            "runtime_axi_accepted": False, "checks": checks}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--netlist", required=True, type=Path)
    cli.add_argument("--meta", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    result = audit(args.netlist, selected_meta=args.meta)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"CONNECT: {len(result['checks'])} real selected memory AXI static paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
