"""Project hardware variants are not synonymous with test names."""
import copy
import tempfile
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hardware_variants
from run_workspace import reserve_run
from test_identity import selected


class VariantCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets = yaml.safe_load(
            (ROOT / "config/regression.yaml").read_text())["tests"]

    def test_catalog_is_derived_from_current_test_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            (root / "config/soc.yaml").write_bytes(
                (ROOT / "config/soc.yaml").read_bytes())
            got = hardware_variants.catalog(root, self.targets)
        variants = {x["name"]: x for x in got["variants"]}
        self.assertIn("soc-default", variants)
        self.assertIn("soc-ethernet-ddr-pcie", variants)
        self.assertIn("chip-ethernet-ddr-pcie",
                      variants["soc-ethernet-ddr-pcie"]["profiles"])
        self.assertLess(len(variants), len(self.targets))
        self.assertTrue(all(x["status"] == "declared_only_not_compiled"
                            for x in variants.values()))
        self.assertIn("not_protocol_acceptance", got["evidence"])

    def _stage_profiles(self, root, profiles, *, manifest=True):
        (root / "config").mkdir()
        (root / "config/soc.yaml").write_bytes(
            (ROOT / "config/soc.yaml").read_bytes())
        tests = {}
        for index, profile in enumerate(profiles):
            plan = copy.deepcopy(self.targets["chip-boot"])
            plan["logical_test"] = profile
            tests[profile] = plan
            identity = selected(profile, plan, root=ROOT, run_id=f"local-{index:012x}")
            workspace = reserve_run(root / ".tools/runs", identity, plan=plan)
            if manifest:
                # The catalog must select an actual per-profile workspace and
                # find its manifest. Tests stub only the archive verifier.
                (workspace / "selected-rtl-manifest.json").write_text("{}\n")
        return tests

    def test_identical_real_top_can_be_reused_by_separate_tests(self):
        verified = {"selected_soc_top": "gen/chip/soc_top.sv",
                    "source_sha256": {"gen/chip/soc_top.sv": "a"*64}}
        with tempfile.TemporaryDirectory() as tmp, \
             patch("hardware_variants.verify_selected_archive", return_value=verified):
            root = Path(tmp)
            tests = self._stage_profiles(root, ("chip-a", "chip-b"))
            variants = hardware_variants.catalog(root, tests, True)["variants"]
        self.assertEqual(variants[0]["verified_profiles"], ["chip-a", "chip-b"])
        self.assertEqual(variants[0]["selected_soc_top_sha256"], "a"*64)

    def test_divergent_hardware_with_same_name_fails(self):
        values = [
            {"selected_soc_top": "gen/chip/soc_top.sv",
             "source_sha256": {"gen/chip/soc_top.sv": x*64}}
            for x in "ab"]
        with tempfile.TemporaryDirectory() as tmp, \
             patch("hardware_variants.verify_selected_archive", side_effect=values):
            root = Path(tmp)
            tests = self._stage_profiles(root, ("chip-a", "chip-b"))
            with self.assertRaisesRegex(ValueError, "different RTL tops"):
                hardware_variants.catalog(root, tests, True)

    def test_strict_does_not_infer_hardware_from_test_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = self._stage_profiles(root, ("chip-a",), manifest=False)
            with self.assertRaisesRegex(ValueError, "chip-a: missing selected RTL archive"):
                hardware_variants.catalog(root, tests, True)


if __name__ == "__main__":
    unittest.main()
