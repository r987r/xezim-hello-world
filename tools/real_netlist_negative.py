"""Run mandatory negative mutations on the *actual* Slang memory RTL export.

Do not promote fixture-only negative checks to source-attested evidence.
Never edit the canonical netlist or its original metadata in place.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from real_netlist_contract import ConnectivityEvidenceError, audit, links


def check_mutations(netlist: Path, meta: Path, manifest: Path) -> dict:
    graph = json.loads(netlist.read_text())
    header = json.loads(meta.read_text())
    m = json.loads(manifest.read_text())
    nodes = {node["id"]: node for node in graph["nodes"]}
    cases = (
        ("broken_high_data_bit", "ingress1.wdata", "missing directed bit"),
        ("swapped_id_lane", "target1.awid", "misrouted/oversized edge"),
        ("disabled_ready_edge", "target1.bready", "missing directed bit"),
    )
    checked = []
    with TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "modified-netlist.json"
        metadata = tmp / "modified-netlist.json.meta.json"
        for case, link_name, expected_error in cases:
            variant = copy.deepcopy(graph)
            link = next(item for item in links(m) if item.name == link_name)
            by_id = {node["id"]: node for node in variant["nodes"]}
            target_ids = {node["id"] for node in variant["nodes"]
                          if node.get("kind") == "Port" and node.get("path") == link.destination}
            edge = next((edge for edge in variant["edges"]
                         if not edge.get("disabled")
                         and edge["target"] in target_ids
                         and by_id[edge["source"]].get("path") == link.source
                         and min(edge.get("bounds", [])) <= link.packed_slice[1]
                         <= max(edge.get("bounds", []))), None)
            if edge is None:
                raise ConnectivityEvidenceError(f"{case}: no original real RTL edge to mutate")
            if case == "broken_high_data_bit":
                edge["bounds"][1] -= 1
            elif case == "swapped_id_lane":
                edge["bounds"] = [0, link.local_width - 1]
            elif case == "disabled_ready_edge":
                edge["disabled"] = True
            out.write_text(json.dumps(variant))
            info = dict(header)
            info["output_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
            metadata.write_text(json.dumps(info))
            try:
                audit(out, selected_meta=metadata, manifest_path=manifest)
            except ConnectivityEvidenceError as exc:
                if expected_error not in str(exc):
                    raise ConnectivityEvidenceError(
                        f"{case}: wrong failure reason {exc}") from exc
            else:
                raise ConnectivityEvidenceError(f"{case}: broken real RTL falsely PASSED")
            checked.append({"mutation": case, "result": "expected_rejection"})
    return {"schema_version": 1, "real_original_netlist_sha256":
            hashlib.sha256(netlist.read_bytes()).hexdigest(),
            "all_mutated_exports_rejected": True, "checks": checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", required=True, type=Path)
    parser.add_argument("--meta", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = check_mutations(args.netlist, args.meta, args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"CONNECT NEGATIVE: {len(result['checks'])} deliberately broken real exports rejected")


if __name__ == "__main__":
    main()
