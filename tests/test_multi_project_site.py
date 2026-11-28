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
import publish_site
from publish_site import architecture_compiler_links, project_entries, project_pages

ORIGINAL_PROJECT = "xezim_soc_dv"
DIRECT_LINK_PROJECT = "xezim_ethernet_cpu_ddr_pcie"


def original_catalog_entry(catalog):
    return next(p for p in catalog["projects"] if p["id"] == ORIGINAL_PROJECT)


class MultiProjectSiteTests(unittest.TestCase):
    def test_two_independent_projects_no_hardware_alias(self):
        found = {p["id"]: p for p in project_catalog.projects(ROOT)}
        first = found[ORIGINAL_PROJECT]
        second = found[DIRECT_LINK_PROJECT]
        self.assertNotEqual(first["config_sha256"], second["config_sha256"])
        self.assertEqual(first["qualification"], "generated_default")
        self.assertEqual(second["qualification"], "ci_generated_compiled")
        self.assertIsNone(second["generated_source"])
        self.assertEqual(second["memory_targets"], ["memory0.ddr0"])
        declared = yaml.safe_load((ROOT / second["config"]).read_text())
        self.assertEqual(second["data_links"],
                         sorted(declared["networks"]["direct_data"]["links"],
                                key=lambda link: link["name"]))
        self.assertEqual(len(second["data_links"]), 4)

    def test_project_page_isolation_with_unattributed_legacy_capture(self):
        projects = project_catalog.projects(ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "data").mkdir()
            (out / "soc-overview.html").write_text("original overview")
            (out / "explorer.html").write_text("original interactive hierarchy")
            (out / "fabric.html").write_text("original qualified default timing")
            entries = [{"target": "chip-ddr4-real", "passed": True,
                        "source_sha": "a"*40, "path": "runs/legacy/report.html"}]
            project_pages(out, projects, entries, "r987r/xezim-hello-world", "a"*40,
                          default_fabric={"current_measured_routes":64})
            index = (out / "index.html").read_text()
            self.assertIn("Choose a chip project", index)
            self.assertIn("projects/xezim_soc_dv/index.html", index)
            self.assertIn("projects/xezim_ethernet_cpu_ddr_pcie/index.html", index)
            new = out / "projects/xezim_ethernet_cpu_ddr_pcie"
            a = out / "projects/xezim_soc_dv"
            self.assertIn("64 routes have qualified current-source latency",
                          (a / "fabric.html").read_text())
            self.assertIn("Unmeasured is not zero", (new / "fabric.html").read_text())
            self.assertNotIn("64 routes", (new / "fabric.html").read_text())
            self.assertIn("No project-qualified", (new / "runs.html").read_text())
            self.assertNotIn("chip-ddr4-real", (new / "runs.html").read_text())
            self.assertIn("ci_generated_compiled", (new / "data/project.json").read_text())
            self.assertIn("CI-selected RTL · see project compile and boot results", index)
            self.assertNotIn("CPU boot simulation passed", index)
            self.assertIn("no functional AXI PASS is inferred", (new / "index.html").read_text())
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
            self.assertIn("arch-h-filter", a_arch)
            self.assertIn("arch-h-tree", a_arch)
            self.assertIn('id="arch-h-svg"', a_arch)
            self.assertIn('id="arch-h-plane"', a_arch)
            self.assertIn("Interactive composition diagram", a_arch)
            self.assertIn("Open detailed generated RTL / router / signal explorer", a_arch)
            self.assertNotIn("window.location.replace", a_arch)
            b_arch = (new / "architecture.html").read_text()
            self.assertIn("arch-h-filter", b_arch)
            self.assertIn("arch-h-tree", b_arch)
            self.assertIn('id="arch-h-svg"', b_arch)
            self.assertIn('id="arch-h-plane"', b_arch)
            self.assertIn('id="arch-h-fit"', b_arch)
            self.assertIn("Interactive composition diagram", b_arch)
            self.assertIn("const edges = links.filter", b_arch)
            self.assertNotIn("__PROJECT_TOPOLOGY_JS__", b_arch)
            self.assertIn("arch-h-crumbs", b_arch)
            self.assertIn("arch-h-children", b_arch)
            for html in (a_arch, b_arch):
                self.assertLess(html.index('id="arch-h-svg"'), html.index('id="arch-h-filter"'))
                self.assertNotIn("__PROJECT_EVIDENCE_SCOPE__", html)
                self.assertIn("arch-h-expanded", html)
                self.assertIn("dashed desktop links are inferred", html)
                self.assertIn("SUBSYSTEM COMPOSITION", html)
                self.assertIn("function drawComposition()", html)
                self.assertIn("function showFocus(id)", html)
                self.assertIn("NI attachments", html)
                self.assertIn("arch-h-diagram-crumbs", html)
                self.assertIn("FlooGen NoC profiles", html)
                self.assertIn('"noc_profiles":', html)
                self.assertIn('"routers":', html)
                self.assertIn('"endpoints":', html)
                self.assertNotIn("/*__COMPOSITION_IMPL__*/", html)
            self.assertIn("compute1_local_data", a_arch)
            self.assertIn("compute0_local_data", b_arch)
            self.assertNotIn("compute1_local_data", b_arch)

            self.assertIn("ethernet0", b_arch)
            self.assertIn("l0_ethernet_compute", b_arch)
            self.assertIn("l1_compute_pcie", b_arch)
            self.assertNotIn('src="../../explorer.html"', b_arch)
            self.assertIn('id="arch-h-svg"', b_arch)
            self.assertIn("Interactive composition diagram", b_arch)
            self.assertIn("Compiler-parsed RTL/router-level explorer", b_arch)
            self.assertNotIn("memory0.hbm0", b_arch)
            self.assertIn("Declared hierarchy only", b_arch)



    def test_fabric_addresses_and_runs_keep_their_selected_design(self):
        from unittest.mock import patch
        projects=project_catalog.projects(ROOT)
        b=next(project for project in projects if project['id']==DIRECT_LINK_PROJECT)
        a_row={'target':'historical-a-test','run_id':123,'attempt':1,
               'source_sha':'a'*40,'path':'runs/original-a/report.html','passed':True}
        b_row={'target':'b-owned-traffic-test','run_id':456,'attempt':1,
               'source_sha':'b'*40,'path':'runs/original-b/report.html','passed':True,
               'project_id':DIRECT_LINK_PROJECT}
        for row in (a_row,b_row):
            row.update(canonical_id=row['path'], assets=[publish_site.SELECTED_RTL_MANIFEST],
                       compiler_inputs=dict(path=publish_site.SELECTED_RTL_MANIFEST,source_count=3))
        runs=[{'id':e['run_id'],'run_attempt':e['attempt']} for e in (a_row,b_row)]
        boot={'project_id':DIRECT_LINK_PROJECT, 'config_sha256':b['config_sha256'],
              'tested_sha':'c'*40, 'current_source':False, 'status':'passed',
              'run_url':'https://github.com/r987r/xezim-hello-world/actions/runs/789',
              'logs':{}}
        import fabric_report
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(publish_site,'evidence_index',return_value=(runs,[a_row,b_row],[])), \
             patch.object(publish_site.boot_evidence,'publish',return_value={DIRECT_LINK_PROJECT:boot}), \
             patch.object(fabric_report,'attach_one_beat_observations',
                          wraps=fabric_report.attach_one_beat_observations) as attach:
            out=Path(tmp)/'public'
            config=yaml.safe_load((ROOT/'config/publication.yaml').read_text())
            dataset=publish_site.build(out,Path(tmp)/'evidence','r987r/xezim-hello-world','a'*40,config)
            self.assertEqual(attach.call_args.args[1],[a_row])
            self.assertEqual(dataset['entries'],[a_row])
            self.assertEqual(dataset['runs'],[runs[0]])
            a=out/'projects'/ORIGINAL_PROJECT
            b=out/'projects'/DIRECT_LINK_PROJECT
            name=publish_site.SELECTED_RTL_MANIFEST
            for explorer, prefix, own, other in (
                (out/'explorer.html','',a_row,b_row),
                (a/'architecture.html','../../',a_row,b_row),
                (b/'architecture.html','../../',b_row,a_row),
            ):
                body=explorer.read_text()
                self.assertIn(f'href="{prefix}{Path(own["path"]).with_name(name).as_posix()}"',body)
                self.assertNotIn(Path(other["path"]).with_name(name).as_posix(),body)
            a_fabric=(a/'fabric.html').read_text()
            b_fabric=(b/'fabric.html').read_text()
            for html in ((out/'fabric.html').read_text(),(out/'runs.html').read_text(),
                         (out/'address-map.html').read_text()):
                self.assertIn('Hierarchical SoC</a> only',html)
            self.assertIn('memory0.hbm0',a_fabric)
            self.assertIn('compute1_local_data',a_fabric)
            self.assertIn('href="../../fabric.html"',a_fabric)
            self.assertNotIn('id="fabric-data"',a_fabric) # no second measured dataset
            for name in ('central_compute_memory','l0_ethernet_compute',
                         'l0_ethernet_memory','l1_compute_pcie','memory0.ddr0'):
                self.assertIn(name,b_fabric)
            for unexpected in ('memory0.hbm0','compute1_local_data','href="../../fabric.html"',
                               'qualified current-source latency','id="fabric-data"'):
                self.assertNotIn(unexpected,b_fabric)
            self.assertIn('Unmeasured is not zero',b_fabric)
            for pair in (
                    '<td>ethernet0</td><td>compute0.sram</td><td>0x10000000 via to_compute0 → compute0</td>',
                    '<td>ethernet0</td><td>memory0.ddr0</td><td>0x140000000 via to_memory0 → memory0</td>'):
                self.assertIn(pair,b_fabric)
                self.assertNotIn(pair,a_fabric)
            self.assertNotIn('<td>ethernet0</td><td>memory0.ddr0</td><td>0x140000000 via to_compute0',b_fabric)
            self.assertIn('href="fabric.html"',(b/'index.html').read_text())
            a_addresses=(a/'address-map.html').read_text()
            b_addresses=(b/'address-map.html').read_text()
            detailed_addresses='href="../../address-map.html"'
            self.assertIn(detailed_addresses,a_addresses)
            self.assertIn('PCIe and DDR register',a_addresses)
            self.assertNotIn(detailed_addresses,b_addresses)
            self.assertNotIn('memory0.hbm0',b_addresses)
            self.assertIn('<code>memory0.ctrl</code></td><td><code>0x40030000</code>'
                          '</td><td><code>0x1000</code>',b_addresses)
            register_browser=(a/'../../address-map.html').read_text()
            self.assertIn('Hierarchical SoC</a> only',register_browser)
            self.assertIn('id="am-csr-browser"',register_browser)
            for html in (a_addresses,b_addresses):
                self.assertNotIn(a_row['path'],html)
                self.assertNotIn(b_row['path'],html)
            a_tests=(a/'runs.html').read_text()
            b_tests=(b/'runs.html').read_text()
            self.assertIn('historical-a-test',a_tests)
            self.assertNotIn('b-owned-traffic-test',a_tests)
            self.assertIn('b-owned-traffic-test',b_tests)
            self.assertIn('Historical source PASS',b_tests)
            self.assertNotIn('historical-a-test',b_tests)
            self.assertNotIn('href="../../runs.html"',b_tests)

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
            baseline["projects"] = [original_catalog_entry(baseline)]
            template = yaml.safe_load(
                (ROOT / "config/projects/ethernet-cpu-ddr-pcie/soc.yaml").read_text())
            for index in range(1, 10):
                pid = f"chip_variant_{index:02d}"
                cfg = copy.deepcopy(template)
                cfg["name"] = pid
                if index==1:
                    ddr=next(region for region in cfg["address_map"]["data"]
                             if region["name"]=="memory0.ddr0")
                    ddr["base"]="0x180000000"
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
                             [ORIGINAL_PROJECT])
            out = root / "site"
            out.mkdir()
            (out / "explorer.html").write_text("original interactive hierarchy")
            project_pages(out, catalog, [], "r987r/xezim-hello-world", "b"*40)
            index = (out / "index.html").read_text()
            self.assertEqual(index.count('class="project-card"'), 10)
            direct_fixture='<td>ethernet0</td><td>memory0.ddr0</td><td>'
            moved=(out/'projects/chip_variant_01/fabric.html').read_text()
            ordinary=(out/'projects/chip_variant_02/fabric.html').read_text()
            self.assertIn(direct_fixture+'0x180000000 via to_memory0 → memory0</td>',moved)
            self.assertNotIn(direct_fixture+'0x140000000',moved)
            self.assertIn(direct_fixture+'0x140000000 via to_memory0 → memory0</td>',ordinary)
            self.assertNotIn(direct_fixture+'0x180000000',ordinary)
            for entry in catalog:
                directory = out / "projects" / entry["id"]
                for page in ("index.html", "architecture.html",
                             "address-map.html", "files.html",
                             "runs.html", "fabric.html", "data/project.json"):
                    self.assertTrue((directory / page).is_file(), (entry["id"], page))
                self.assertEqual(
                    json.loads((directory / "data/project.json").read_text())["runs"], [])
                self.assertIn("No project-qualified",
                              (directory / "runs.html").read_text())
                architecture = (directory / "architecture.html").read_text()
                self.assertIn("arch-h-filter", architecture)
                self.assertIn('id="arch-h-svg"', architecture)
                self.assertIn("const edges = links.filter", architecture)
                if entry.get("architecture_explorer"):
                    self.assertIn("Open detailed generated RTL", architecture)
                self.assertIn(entry["id"], architecture)


    def test_other_compiled_projects_cannot_borrow_default_explorer(self):
        catalog = project_catalog.projects(ROOT)
        cloned = copy.deepcopy(next(p for p in catalog if p["id"] == DIRECT_LINK_PROJECT))
        cloned["architecture_explorer"] = None
        cloned["qualification"] = "ci_generated_compiled"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "explorer.html").write_text("legacy hierarchy")
            project_pages(out, [cloned], [], "r987r/xezim-hello-world", "c"*40)
            arch = (out / "projects" / cloned["id"] / "architecture.html").read_text()
            self.assertIn("arch-h-filter", arch)
            self.assertNotIn('window.location.replace("../../explorer.html")', arch)

    def test_catalog_requires_unique_explorer_ownership(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config/projects").mkdir(parents=True)
            (root / "config/soc.yaml").write_text(
                (ROOT / "config/soc.yaml").read_text())
            (root / "gen/chip").mkdir(parents=True)
            (root / "gen/chip/soc_top.sv").write_text("module soc_top; endmodule")
            cfg = yaml.safe_load((ROOT / "config/projects/catalog.yaml").read_text())
            original = original_catalog_entry(cfg)
            alias = dict(original, id="another_chip", config="config/projects/another_chip.yaml")
            cfg["projects"] = [original, alias]
            clone = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
            clone["name"] = "another_chip"
            (root / alias["config"]).write_text(yaml.safe_dump(clone))
            (root / "config/projects/catalog.yaml").write_text(yaml.safe_dump(cfg))
            with self.assertRaisesRegex(ValueError, "more than one project"):
                project_catalog.projects(root)

    def test_bad_catalog_rejects_aliased_or_unqualified_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config/projects").mkdir(parents=True)
            (root / "gen/chip").mkdir(parents=True)
            (root / "config/soc.yaml").write_text(
                (ROOT / "config/soc.yaml").read_text())
            (root / "gen/chip/soc_top.sv").write_text("module soc_top; endmodule")
            catalog = yaml.safe_load((ROOT / "config/projects/catalog.yaml").read_text())
            original = original_catalog_entry(catalog)
            catalog["projects"] = [original, copy.deepcopy(original)]
            (root / "config/projects/catalog.yaml").write_text(
                yaml.safe_dump(catalog))
            with self.assertRaisesRegex(ValueError, "duplicate project identity"):
                project_catalog.projects(root)


class ArchitectureCompilerLinks(unittest.TestCase):
    def setUp(self):
        self.manifest = 'selected-rtl-manifest.json'
        self.entry = dict(
            project_id='a', target='chip-boot', canonical_id='verilator/a/b/run-a',
            run_id=123, attempt=2, source_sha='f' * 40, passed=False,
            path='runs/verilator/a/b/run-a/report.html', assets=[self.manifest],
            compiler_inputs=dict(path=self.manifest, source_count=279),
            compiler_artifact_id=456,
        )

    def render(self, *entries, design='a', base='../../'):
        return architecture_compiler_links(
            project_entries(entries, design, 'a'), base, 'owner/test')

    def test_same_run_manifest_original_archive_and_tested_source(self):
        html = self.render(self.entry)
        self.assertIn('href="../../runs/verilator/a/b/run-a/' + self.manifest, html)
        self.assertIn('Run 123, attempt 2', html)
        self.assertIn('https://github.com/owner/test/actions/runs/123/artifacts/456', html)
        self.assertIn('ffffffffff', html)
        self.assertNotIn('Recorded PASS', html)
        self.assertIn('href="runs/verilator/', self.render(self.entry, base=''))

    def test_newest_available_verified_per_target_and_project_only(self):
        older = dict(self.entry, run_id=100, compiler_artifact_id=None)
        other = dict(self.entry, project_id='b', target='chip-other')
        unverified_latest = dict(self.entry, run_id=999, compiler_inputs=None)
        html = self.render(other, unverified_latest, self.entry, older)
        self.assertNotIn('chip-other', html)
        self.assertNotIn('Run 100', html)
        self.assertNotIn('Run 999', html)
        self.assertIn('Run 123', html)
        self.assertIn('Run 100', self.render(older))
        self.assertNotIn('/artifacts/', self.render(older))

    def test_observation_missing_asset_and_foreign_links_do_not_publish(self):
        mutants = [
            dict(self.entry, evidence_only=True),
            dict(self.entry, assets=[]),
            dict(self.entry, path='https://external.test/report.html'),
            dict(self.entry, canonical_id=None),
        ]
        wrong = copy.deepcopy(self.entry)
        wrong['compiler_inputs']['path'] = 'elsewhere.json'
        html = self.render(*mutants, wrong)
        self.assertIn('No verified compiler manifests published', html)
        self.assertNotIn('<a ', html)


if __name__ == "__main__":
    unittest.main()
