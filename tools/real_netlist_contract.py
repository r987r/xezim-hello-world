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

from signal_paths import read_graph, enumerate_ports, trace


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
    ("memory_bready", ".memories[0].u_mem.s_axi_bready", ".fabric.m_axi_bready", "b"),
    ("memory_arvalid", ".fabric.m_axi_arvalid", ".memories[0].u_mem.s_axi_arvalid", "ar"),
    ("memory_rready", ".memories[0].u_mem.s_axi_rready", ".fabric.m_axi_rready", "r"),
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
    _, nodes, _ = read_graph(netlist)
    ports = enumerate_ports(nodes)
    if len(ports) < 8:
        raise ConnectivityEvidenceError("real elaborated design exposes too few ports")
    # Keep the list of *all* matching port nodes, including duplicates across
    # generated bank instances: proof is per selected exact hierarchy pair.
    def unique(suffix):
        found = [p for p in ports if str(p["path"]).endswith(suffix)]
        if len(found) != 1:
            raise ConnectivityEvidenceError(
                f"nonunique/missing selected RTL port suffix {suffix}: {len(found)}")
        return found[0]

    checks = []
    for name, source_suffix, destination_suffix, channel in PAIRS:
        src, dst = unique(source_suffix), unique(destination_suffix)
        if str(src["direction"]).lower() not in ("out", "output"):
            raise ConnectivityEvidenceError(f"{name}: source is not an output port")
        if str(dst["direction"]).lower() not in ("in", "input"):
            raise ConnectivityEvidenceError(f"{name}: sink is not an input port")
        if not src["bounds"] or not dst["bounds"]:
            raise ConnectivityEvidenceError(f"{name}: missing elaborated bit bounds")
        proof = trace(netlist, src["path"], dst["path"], max_depth=64)
        if not proof["found"]:
            raise ConnectivityEvidenceError(
                f"{name}: no elaborated static dependency between ports")
        checks.append({"name": name, "channel": channel, "source": src["path"],
                       "destination": dst["path"], "source_bounds": src["bounds"],
                       "destination_bounds": dst["bounds"],
                       "static_dependency_found": True,
                       "steps": len(proof["steps"])})
    return {"schema_version": 1, "profile": source_profile,
            "netlist_sha256": actual_netlist_sha,
            "selected_plan_sha256": meta["plan_sha256"],
            "selected_source_sha256": meta["selected_source_sha256"],
            "evidence": "actual_elaborated_static_axichannel_dependency_only",
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
