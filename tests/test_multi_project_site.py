"""Project picker and project-scoped source/evidence isolation gates."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import project_catalog
from publish_site import project_pages


class MultiProjectSiteTests(unittest.TestCase):
    def test_two_independent_projects_no_hardware_alias(self):
        found = project_catalog.projects(ROOT)
        self.assertEqual([x["id"] for x in found],
                         ["xezim_soc_dv", "xezim_ethernet_cpu_ddr_pcie"])
        first, second = found
        self.assertNotEqual(first["config_sha256"], second["config_sha256"])
        self.assertEqual(first["qualification"], "generated_default")
        self.assertEqual(second["qualification"], "source_contract_only")
        self.assertIsNone(second["generated_source"])
        self.assertEqual(second["memory_targets"], ["memory0.ddr0"])
        self.assertEqual(len(second["data_links"]), 3)

    def test_project_page_isolation_with_unattributed_legacy_capture(self):
        projects = project_catalog.projects(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "data").mkdir()
            (out / "soc-overview.html").write_text("original overview")
            entries = [{"target": "chip-ddr4-real", "passed": True,
                        "source_sha": "a"*40, "path": "runs/legacy/report.html"}]
            project_pages(out, projects, entries, "r987r/xezim-hello-world", "a"*40)
            index = (out / "index.html").read_text()
            self.assertIn("Choose a chip project", index)
            self.assertIn("projects/xezim_soc_dv/index.html", index)
            self.assertIn("projects/xezim_ethernet_cpu_ddr_pcie/index.html", index)
            new = out / "projects/xezim_ethernet_cpu_ddr_pcie"
            a = out / "projects/xezim_soc_dv"
            self.assertIn("No project-qualified", (new / "runs.html").read_text())
            self.assertNotIn("chip-ddr4-real", (new / "runs.html").read_text())
            self.assertIn("source_contract_only", (new / "data/project.json").read_text())
            self.assertNotIn("memory0.hbm0", (new / "address-map.html").read_text())
            self.assertIn("memory0.hbm0", (a / "address-map.html").read_text())
            self.assertEqual(json.loads((new / "data/project.json").read_text())["runs"], [])
            self.assertIn("original", (a / "index.html").read_text().lower())

    def test_bad_catalog_rejects_aliased_or_unqualified_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            import shutil
            root = Path(temp)
            (root / "config/projects").mkdir(parents=True)
            (root / "gen/chip").mkdir(parents=True)
            (root / "config/soc.yaml").write_text(
                (ROOT / "config/soc.yaml").read_text())
            (root / "gen/chip/soc_top.sv").write_text("module soc_top; endmodule")
            catalog = yaml.safe_load((ROOT / "config/projects/catalog.yaml").read_text())
            catalog["projects"] = [copy.deepcopy(catalog["projects"][0])]*2
            (root / "config/projects/catalog.yaml").write_text(
                yaml.safe_dump(catalog))
            with self.assertRaisesRegex(ValueError, "duplicate project identity"):
                project_catalog.projects(root)


if __name__ == "__main__":
    unittest.main()
