"""Exact selected RTL comparisons use verified generated archives."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from selected_rtl_provenance import archive_selected_filelist
from design_explorer import selected_variant_diff, selected_variant_markdown


def make(root, content):
    top = root / "gen/chip/soc_top.sv"
    top.parent.mkdir(parents=True)
    top.write_text(content)
    tb = root / "dv/full_chip_tb.sv"
    tb.parent.mkdir(parents=True)
    tb.write_text("module full_chip_tb; endmodule\n")
    out = root / ".tools/regression/example"
    out.mkdir(parents=True)
    sources = [str(top), str(tb)]
    flist = out / "sources.f"
    flist.write_text("\n".join(sources) + "\n")
    test = {"engine":"cocotb-verilator", "sources":"noc", "top":"full_chip_tb"}
    (root / "config").mkdir()
    (root / "config/regression.yaml").write_text(yaml.safe_dump({"tests":{"example":test}}))
    ident = {"legacy_target":"example", "identity_sha256":"test",
             "config_sha256":"test",
             "selection":{"filelist_sha256":hashlib.sha256(flist.read_bytes()).hexdigest()}}
    plan = {**test, "target":"example", "source_target":"noc",
            "sources":sources, "includes":[], "defines":[], "args":[], "identity":ident}
    (out / "plan.json").write_text(json.dumps(plan))
    (out / "identity.json").write_text(json.dumps(ident))
    archive_selected_filelist(root, "example", test, plan, flist)
    return top


class SelectedVariantDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp_a, self.temp_b = TemporaryDirectory(), TemporaryDirectory()
        self.addCleanup(self.temp_a.cleanup)
        self.addCleanup(self.temp_b.cleanup)
        self.a, self.b = Path(self.temp_a.name), Path(self.temp_b.name)
        self.src_a = make(self.a, "module soc_top; wire a; endmodule\n")
        self.src_b = make(self.b, "module soc_top; wire b; endmodule\n")

    def test_real_archive_diff_and_text(self):
        v = selected_variant_diff(self.a,"example",self.b,"example")
        self.assertTrue(v["selected_soc_top_text"]["changed"])
        self.assertIn("gen/chip/soc_top.sv", v["rtl_sources"]["changed"])
        self.assertIn("wire a", selected_variant_markdown(v))
        self.assertIn("wire b", selected_variant_markdown(v))
        self.assertIn("not elaboration", selected_variant_markdown(v))

    def test_selected_compiler_contract_tracks_actual_top_and_filelist(self):
        result = selected_variant_diff(self.a, "example", self.b, "example")
        selected = result["selected_compiler_contract"]
        self.assertEqual(selected["evidence"], "compiler_source_selected_not_elaborated")
        self.assertIn("filelist_sha256", selected["changed"])
        self.assertNotIn("identity_sha256", selected["changed"])
        self.assertNotIn("manifest_sha256", selected["changed"])
        md = selected_variant_markdown(result)
        self.assertIn("Selected compiler and hardware selection", md)
        self.assertIn("filelist_sha256", md)
        self.assertIn("not physical pin proof", md)

    def test_foreign_source_fails_closed(self):
        self.src_b.write_text("module soc_top; wire forged; endmodule\n")
        with self.assertRaisesRegex(ValueError,"modified"):
            selected_variant_diff(self.a,"example",self.b,"example")
        self.src_b.write_text("module soc_top; wire b; endmodule\n")
        folder = self.b / ".tools/regression/example"
        manifest = json.loads((folder / "selected-rtl-manifest.json").read_text())
        (self.b / manifest["archive"] / "gen/chip/soc_top.sv").write_text("forged")
        with self.assertRaisesRegex(ValueError,"mismatch"):
            selected_variant_diff(self.a,"example",self.b,"example")


class ExplicitCombinedReviewTests(unittest.TestCase):
    profile = "chip-ethernet-ddr-pcie"

    def setUp(self):
        from run_workspace import reserve_materialized_run
        from test_identity import selected as identity
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "config").mkdir()
        (self.root / "config/soc.yaml").write_text("name: test_soc\n")
        self.definition = yaml.safe_load((ROOT / "config/regression.yaml").read_text())["tests"][self.profile]
        self.tests = {self.profile: self.definition}
        (self.root / "config/regression.yaml").write_text(yaml.safe_dump({"tests": self.tests}))
        self.first, self.second = [
            self.prepare(i, identity, reserve_materialized_run) for i in (1, 2)
        ]

    def prepare(self, i, identity, reserve):
        seed = identity(self.profile, self.definition, run_id=f"local-{i:012x}", root=ROOT)
        def write(folder):
            top = folder / "variant/soc_top.sv"
            top.parent.mkdir()
            top.write_text(f"module soc_top; wire v{i}; endmodule\n")
            (folder / "sources.f").write_text(str(top) + "\n")
        folder, ident = reserve(self.root / ".tools/runs", seed, write, plan=self.definition)
        filelist = folder / "sources.f"
        plan = {**self.definition, "target": self.profile, "source_target": "noc",
                "stage": "files", "identity": ident,
                "sources": filelist.read_text().splitlines(), "includes": [], "defines": [], "args": []}
        (folder / "plan.json").write_text(json.dumps(plan))
        archive_selected_filelist(self.root, self.profile, self.definition, plan, filelist, directory=folder)
        return folder

    def test_exact_explicit_readers_ignore_other_preparation(self):
        from hardware_variants import catalog
        from lint_rtl import verify_plan
        from selected_rtl_provenance import selected
        for folder in (self.first, self.second):
            self.assertEqual(selected(self.root, self.profile, files_workspace=folder)["source_list"],
                             folder / "sources.f")
            self.assertEqual(verify_plan(self.root, self.profile, "full_chip_tb", files_workspace=folder),
                             folder / "sources.f")
        diff = selected_variant_diff(self.root, self.profile, self.root, self.profile,
                                     before_workspace=self.first, after_workspace=self.second)
        self.assertTrue(diff["selected_soc_top_text"]["changed"])
        self.assertNotEqual(diff["before"]["sha"], diff["after"]["sha"])
        self.assertEqual(catalog(self.root, self.tests)["variants"][0]["verified_profiles"], [])
        with self.assertRaisesRegex(ValueError, "--files-workspace"):
            catalog(self.root, self.tests, require_resolved=True)
        self.assertEqual(catalog(self.root, self.tests, files_workspace=self.first)["variants"][0]
                         ["verified_profiles"], [self.profile])

    def test_no_implicit_selection_mirrors_or_dirty_files(self):
        from selected_rtl_provenance import selected
        with self.assertRaisesRegex(ValueError, "--files-workspace"):
            selected(self.root, self.profile)
        with self.assertRaisesRegex(ValueError, "checkout-owned"):
            selected(self.root, self.profile, files_workspace=self.root.parent)
        (self.first / "result.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "files-only"):
            selected(self.root, self.profile, files_workspace=self.first)
        (self.second / "variant/soc_top.sv").write_text("unverified")
        with self.assertRaisesRegex(ValueError, "modified"):
            selected(self.root, self.profile, files_workspace=self.second)
        mirror = self.root / ".tools/regression" / self.profile
        mirror.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "mirror forbidden"):
            selected(self.root, self.profile, files_workspace=self.second)
