#!/usr/bin/env python3
"""Generic selected SoC RTL direct-port proof using the existing memory checker.

This extends #46 beyond the fixed memory_tb field list. A contract records
explicit elaborated Port paths, direction, widths and original compiled input
SHA. The checker uses the SAME real-netlist Port/edge coverage algorithm as
real_netlist_contract.py, not name similarity or drawn graph edges.

A verified connection is one direct binding only: it cannot prove a routed
NoC transaction, CDC safety, silicon physical DDR, or passive traffic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from real_netlist_contract import Link, _prove_link, ConnectivityEvidenceError
from signal_paths import read_graph, enumerate_ports
from selected_rtl_provenance import selected

ROOT = Path(__file__).resolve().parents[1]
HEXDIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _strict_links(contract: dict) -> list[Link]:
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        raise ConnectivityEvidenceError("invalid SoC direct-port contract schema")
    declarations = contract.get("links")
    if not isinstance(declarations, list) or not declarations or len(declarations) > 2000:
        raise ConnectivityEvidenceError("missing/oversized SoC port contract")
    names: set[str] = set()
    endpoints: set[tuple[str, str]] = set()
    rows = []
    for entry in declarations:
        if not isinstance(entry, dict) or set(entry) != {
                "name", "source", "destination", "width", "protocol"}:
            raise ConnectivityEvidenceError("malformed SoC direct port declaration")
        name, start, end = entry["name"], entry["source"], entry["destination"]
        width, protocol = entry["width"], entry["protocol"]
        if (not all(isinstance(x, str) and x and len(x) < 256
                    for x in (name, start, end, protocol))
                or type(width) is not int or not 1 <= width <= 4096
                or start == end or name in names or (start, end) in endpoints):
            raise ConnectivityEvidenceError("ambiguous/invalid SoC direct port identity")
        names.add(name)
        endpoints.add((start, end))
        # One direct point-to-point bus: index0, no implicit rewrites or
        # truncation permitted. Original netlist Port IDs carry bit bounds.
        rows.append(Link(name, protocol, "full", "selected_soc", 0,
                         start, end, False, width, width, 1))
    return rows


def audit(root: Path, profile: str, *, netlist: Path, meta: Path,
          contract_path: Path) -> dict:
    root = root.resolve()
    selection = selected(root, profile)
    if selection["top"] not in ("full_chip_tb", "full_chip_dma_tb"):
        raise ConnectivityEvidenceError("SoC direct port proof requires full-chip selected top")
    metadata = json.loads(meta.read_text())
    data = netlist.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if (metadata.get("profile") != profile
            or metadata.get("top") != selection["top"]
            or metadata.get("mode") != "netlist"
            or metadata.get("evidence") != "elaborated_slang_netlist_inputs_attested"
            or metadata.get("output_sha256") != actual
            or metadata.get("filelist_sha256") != selection["filelist_sha256"]
            or metadata.get("plan_sha256") != selection["plan_sha256"]
            or metadata.get("selected_source_sha256") != selection["selected_source_sha256"]):
        raise ConnectivityEvidenceError("foreign/stale SoC netlist selected-source evidence")
    spec_raw = contract_path.read_bytes()
    spec = json.loads(spec_raw)
    if (spec.get("profile") != profile
            or spec.get("compiled_top") != selection["top"]
            or spec.get("filelist_sha256") != selection["filelist_sha256"]):
        raise ConnectivityEvidenceError("SoC port contract does not bind exact compiled variant")
    declarations = _strict_links(spec)
    _, nodes, directed = read_graph(netlist)
    ports = {}
    for port in enumerate_ports(nodes):
        ports.setdefault(port["path"], []).append(port)
    proofs = [_prove_link(link, ports, directed) for link in declarations]
    return {
        "schema_version": 1,
        "profile": profile,
        "top": selection["top"],
        "selected_plan_sha256": selection["plan_sha256"],
        "selected_filelist_sha256": selection["filelist_sha256"],
        "netlist_sha256": actual,
        "contract_sha256": hashlib.sha256(spec_raw).hexdigest(),
        "verified_direct_port_bindings": len(proofs),
        "verified_direct_bit_positions": sum(x["connected_bit_count"] for x in proofs),
        "evidence": "real_elaborated_selected_soc_direct_port_bits_only",
        "noc_routed_traffic_observed": False,
        "cdc_qualified": False,
        "checks": proofs,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--profile", required=True)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--netlist", required=True, type=Path)
    cli.add_argument("--meta", required=True, type=Path)
    cli.add_argument("--contract", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    result = audit(args.root, args.profile, netlist=args.netlist,
                   meta=args.meta, contract_path=args.contract)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"SOC BIT CONTRACT: {result['verified_direct_port_bindings']} direct links; "
          f"{result['verified_direct_bit_positions']} original netlist bit positions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
