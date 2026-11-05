"""Diagram-gen-compatible views of pinned FlooGen-generated router networks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import noc_diagrams


class RealNetworkDiagrams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.root = ROOT / "gen/noc/floonoc"
        cls.networks = noc_diagrams.read_generated_nocs(cls.root)

    def test_every_generated_mesh_uses_real_endpoint_coordinates(self):
        self.assertEqual(len(self.networks), 12)
        for name, n in self.networks.items():
            self.assertEqual(n["entry"]["routers"], n["width"] * n["height"])
            self.assertEqual(set(n["endpoints"]), set(n["positions"]), name)
            self.assertEqual(len(n["positions"]), n["entry"]["endpoint_count"])
        self.assertEqual(self.networks["global_data"]["entry"]["routers"], 12)
        self.assertEqual(self.networks["global_data"]["endpoints"]["compute1_sram"]["addr_range"]["base"], 0x11000000)

    def test_physical_links_are_not_confused_with_planned_soc_wiring(self):
        graph = noc_diagrams.diagram_gen_metadata(self.cfg, self.networks)
        nodes = {i["name"] for i in graph["instances"]}
        links = graph["connections"]
        self.assertTrue(all(l["from"]["instance"] in nodes and l["to"]["instance"] in nodes for l in links))
        physical = [l for l in links if l["status"] == "generated_structural"]
        planned = [l for l in links if l["status"] == "planned_integration"]
        wired = [l for l in links if l["status"] == "wired_boot_configuration"]
        self.assertTrue(physical)
        self.assertTrue(planned)
        self.assertTrue(all(l["from"]["instance"].split(".")[0] ==
                            l["to"]["instance"].split(".")[0] for l in physical))
        self.assertTrue(any("compute1_sram" in l["from"]["instance"] for l in wired))
        for block in ("compute0.cpu", "compute0.dma", "compute0.sram",
                      "compute1.cpu", "compute1.dma", "compute1.sram",
                      "memory0.ctrl", "memory0.internal_target_crossbar"):
            self.assertIn(block, nodes)
        self.assertTrue(any(l["from"]["instance"] == "compute0.cpu" for l in wired))
        self.assertTrue(any(l["to"]["instance"] == "memory0.ctrl" for l in planned))
        self.assertIn("groups", graph)
        self.assertEqual(len([g for g in graph["groups"] if g["name"] in self.networks]), 12)

    def test_render_diagrams_and_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            graph, diagrams = noc_diagrams.render(self.cfg, self.root, out)
            self.assertIn("noc-hierarchy", diagrams)
            self.assertEqual(set(diagrams), {"noc-hierarchy"})
            self.assertEqual(len(diagrams), 1)
            self.assertIn("compute0", diagrams["noc-hierarchy"])
            self.assertIn("global_config", diagrams["noc-hierarchy"])
            self.assertIn("CPU boot and optional real DMA/CSR wiring", diagrams["noc-hierarchy"])
            self.assertTrue((out/"noc-topology.json").exists())
            self.assertEqual(len(json.loads((out/"noc-topology.json").read_text())["networks"]), 12)
            self.assertFalse((out / "noc").exists())
            self.assertFalse((out / "architecture.svg").exists())
            for name in diagrams:
                self.assertTrue((out/(name+".mmd")).exists())
                tree = ElementTree.parse(out/(name+".svg"))
                self.assertEqual(tree.getroot().tag.rsplit("}",1)[-1], "svg")

if __name__ == "__main__":
    unittest.main()
