"""Project hardware variants are not synonymous with test names."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hardware_variants


class VariantCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets = yaml.safe_load(
            (ROOT / "config/regression.yaml").read_text())["tests"]

    def test_catalog_is_derived_from_current_test_sources(self):
        got = hardware_variants.catalog(ROOT, self.targets)
        variants = {x["name"]: x for x in got["variants"]}
        self.assertIn("soc-default", variants)
        self.assertIn("soc-ethernet-ddr-pcie", variants)
        self.assertIn("chip-ethernet-ddr-pcie",
                      variants["soc-ethernet-ddr-pcie"]["profiles"])
        self.assertLess(len(variants), len(self.targets))
        self.assertTrue(all(x["status"] == "declared_only_not_compiled"
                            for x in variants.values()))
        self.assertIn("not_protocol_acceptance", got["evidence"])

    def test_identical_real_top_can_be_reused_by_separate_tests(self):
        original = copy.deepcopy(self.targets["chip-boot"])
        tests = {"chip-a": original, "chip-b": copy.deepcopy(original)}
        selected = {"selected_soc_top": "gen/chip/soc_top.sv",
                    "source_sha256": {"gen/chip/soc_top.sv": "a"*64}}
        with patch.object(hardware_variants.Path, "is_file", return_value=True), \
             patch("hardware_variants.verify_selected_archive",
                   return_value=selected):
            variants = hardware_variants.catalog(ROOT, tests, True)["variants"]
        self.assertEqual(variants[0]["verified_profiles"], ["chip-a", "chip-b"])
        self.assertEqual(variants[0]["selected_soc_top_sha256"], "a"*64)

    def test_divergent_hardware_with_same_name_fails(self):
        original = copy.deepcopy(self.targets["chip-boot"])
        tests = {"chip-a": original, "chip-b": copy.deepcopy(original)}
        values = [
            {"selected_soc_top": "gen/chip/soc_top.sv",
             "source_sha256": {"gen/chip/soc_top.sv": x*64}}
            for x in "ab"]
        with patch.object(hardware_variants.Path, "is_file", return_value=True), \
             patch("hardware_variants.verify_selected_archive", side_effect=values):
            with self.assertRaisesRegex(ValueError, "different RTL tops"):
                hardware_variants.catalog(ROOT, tests, True)

    def test_strict_does_not_infer_hardware_from_test_definition(self):
        tests = {"chip-a": copy.deepcopy(self.targets["chip-boot"])}
        with self.assertRaisesRegex(ValueError, "missing selected RTL"):
            hardware_variants.catalog(ROOT, tests, True)


if __name__ == "__main__":
    unittest.main()
