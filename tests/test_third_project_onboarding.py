"""New project onboarding must not hardcode two IDs or borrow hardware evidence."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from project_catalog import projects
from project_scaffold import create_project
from publish_site import project_pages


class ThirdProjectOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config/projects/ethernet-cpu-ddr-pcie").mkdir(parents=True)
        (self.root / "config/projects/catalog.yaml").write_text(
            (ROOT / "config/projects/catalog.yaml").read_text())
        (self.root / "config/projects/ethernet-cpu-ddr-pcie/soc.yaml").write_text(
            (ROOT / "config/projects/ethernet-cpu-ddr-pcie/soc.yaml").read_text())
        (self.root / "config/soc.yaml").write_text(
            (ROOT / "config/soc.yaml").read_text())
        (self.root / "config/interface_contracts.yaml").write_text(
            (ROOT / "config/interface_contracts.yaml").read_text())
        (self.root / "gen/chip").mkdir(parents=True)
        (self.root / "gen/chip/soc_top.sv").write_text("module soc_top; endmodule\n")

    def test_scaffold_adds_independent_source_only_catalog_entry(self):
        target = create_project("chip_third", "xezim_ethernet_cpu_ddr_pcie",
                                "Third chip", "New source-only chip",
                                root=self.root)
        self.assertTrue(target.is_file())
        design = yaml.safe_load(target.read_text())
        self.assertEqual(design["name"], "chip_third")
        self.assertEqual(len(design["networks"]["direct_data"]["links"]), 4)
        # The third chip must use a different authored topology rather than
        # only a renamed source. Change both its connectivity and layout.
        design["networks"]["direct_data"]["links"].append({
            "name": "pcie_memory", "endpoints": ["pcie0", "memory0"],
            "duplex": True})
        design["layout"]["regions"] = [
            {"name": "edge", "subsystems": ["pcie0", "ethernet0"]},
            {"name": "compute_memory", "subsystems": ["compute0", "memory0"]}]
        target.write_text(yaml.safe_dump(design, sort_keys=False))
        catalog = projects(self.root)
        self.assertEqual(len(catalog), 3)
        first, second, third = catalog
        self.assertEqual(third["id"], "chip_third")
        self.assertEqual(third["qualification"], "source_contract_only")
        self.assertIsNone(third["generated_source"])
        self.assertIsNone(third["architecture_explorer"])
        self.assertNotEqual(third["config_sha256"], second["config_sha256"])
        self.assertEqual(len(third["data_links"]), 5)
        self.assertEqual(len(second["data_links"]), 4)
        self.assertNotEqual(third["layout"], second["layout"])
        self.assertEqual(len(third["design"]["noc_profiles"]), 19)
        output = self.root / "site"
        output.mkdir()
        (output / "explorer.html").write_text("original RTL explorer")
        project_pages(output, catalog, [], "r987r/xezim-hello-world", "b"*40)
        arch = (output / "projects/chip_third/architecture.html").read_text()
        other = (output / "projects/xezim_ethernet_cpu_ddr_pcie/architecture.html").read_text()
        for token in ('id="arch-h-svg"', 'function drawComposition()',
                      'arch-h-diagram-crumbs', 'data-component-box',
                      'pcie_memory', 'router slots'):
            self.assertIn(token, arch)
            if token not in ("pcie_memory",):
                self.assertIn(token, other)
        self.assertNotIn("pcie_memory", other)
        self.assertNotIn("Open detailed generated RTL", arch)
        self.assertEqual(json.loads((output / "projects/chip_third/data/project.json").read_text())["runs"], [])

    def test_reject_duplicate_and_invalid_id_without_modifying_catalog(self):
        before = (self.root / "config/projects/catalog.yaml").read_text()
        for pid in ("../danger", "xezim_soc_dv", "UpperCase"):
            with self.subTest(pid=pid):
                with self.assertRaises(ValueError):
                    create_project(pid, "xezim_ethernet_cpu_ddr_pcie",
                                   "Another", "Another config", root=self.root)
                self.assertEqual((self.root / "config/projects/catalog.yaml").read_text(), before)


if __name__ == "__main__":
    unittest.main()
