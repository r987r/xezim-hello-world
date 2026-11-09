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

    def test_semantic_diff_reports_module_bus_and_link_status(self):
        before = design_explorer.catalog(ROOT)
        after = copy.deepcopy(before)
        node = after["nodes"][0]
        old_module = node["module"]
        node["module"] = "different_soc_ip"
        after["edges"][0]["name"] = "renamed NoC link"
        after["edges"][0]["status"] = "reserved_idle"
        after["configuration"]["buses"]["data"]["data_bits"] = 128
        diff = design_explorer.difference(before, after)
        entry = diff["semantic"]
        self.assertEqual(entry["evidence"],
                         "source_declared_only_not_elaborated_or_observed")
        self.assertEqual(entry["instances"]["changed"][node["id"]]["module"],
                         {"before": old_module, "after": "different_soc_ip"})
        self.assertEqual(len(entry["routes"]["changed"]), 1)
        self.assertFalse(entry["routes"]["added"])
        self.assertFalse(entry["routes"]["removed"])
        self.assertIn("buses", entry["soc_configuration"])
        self.assertIn("different_soc_ip", design_explorer.markdown_diff(diff))

    def test_semantic_diff_ignores_nonsemantic_order(self):
        before = design_explorer.catalog(ROOT)
        after = copy.deepcopy(before)
        after["nodes"].reverse()
        after["edges"].reverse()
        after["groups"].reverse()
        after["configuration"]["subsystems"].reverse()
        after["configuration"]["address_map"]["data"].reverse()
        # A named configuration row's position is not an SoC change.
        after["configuration"] = design_explorer.normalized_configuration(
            after["configuration"])
        review = design_explorer.semantic_difference(before, after)
        self.assertFalse(review["instances"]["changed"])
        self.assertFalse(review["routes"]["changed"])
        self.assertFalse(review["soc_configuration"])

    def test_semantic_duplicate_route_fails_closed(self):
        before = design_explorer.catalog(ROOT)
        after = copy.deepcopy(before)
        after["edges"].append({**after["edges"][0], "id": "unverified-copy"})
        with self.assertRaisesRegex(ValueError, "duplicate semantic identity"):
            design_explorer.semantic_difference(before, after)

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
        self.assertTrue(all("position" not in node for node in graph["nodes"]))

    def test_current_rtl_memory_backend_and_real_dma_actors_are_profile_accurate(self):
        graph = design_explorer.catalog(ROOT)
        nodes = {n["id"]: n for n in graph["nodes"]}
        ddr = nodes["memory0.ddr0"]["info"]["memory_integration"]
        hbm = nodes["memory0.hbm0"]["info"]["memory_integration"]
        self.assertEqual(ddr["soc_backend"], "axi_ram")
        self.assertEqual(hbm["soc_backend"], "axi_ram")
        self.assertEqual(ddr["integration"], "behavioral_axi_ram")
        self.assertNotEqual(ddr["controller_profile"], None)
        dma = "compute0_local_data.dma"
        self.assertEqual(graph["profiles"]["chip-dma"]["actors"][dma]["kind"], "rtl_dma")
        self.assertEqual(graph["profiles"]["chip-boot"]["actors"][dma]["kind"], "verification_bfm")
        self.assertEqual(graph["profiles"]["chip-cpu-dma"]["actor_catalog_status"],
                         "runtime_generated_not_available")

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

    def test_missing_runtime_manifest_is_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gen/diagrams").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "gen/diagrams/noc-topology.json").write_text(
                (ROOT / "gen/diagrams/noc-topology.json").read_text())
            tests = {"schema_version": 1, "tests": {
                "cpu-dma": {"engine": "cocotb-verilator", "top": "chip_tb",
                            "report": {"axi": {
                                "actors": ".tools/regression/cpu-dma/variant/manifest.json"}}}}}
            (root / "config/regression.yaml").write_text(yaml.safe_dump(tests))
            graph = design_explorer.catalog(root)
            entry = graph["profiles"]["cpu-dma"]
            self.assertEqual(entry["actor_catalog_status"],
                             "runtime_generated_not_available")
            self.assertEqual(entry["actors"], {})
            self.assertEqual(entry["monitors"], [])

    def test_missing_checked_in_actor_manifest_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gen/diagrams").mkdir(parents=True)
            (root / "config").mkdir()
            (root / "gen/diagrams/noc-topology.json").write_text(
                (ROOT / "gen/diagrams/noc-topology.json").read_text())
            tests = {"schema_version": 1, "tests": {
                "bad": {"engine": "cocotb-verilator", "top": "chip_tb",
                        "report": {"axi": {"actors": "gen/chip/missing.json"}}}}}
            (root / "config/regression.yaml").write_text(yaml.safe_dump(tests))
            with self.assertRaisesRegex(ValueError, "missing source"):
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
