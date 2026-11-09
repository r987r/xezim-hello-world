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
