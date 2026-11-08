"""Real-netlist proof gate must reject false or altered source/path claims.

Fixture tests qualify the validator only. The CI job separately builds the
upstream source-pinned exporter and runs on a Bender-resolved real RTL profile.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import real_netlist_contract as rc


class RealNetlistContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.netlist = self.dir / "netlist.json"
        self.meta = self.dir / "netlist.json.meta.json"
        self.meta.write_text(json.dumps({
            "profile": "memory", "top": "memory_tb", "mode": "netlist",
            "evidence": "elaborated_slang_netlist_inputs_attested",
            "plan_sha256": "a" * 64,
            "selected_source_sha256": {"gen/memory/memory_tb.sv": "b" * 64},
        }))
        data = {"version": 3, "fileTable": ["gen/memory/memory_tb.sv"],
                "nodes": [], "edges": []}
        self.endpoints = []
        for i, (_, src, dst, channel) in enumerate(rc.PAIRS):
            left, right = 3 * i + 1, 3 * i + 3
            data["nodes"].extend([
                {"id": left, "kind": "Port",
                 "path": "memory_tb" + src, "direction": "Out",
                 "bounds": [0, 0]},
                {"id": left + 1, "kind": "Assignment",
                 "path": "memory_tb.link_%d" % i},
                {"id": right, "kind": "Port",
                 "path": "memory_tb" + dst, "direction": "In",
                 "bounds": [0, 0]},
            ])
            data["edges"].extend([
                {"source": left, "target": left+1},
                {"source": left+1, "target": right},
            ])
            self.endpoints.append((left, right))
        # In actual exported graphs the same fabric port serves multiple
        # source pairs; de-duplicate identical path nodes across this fixture.
        unique = {}
        aliases = {}
        for node in data["nodes"]:
            path = node.get("path")
            if node["kind"] == "Port" and path in unique:
                aliases[node["id"]] = unique[path]
            else:
                unique[path] = node["id"]
        data["nodes"] = [n for n in data["nodes"] if n["id"] not in aliases]
        for edge in data["edges"]:
            edge["source"] = aliases.get(edge["source"], edge["source"])
            edge["target"] = aliases.get(edge["target"], edge["target"])
        self.graph = data
        self.save()

    def save(self):
        self.netlist.write_text(json.dumps(self.graph))

    def test_actual_schema_validator_requires_all_channel_paths(self):
        result = rc.audit(self.netlist, selected_meta=self.meta)
        self.assertEqual(len(result["checks"]), len(rc.PAIRS))
        self.assertFalse(result["runtime_axi_accepted"])
        self.assertEqual(result["evidence"],
                         "actual_elaborated_static_axichannel_dependency_only")

    def test_broken_wire_wrong_direction_and_missing_endpoint_rejected(self):
        original = list(self.graph["edges"])
        self.graph["edges"] = original[1:]
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "no elaborated"):
            rc.audit(self.netlist, selected_meta=self.meta)
        self.graph["edges"] = original
        self.graph["nodes"][0]["direction"] = "In"
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "not an output"):
            rc.audit(self.netlist, selected_meta=self.meta)
        self.graph["nodes"][0]["direction"] = "Out"
        self.graph["nodes"][0]["path"] = "wrong.path"
        self.save()
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "missing"):
            rc.audit(self.netlist, selected_meta=self.meta)

    def test_wrong_source_and_unrecognized_export_evidence_rejected(self):
        meta = json.loads(self.meta.read_text())
        meta["profile"] = "supernoc"
        self.meta.write_text(json.dumps(meta))
        with self.assertRaisesRegex(rc.ConnectivityEvidenceError, "provenance"):
            rc.audit(self.netlist, selected_meta=self.meta)


if __name__ == "__main__":
    unittest.main()
