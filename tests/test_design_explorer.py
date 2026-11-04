"""Regression tests for the generic 2D design/verification graph."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import design_explorer


class ExplorerTests(unittest.TestCase):
    def test_existing_profiles_and_no_3d(self):
        graph = design_explorer.catalog(ROOT)
        self.assertEqual(graph["schema_version"], 1)
        self.assertIn("supernoc", graph["profiles"])
        self.assertIn("chip-dma", graph["profiles"])
        self.assertIn("chip-boot", graph["profiles"])
        self.assertTrue(graph["nodes"])
        self.assertTrue(graph["edges"])
        self.assertEqual(graph["profiles"]["supernoc"]["top"], "supernoc_tb")
        self.assertEqual(graph["profiles"]["chip-dma"]["actors"]["compute0_local_data.dma"]["kind"], "rtl_dma")
        self.assertEqual(graph["profiles"]["chip-boot"]["actors"]["compute0_local_data.dma"]["kind"], "verification_bfm")
        self.assertTrue(graph["profiles"]["chip-dma"]["monitors"])
        self.assertNotIn("position", graph["nodes"][0])
        self.assertNotIn("z", json.dumps(graph))

    def test_new_subsystem_is_generic_without_parser_changes(self):
        graph = design_explorer.catalog(ROOT)
        source = graph["nodes"][0]
        fake = copy.deepcopy(graph)
        fake["nodes"].append({"id": "ethernet47.tx", "module": "unexpected_eth_ip",
                              "kind": "rtl_or_boundary", "groups": [], "info": {}})
        fake["edges"].append({"id": "link:new", "from": {"instance": source["id"], "port": "o"},
                              "to": {"instance": "ethernet47.tx", "port": "i"},
                              "name": "New subsystem", "type": "axi_interconnect",
                              "status": "generated_structural", "signals": []})
        diff = design_explorer.difference(graph, fake)
        self.assertEqual(diff["nodes"]["added"], ["ethernet47.tx"])
        self.assertEqual(diff["edges"]["added"], ["link:new"])
        self.assertFalse(diff["nodes"]["removed"])

    def test_stable_edge_ids_ignore_input_order(self):
        graph = design_explorer.catalog(ROOT)
        self.assertEqual(len({edge["id"] for edge in graph["edges"]}), len(graph["edges"]))
        self.assertEqual(graph["edges"], sorted(graph["edges"], key=lambda e: e["id"]))

    def test_external_verification_report_is_static_not_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "uvm.json"
            report.write_text('{"classes": [{"name": "axi_driver"}]}')
            graph = design_explorer.catalog(ROOT, verification_reports={"chip-dma": report})
            ext = graph["profiles"]["chip-dma"]["static_verification"]
            self.assertEqual(ext["evidence"], "syntactic_inference_not_runtime")
            self.assertEqual(ext["report"]["classes"][0]["name"], "axi_driver")
            with self.assertRaisesRegex(ValueError, "unknown test profile"):
                design_explorer.catalog(ROOT, verification_reports={"unknown": report})

    def test_reject_unknown_generated_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gen/diagrams").mkdir(parents=True)
            (root / "config").mkdir()
            base = json.loads((ROOT / "gen/diagrams/noc-topology.json").read_text())
            base["connections"][0]["to"]["instance"] = "missing.endpoint"
            (root / "gen/diagrams/noc-topology.json").write_text(json.dumps(base))
            (root / "config/regression.yaml").write_text(
                (ROOT / "config/regression.yaml").read_text())
            with self.assertRaisesRegex(ValueError, "unknown connectivity endpoint"):
                design_explorer.catalog(root)

    def test_catches_bad_actor_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gen/diagrams").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "gen/chip").mkdir(parents=True)
            (root / "gen/diagrams/noc-topology.json").write_text(
                (ROOT / "gen/diagrams/noc-topology.json").read_text())
            tests = {"schema_version": 1, "tests": {
                "test-new": {"engine": "cocotb-verilator", "top": "test_new",
                             "report": {"axi": {"actors": "gen/chip/new.json"}}}}}
            (root / "config/regression.yaml").write_text(yaml.safe_dump(tests))
            (root / "gen/chip/new.json").write_text(
                '{"axi_actors":{"missing.instance":{"kind":"verification_bfm"}}}')
            with self.assertRaisesRegex(ValueError, "actors are not in generated topology"):
                design_explorer.catalog(root)


if __name__ == "__main__":
    unittest.main()
