"""Negative and positive exact selected generated-source lock checks."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from selected_source_reference import ReferenceError, compare, validate_lock, TOP


class CombinedReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads(
            (ROOT / "config/selected-rtl-reference/ethernet-ddr-pcie.json").read_text()
        )

    def setUp(self):
        lock = self.lock
        self.manifest = {
            "schema_version": 1,
            "profile": lock["profile"],
            "compiled_top": lock["compiled_top"],
            "selected_soc_top": lock["selected_soc_top"],
            "source_count": lock["source_count"],
            "source_sha256": {
                **lock["required_source_sha256"], **lock["required_generated_sha256"]
            },
            "generated_sha256": dict(lock["required_generated_sha256"]),
            "compiler_input_sha256": "a" * 64,
            "filelist_sha256": "b" * 64,
            "identity_sha256": "c" * 64,
        }

    def test_historical_reference_matches_real_source_selection_shape(self):
        validate_lock(self.lock)
        actual = compare(self.lock, self.manifest)
        self.assertEqual(actual["selected_top_sha256"],
                         self.lock["required_generated_sha256"][TOP])
        self.assertIn("not_bit_elaboration", actual["evidence"])
        self.assertEqual(actual["checked_generated_sources"],
                         len(self.lock["required_generated_sha256"]))

    def test_independent_run_id_never_changes_selected_source_identity(self):
        other = copy.deepcopy(self.manifest)
        other["identity_sha256"] = "d" * 64
        self.assertEqual(compare(self.lock, other),
                         compare(self.lock, self.manifest))

    def test_fail_closed_on_modified_top_noc_firmware_ddr(self):
        for path in self.lock["required_generated_sha256"]:
            with self.subTest(path=path):
                bad = copy.deepcopy(self.manifest)
                bad["generated_sha256"][path] = "0" * 64
                with self.assertRaisesRegex(ReferenceError, "changed"):
                    compare(self.lock, bad)
        for path in self.lock["required_source_sha256"]:
            with self.subTest(path=path):
                bad = copy.deepcopy(self.manifest)
                bad["source_sha256"][path] = "0" * 64
                with self.assertRaisesRegex(ReferenceError, "changed"):
                    compare(self.lock, bad)

    def test_reject_file_missing_from_compiler_even_if_generated(self):
        bad = copy.deepcopy(self.manifest)
        del bad["source_sha256"][TOP]
        with self.assertRaisesRegex(ReferenceError, "compiled closure"):
            compare(self.lock, bad)

    def test_reject_foreign_profile_missing_provenance_bad_count(self):
        for key, value in (("profile", "other"),
                           ("selected_soc_top", "fake.sv"),
                           ("source_count", 3),
                           ("compiler_input_sha256", "not-sha")):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.manifest)
                bad[key] = value
                with self.assertRaises(ReferenceError):
                    compare(self.lock, bad)
        lock = copy.deepcopy(self.lock)
        lock["verified_pr_head"] = "invalid"
        with self.assertRaisesRegex(ReferenceError, "SHA"):
            compare(lock, self.manifest)
        lock = copy.deepcopy(self.lock)
        del lock["required_generated_sha256"][TOP]
        with self.assertRaisesRegex(ReferenceError, "generated top"):
            compare(lock, self.manifest)


if __name__ == "__main__":
    unittest.main()
