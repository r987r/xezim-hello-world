"""Strict all-width memory AXI port bindings, independent of simulation PASS.

The live CI job also compiles the pinned upstream slang-netlist and mutates
its real export. Synthetic fixtures isolate contract failure modes only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import real_netlist_contract as rc


MANIFEST = {
    "ingress": 2,
    "targets": [{"name": "memory0.hbm0"}, {"name": "memory0.ddr0"}],
    "target_count": 2,
    "address_bits": 64,
    "data_bits": 64,
    "id_bits": 4,
    "backing_addr_bits": 16,
}


class MemoryAxiFullWidthTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.graph_path = root / "netlist.json"
        self.meta_path = root / "netlist.json.meta.json"
        self.manifest_path = root / "manifest.json"
        self.manifest_path.write_text(json.dumps(MANIFEST))
        self.graph = {"version": 3, "fileTable": ["gen/memory/memory_tb.sv"],
                      "nodes": [], "edges": []}
        self.path_nodes = {}
        next_id = 1
        for link in rc.links(MANIFEST):
            srcw = (link.local_width if link.source_is_local else
                    link.instance_count * link.packed_width_per_lane)
            dstw = (link.instance_count * link.packed_width_per_lane if link.source_is_local
                    else link.local_width)
            for path, width, direction in ((link.source, srcw, "Out"),
                                           (link.destination, dstw, "In")):
                if path not in self.path_nodes:
                    node = {"id": next_id, "kind": "Port", "path": path,
                            "name": path.split(".")[-1], "direction": direction,
                            "bounds": [0, width - 1],
                            "location": {"fileIndex": 0, "line": 1, "column": 1}}
                    self.graph["nodes"].append(node)
                    self.path_nodes[path] = node
                    next_id += 1
            start, stop = link.packed_slice
            self.graph["edges"].append({
                "source": self.path_nodes[link.source]["id"],
                "target": self.path_nodes[link.destination]["id"],
                "bounds": [start, stop], "disabled": False,
            })
        self.save()

    def save(self):
        data = json.dumps(self.graph)
        self.graph_path.write_text(data)
        meta = {"profile": "memory", "top": "memory_tb", "mode": "netlist",
                "evidence": "elaborated_slang_netlist_inputs_attested",
                "output_sha256": hashlib.sha256(data.encode()).hexdigest(),
                "plan_sha256": "a" * 64,
                "selected_source_sha256": {"gen/memory/memory_tb.sv": "b" * 64}}
        self.meta_path.write_text(json.dumps(meta))

    def check(self):
        return rc.audit(self.graph_path, selected_meta=self.meta_path,
                        manifest_path=self.manifest_path)

    def edge(self, linkname):
        link = next(l for l in rc.links(MANIFEST) if l.name == linkname)
        src = self.path_nodes[link.source]["id"]
        dst = self.path_nodes[link.destination]["id"]
        return next(e for e in self.graph["edges"]
                    if e["source"] == src and e["target"] == dst)

    def test_all_144_declared_field_pairs_and_1184_bit_positions(self):
        report = self.check()
        self.assertEqual(report["checked_direct_port_pairs"], 144)
        self.assertEqual(report["checked_bit_positions"], 1184)
        self.assertFalse(report["runtime_axi_accepted"])
        self.assertFalse(report["physical_ddr_phy_qualified"])
        proof = {row["name"]: row for row in report["checks"]}
        self.assertEqual(proof["ingress1.wdata"]["packed_slice"], [64, 127])
        self.assertEqual(proof["ingress1.awid"]["packed_slice"], [4, 7])
        self.assertEqual(proof["target1.awid"]["packed_slice"], [5, 9])
        self.assertEqual(proof["target1.awaddr"]["packed_slice"], [64, 79])
        self.assertIn("target1.rready", proof)
        self.assertEqual(proof["target1.rready"]["source"],
                         "memory_tb.fabric.m_axi_rready")
        self.assertEqual(proof["target1.rdata"]["source"],
                         "memory_tb.memories[1].u_mem.s_axi_rdata")

    def test_high_bit_broken_wire_fails_with_legitimate_low_bits(self):
        self.edge("ingress1.wdata")["bounds"] = [64, 126]
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "127"):
            self.check()

    def test_high_id_bit_required_on_memory_output(self):
        self.edge("target1.awid")["bounds"] = [5, 8]
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "9"):
            self.check()

    def test_swapped_lane_rejected_instead_of_counting_other_master(self):
        self.edge("ingress1.awid")["bounds"] = [0, 3]
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "misrouted"):
            self.check()

    def test_wrong_manifest_or_actual_port_width_fails_closed(self):
        wrong = dict(MANIFEST, id_bits=5)
        self.manifest_path.write_text(json.dumps(wrong))
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "width mismatch"):
            self.check()
        self.manifest_path.write_text(json.dumps(MANIFEST))
        link = next(l for l in rc.links(MANIFEST) if l.name == "ingress0.wdata")
        self.path_nodes[link.source]["bounds"] = [0, 62]
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "width mismatch"):
            self.check()

    def test_disabled_or_reversed_handshake_fails(self):
        self.edge("target1.bready")["disabled"] = True
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "target1.bready"):
            self.check()
        self.edge("target1.bready")["disabled"] = False
        link = next(l for l in rc.links(MANIFEST) if l.name == "ingress0.awready")
        self.path_nodes[link.source]["direction"] = "In"
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "non-output source"):
            self.check()

    def test_duplicate_source_and_sink_replicas_not_collapsed(self):
        link = next(l for l in rc.links(MANIFEST) if l.name == "ingress0.awvalid")
        src = self.path_nodes[link.source]
        dup = dict(src, id=9001)
        self.graph["nodes"].append(dup)
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "replica 9001"):
            self.check()
        self.graph["edges"].append({"source": 9001,
                                    "target": self.path_nodes[link.destination]["id"],
                                    "bounds": [0, 0], "disabled": False})
        self.save()
        self.assertEqual(self.check()["checked_direct_port_pairs"], 144)
        self.graph["nodes"].remove(dup)
        self.graph["edges"].pop()
        target = self.path_nodes[link.destination]
        self.graph["nodes"].append(dict(target, id=9002))
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "destination replica 9002"):
            self.check()

    def test_export_hash_rejected_even_if_all_bits_connected(self):
        self.graph_path.write_text(self.graph_path.read_text() + " ")
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "hash mismatch"):
            self.check()

    def test_malformed_manifest_and_missing_fields_fail_closed(self):
        self.manifest_path.write_text(json.dumps(dict(MANIFEST, target_count=3)))
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "target inventory"):
            self.check()
        self.manifest_path.write_text(json.dumps(MANIFEST))
        link = next(l for l in rc.links(MANIFEST) if l.name == "target1.araddr")
        self.graph["nodes"].remove(self.path_nodes[link.destination])
        self.graph["edges"] = [e for e in self.graph["edges"]
                               if e["target"] != self.path_nodes[link.destination]["id"]]
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "missing real elaborated port"):
            self.check()


if __name__ == "__main__":
    unittest.main()
