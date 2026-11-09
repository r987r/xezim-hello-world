"""Default SoC review RTL must be actual generated code and hash-stable."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate

class DefaultReviewVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def test_tracked_default_variant_exact_code_copy(self):
        source = ROOT / "gen/chip/soc_top.sv"
        root = ROOT / "gen/projects" / self.cfg["name"] / "variants/default"
        copy = root / "rtl/soc_top.sv"
        record = json.loads((root / "manifest.json").read_text())
        self.assertEqual(copy.read_bytes(), source.read_bytes())
        self.assertEqual(generate.sha(copy.read_bytes()), record["generated_sv_sha256"])
        self.assertEqual(record["variant"], "default")
        self.assertIn("not_opt_in_selected", record["evidence"])
        self.assertIn("module soc_top", copy.read_text())

    def test_generator_emits_identical_baseline_without_full_build(self):
        selected = generate.verify_generated_source_graph(self.cfg, ROOT / "gen")
        self.assertEqual(selected["project"], self.cfg["name"])
        self.assertEqual(selected["variant"], "default")
        with tempfile.TemporaryDirectory() as temp:
            scratch = Path(temp)
            chip = scratch / "chip"
            chip.mkdir()
            (chip / "soc_top.sv").write_bytes(
                (ROOT / "gen/chip/soc_top.sv").read_bytes())
            generate.emit_default_review_variant(selected, scratch)
            actual = scratch / "projects" / self.cfg["name"] / "variants/default"
            expected = ROOT / "gen/projects" / self.cfg["name"] / "variants/default"
            self.assertEqual((actual / "rtl/soc_top.sv").read_bytes(),
                             (expected / "rtl/soc_top.sv").read_bytes())
            self.assertEqual((actual / "manifest.json").read_bytes(),
                             (expected / "manifest.json").read_bytes())

    def test_missing_unsafe_or_wrong_project_fails_closed(self):
        selected = generate.verify_generated_source_graph(self.cfg, ROOT / "gen")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(generate.GenerationError, "missing"):
                generate.emit_default_review_variant(selected, root)
            root.joinpath("chip").mkdir()
            root.joinpath("chip/soc_top.sv").symlink_to(
                ROOT / "gen/chip/soc_top.sv")
            with self.assertRaisesRegex(generate.GenerationError, "missing"):
                generate.emit_default_review_variant(selected, root)
            (root / "chip/soc_top.sv").unlink()
            (root / "chip/soc_top.sv").write_text("module soc_top; endmodule\n")
            with self.assertRaisesRegex(generate.GenerationError, "project name"):
                generate.emit_default_review_variant(
                    {**selected, "project": "bad/name"}, root)
            with self.assertRaisesRegex(generate.GenerationError, "source-validated IR"):
                generate.emit_default_review_variant(
                    {**selected, "variant": "ethernet-ddr-pcie"}, root)
            with self.assertRaisesRegex(generate.GenerationError, "source-validated IR"):
                generate.emit_default_review_variant(
                    {**selected, "soc_ir_sha256": "0" * 63}, root)

if __name__ == "__main__":
    unittest.main()
