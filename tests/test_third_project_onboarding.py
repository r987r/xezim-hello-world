"""New project onboarding must not hardcode two IDs or borrow hardware evidence."""
from pathlib import Path
import copy
import json
import shutil
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from project_catalog import REGISTRY, projects
from project_scaffold import create_project
from publish_site import project_pages


class ThirdProjectOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog_path = self.root / REGISTRY
        baseline = yaml.safe_load((ROOT / REGISTRY).read_text())
        # Copy the whole catalog and its actual referenced inputs. No setup
        # change should be needed when another project is added.
        inputs = {"config/interface_contracts.yaml"}
        for entry in baseline["projects"]:
            inputs.add(entry["config"])
            if entry.get("generated_source"):
                inputs.add(entry["generated_source"])
        for rel in inputs:
            destination = self.root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, destination)
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(yaml.safe_dump(baseline, sort_keys=False))
        self.baseline_ids = {p["id"] for p in baseline["projects"]}
        self.fixture_id = "chip_onboarding_fixture"
        while self.fixture_id in self.baseline_ids:
            self.fixture_id += "_new"

    def test_scaffold_adds_independent_source_only_catalog_entry(self):
        target = create_project(self.fixture_id, "xezim_ethernet_cpu_ddr_pcie",
                                "Third chip", "New source-only chip",
                                root=self.root)
        self.assertTrue(target.is_file())
        design = yaml.safe_load(target.read_text())
        self.assertEqual(design["name"], self.fixture_id)
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
        # Move the new project ahead of both baselines to catch positional
        # ownership assumptions in the unmodified catalog and site pipeline.
        registry = yaml.safe_load(self.catalog_path.read_text())
        registry["projects"].reverse()
        self.catalog_path.write_text(yaml.safe_dump(registry, sort_keys=False))
        catalog = projects(self.root)
        by_id = {p["id"]: p for p in catalog}
        self.assertEqual(set(by_id), self.baseline_ids | {self.fixture_id})
        second = by_id["xezim_ethernet_cpu_ddr_pcie"]
        third = by_id[self.fixture_id]
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
        for project in catalog:
            if project["architecture_explorer"]:
                explorer = output / project["architecture_explorer"]
                explorer.parent.mkdir(parents=True, exist_ok=True)
                explorer.write_text("project-owned RTL explorer")
        project_pages(output, catalog, [], "r987r/xezim-hello-world", "b"*40)
        listed = json.loads((output / "data/projects.json").read_text())["projects"]
        self.assertEqual([p["id"] for p in listed], [p["id"] for p in catalog])
        fixture_page = output / "projects" / self.fixture_id
        arch = (fixture_page / "architecture.html").read_text()
        other = (output / "projects/xezim_ethernet_cpu_ddr_pcie/architecture.html").read_text()
        for token in ('id="arch-h-svg"', 'function drawComposition()',
                      'arch-h-diagram-crumbs', 'data-component-box',
                      'pcie_memory', 'router slots'):
            self.assertIn(token, arch)
            if token not in ("pcie_memory",):
                self.assertIn(token, other)
        self.assertNotIn("pcie_memory", other)
        self.assertNotIn("Open detailed generated RTL", arch)
        self.assertEqual(json.loads((fixture_page / "data/project.json").read_text())["runs"], [])

    def test_reject_duplicate_and_invalid_id_without_modifying_catalog(self):
        before = self.catalog_path.read_text()
        for pid in ("../danger", "xezim_soc_dv", "UpperCase"):
            with self.subTest(pid=pid):
                with self.assertRaises(ValueError):
                    create_project(pid, "xezim_ethernet_cpu_ddr_pcie",
                                   "Another", "Another config", root=self.root)
                self.assertEqual(self.catalog_path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
