"""#165 canonical SoC schema, source-topology agreement and fail-closed drift."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import soc_ir


class SocIRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.graph = json.loads((ROOT / "gen/diagrams/noc-topology.json").read_text())

    def test_real_generated_graph_and_bus_address_contracts(self):
        result = soc_ir.compile_ir(self.soc, self.graph)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["project"], self.soc["name"])
        self.assertEqual(result["buses"]["data"]["data_bits"], 64)
        self.assertEqual(len(result["instances"]), len(self.graph["instances"]))
        self.assertEqual(len(result["links"]), len(self.graph["connections"]))
        self.assertEqual(len(result["subsystems"]), len(self.soc["subsystems"]))
        self.assertIn("data:memory0.ddr0", {r["plane"] + ":" + r["name"]
                                          for r in result["address_map"]})
        self.assertIn("not_rtl_elaboration", result["evidence"])
        self.assertTrue(soc_ir.verify_ir(result, self.soc, self.graph))

    def test_canonical_semantics_ignore_named_row_order(self):
        original = soc_ir.compile_ir(self.soc, self.graph)
        changed = copy.deepcopy(self.soc)
        changed["subsystems"].reverse()
        changed["memory_targets"].reverse()
        changed["address_map"]["data"].reverse()
        for net in changed["networks"].values():
            if "outputs" in net:
                net["outputs"].reverse()
            if "reachable_subsystems" in net:
                net["reachable_subsystems"].reverse()
        self.assertEqual(soc_ir.compile_ir(changed, self.graph), original)

    def test_reject_dropped_link_unknown_port_or_missing_instance(self):
        for kind in ("duplicate", "missing", "foreign_port", "foreign_subsystem"):
            doc = copy.deepcopy(self.graph)
            cfg = copy.deepcopy(self.soc)
            if kind == "duplicate":
                doc["connections"].append(copy.deepcopy(doc["connections"][0]))
            if kind == "missing":
                doc["connections"][0]["to"]["instance"] = "missing_target"
            if kind == "foreign_port":
                doc["connections"][0]["from"]["port"] = ""
            if kind == "foreign_subsystem":
                cfg["subsystems"][0]["name"] = "unimplemented_soc"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                soc_ir.compile_ir(cfg, doc)

    def test_reject_source_config_change_even_when_graph_unchanged(self):
        result = soc_ir.compile_ir(self.soc, self.graph)
        changed = copy.deepcopy(self.soc)
        changed["buses"]["data"]["data_bits"] = 128
        with self.assertRaisesRegex(soc_ir.SocIRError, "differs"):
            soc_ir.verify_ir(result, changed, self.graph)

    def test_reject_address_overlap_using_existing_validator(self):
        changed = copy.deepcopy(self.soc)
        changed["address_map"]["data"][3]["base"] = changed["address_map"]["data"][2]["base"]
        with self.assertRaises(ValueError):
            soc_ir.compile_ir(changed, self.graph)

    def test_json_is_stable_and_check_rejects_tampered_snapshot(self):
        result = soc_ir.compile_ir(self.soc, self.graph)
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "soc-ir.json"
            dest.write_bytes(soc_ir.encoded(result))
            self.assertEqual(dest.read_bytes(), soc_ir.encoded(
                soc_ir.compile_ir(self.soc, self.graph)))
            tampered = json.loads(dest.read_text())
            tampered["instances"][0]["module"] = "fabricated_chip"
            with self.assertRaisesRegex(soc_ir.SocIRError, "differs"):
                soc_ir.verify_ir(tampered, self.soc, self.graph)


if __name__ == "__main__":
    unittest.main()
