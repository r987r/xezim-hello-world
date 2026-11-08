#!/usr/bin/env python3
"""Mutate a real compiled SuperNoC graph without altering canonical evidence.

Mandatory negative qualification: selectively remove a compiler edge for
clock, reset, CPU data and reserved Ethernet/PCIe boundaries. Rehash each
mutated artifact; the verifier must reject *wiring*, not only hash mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from supernoc_netlist_contract import audit, SupernocConnectivityError

TEST_PORTS = (
    "clk_i", "rst_ni", "m_compute0_local_data_cpu_awid",
    "m_ethernet0_local_data_packet_dma_awvalid",
    "m_pcie0_local_data_host_awvalid",
)


def check(netlist: Path, meta: Path, root: Path) -> dict:
    original = audit(netlist, meta, root)
    checks = {p["port"]: p for p in original["checks"]}
    original_graph = json.loads(netlist.read_text())
    original_meta = json.loads(meta.read_text())
    outputs = []
    with TemporaryDirectory() as td:
        work = Path(td)
        out = work / "tampered.json"
        out_meta = work / "tampered.json.meta.json"
        for port in TEST_PORTS:
            if port not in checks:
                raise SupernocConnectivityError(f"missing required negative proof port {port}")
            evidence = checks[port]
            if not evidence["directed_bit_witnesses"]:
                raise SupernocConnectivityError(f"{port}: no positive real RTL witness")
            src, dst, _, _ = evidence["directed_bit_witnesses"][0]
            graph = json.loads(json.dumps(original_graph))
            # Remove ALL directed edges between the chosen original
            # src/sink nodes. Never change declared source hierarchy.
            graph["edges"] = [
                e for e in graph["edges"]
                if not (e.get("source") == src and e.get("target") == dst)
            ]
            if len(graph["edges"]) == len(original_graph["edges"]):
                raise SupernocConnectivityError(f"{port}: no original edge to mutate")
            out.write_text(json.dumps(graph))
            info = dict(original_meta)
            info["output_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
            out_meta.write_text(json.dumps(info))
            try:
                audit(out, out_meta, root)
            except SupernocConnectivityError as exc:
                if "missing directed bits" not in str(exc) and "missing bits" not in str(exc):
                    raise SupernocConnectivityError(
                        f"{port}: rejected for wrong reason: {exc}") from exc
                outputs.append({"port": port, "result": "broken_real_port_edge_rejected"})
            else:
                raise SupernocConnectivityError(
                    f"{port}: missing real compiler edge falsely accepted")
    return {"schema_version": 1,
            "original_real_netlist_sha256": original["netlist_sha256"],
            "all_mutations_rejected": True, "checks": outputs}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--netlist", required=True, type=Path)
    cli.add_argument("--meta", required=True, type=Path)
    cli.add_argument("--root", default=Path(__file__).resolve().parents[1], type=Path)
    cli.add_argument("--out", required=True, type=Path)
    opts = cli.parse_args()
    report = check(opts.netlist, opts.meta, opts.root)
    opts.out.parent.mkdir(parents=True, exist_ok=True)
    opts.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(f"CONNECT NEGATIVE: {len(report['checks'])} real SuperNoC broken wires rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
