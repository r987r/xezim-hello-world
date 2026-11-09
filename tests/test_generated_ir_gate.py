"""#165/#166 generator-consumer gate rejects inconsistent emitted topology."""
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
import generate


class GeneratorIRConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.topology = json.loads((ROOT / "gen/diagrams/noc-topology.json").read_text())

    def write_topology(self, directory, data):
        path = Path(directory) / "diagrams/noc-topology.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(data))
        return path

    def test_existing_real_default_generated_graph_agrees_with_ip_contracts(self):
        result = generate.verify_generated_source_graph(self.cfg, ROOT / "gen")
        self.assertEqual(result["instance_count"], len(self.topology["instances"]))
        self.assertEqual(result["link_count"], len(self.topology["connections"]))
        self.assertEqual(len(result["soc_ir_sha256"]), 64)
        self.assertEqual(len(result["composition_sha256"]), 64)
        self.assertEqual(result["project"], self.cfg["name"])
        self.assertEqual(result["variant"], "default")
        self.assertEqual(result["schema_version"], 1)
        self.assertIn("not_elaborated", result["source_evidence"])

    def test_incorrect_generated_endpoint_or_missing_peripheral_is_fatal(self):
        for corruption in ("endpoint", "peripheral", "clock"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                graph = copy.deepcopy(self.topology)
                soc = copy.deepcopy(self.cfg)
                if corruption == "endpoint":
                    graph["connections"][0]["to"]["instance"] = "ghost_noc"
                elif corruption == "peripheral":
                    graph["instances"] = [
                        row for row in graph["instances"]
                        if not row["name"].startswith("pcie0")]
                else:
                    next(row for row in soc["subsystems"]
                         if row["name"] == "ethernet0")["clock_domain"] = "unqualified_eth"
                self.write_topology(tmp, graph)
                with self.assertRaises(ValueError):
                    generate.verify_generated_source_graph(soc, Path(tmp))

    def test_missing_topology_and_symlink_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(generate.GenerationError,
                                        "failed to emit"):
                generate.verify_generated_source_graph(self.cfg, Path(tmp))
            link = Path(tmp) / "diagrams/noc-topology.json"
            link.parent.mkdir(parents=True)
            link.symlink_to(ROOT / "gen/diagrams/noc-topology.json")
            with self.assertRaisesRegex(generate.GenerationError,
                                        "failed to emit"):
                generate.verify_generated_source_graph(self.cfg, Path(tmp))


if __name__ == "__main__":
    unittest.main()
