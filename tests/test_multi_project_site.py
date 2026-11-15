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
        self.assertEqual(second["qualification"], "ci_generated_compiled")
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
            self.assertIn("ci_generated_compiled", (new / "data/project.json").read_text())
            self.assertNotIn("memory0.hbm0", (new / "address-map.html").read_text())
            self.assertIn("memory0.hbm0", (a / "address-map.html").read_text())
            self.assertEqual(json.loads((new / "data/project.json").read_text())["runs"], [])
            self.assertIn("original", (a / "index.html").read_text().lower())
            self.assertIn("gen/chip/soc_top.sv", (a / "files.html").read_text())
            self.assertIn("chip/soc_top.sv", (new / "files.html").read_text())
            self.assertIn("chip/sources.f", (new / "files.html").read_text())
            self.assertIn("project-compile.yml", (new / "files.html").read_text())
            self.assertNotIn("memory0.hbm0", (new / "files.html").read_text())
            a_arch = (a / "architecture.html").read_text()
            self.assertIn('window.location.replace("../../explorer.html")', a_arch)
            self.assertIn("complete interactive", a_arch)
            self.assertNotIn("project-architecture-frame", a_arch)
            b_arch = (new / "architecture.html").read_text()
            self.assertIn("arch-h-filter", b_arch)
            self.assertIn("arch-h-tree", b_arch)
            self.assertIn("arch-h-crumbs", b_arch)
            self.assertIn("arch-h-children", b_arch)
            self.assertIn("ethernet0", b_arch)
            self.assertIn("l0_ethernet_compute", b_arch)
            self.assertIn("l1_compute_pcie", b_arch)
            self.assertNotIn('src="../../explorer.html"', b_arch)
            self.assertNotIn("memory0.hbm0", b_arch)
            self.assertIn("Declared hierarchy only", b_arch)



    def test_ten_catalog_projects_generate_ten_isolated_navigation_pages(self):
        """Scale proof for catalog/publisher routing, not ten compiled chips."""
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config/projects").mkdir(parents=True)
            (root / "gen/chip").mkdir(parents=True)
            (root / "config/soc.yaml").write_text(
                (ROOT / "config/soc.yaml").read_text())
            (root / "gen/chip/soc_top.sv").write_text("module soc_top; endmodule\n")
            baseline = yaml.safe_load(
                (ROOT / "config/projects/catalog.yaml").read_text())
            baseline["projects"] = [copy.deepcopy(baseline["projects"][0])]
            template = yaml.safe_load(
                (ROOT / "config/projects/ethernet-cpu-ddr-pcie/soc.yaml").read_text())
            for index in range(1, 10):
                pid = f"chip_variant_{index:02d}"
                cfg = copy.deepcopy(template)
                cfg["name"] = pid
                relative = f"config/projects/{pid}.yaml"
                (root / relative).write_text(yaml.safe_dump(cfg, sort_keys=False))
                baseline["projects"].append({
                    "id": pid, "title": f"Chip {index:02d}",
                    "subtitle": "Independent source configuration",
                    "config": relative,
                    "qualification": "source_contract_only"})
            (root / "config/projects/catalog.yaml").write_text(
                yaml.safe_dump(baseline, sort_keys=False))
            catalog = project_catalog.projects(root)
            self.assertEqual(len(catalog), 10)
            self.assertEqual(len({p["config_sha256"] for p in catalog}), 10)
            output = StringIO()
            with patch("sys.argv", ["project_catalog.py", "--root",
                                   str(root), "--matrix"]), redirect_stdout(output):
                project_catalog.main()
            matrix = json.loads(output.getvalue())
            self.assertEqual(matrix["project"], [p["id"] for p in catalog])
            compiled = StringIO()
            with patch("sys.argv", ["project_catalog.py", "--root", str(root),
                                    "--matrix", "--compiled-only"]), redirect_stdout(compiled):
                project_catalog.main()
            self.assertEqual(json.loads(compiled.getvalue())["project"],
                             ["xezim_soc_dv"])
            out = root / "site"
            out.mkdir()
            project_pages(out, catalog, [], "r987r/xezim-hello-world", "b"*40)
            index = (out / "index.html").read_text()
            self.assertEqual(index.count('class="project-card"'), 10)
            for entry in catalog:
                directory = out / "projects" / entry["id"]
                for page in ("index.html", "architecture.html",
                             "address-map.html", "files.html",
                             "runs.html", "data/project.json"):
                    self.assertTrue((directory / page).is_file(), (entry["id"], page))
                self.assertEqual(
                    json.loads((directory / "data/project.json").read_text())["runs"], [])
                self.assertIn("No project-qualified",
                              (directory / "runs.html").read_text())
                architecture = (directory / "architecture.html").read_text()
                self.assertIn("arch-h-filter", architecture)
                self.assertIn(entry["id"], architecture)


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
