"""Negative and positive exact selected generated-source lock checks."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from selected_source_reference import ReferenceError, compare, validate_lock, _stable_compiler_inputs, TOP


class CombinedReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads(
            (ROOT / "config/selected-rtl-reference/ethernet-ddr-pcie.json").read_text()
        )

    def setUp(self):
        lock = self.lock
        self.lock = copy.deepcopy(self.lock)
        # A synthetic complete selected source inventory. Its fingerprint
        # must be computed from actual selected fields, never from arbitrary
        # literal 64-digit placeholders.
        generated_sv = {k: v for k, v in lock["required_generated_sha256"].items()
                        if k.endswith(".sv")}
        variable = lock["historical_volatile_source_sha256"]
        extra_count = lock["source_count"] - len(generated_sv) - len(variable)
        extra = {f"rtl/pinned/test_source_{n:03d}.sv": "f" * 64
                 for n in range(extra_count)}
        self.manifest = {
            "schema_version": 1,
            "profile": lock["profile"],
            "compiled_top": lock["compiled_top"],
            "selected_soc_top": lock["selected_soc_top"],
            "source_count": lock["source_count"],
            "source_sha256": {
                **extra, **generated_sv, **variable,
                **lock["required_source_sha256"]
            },
            "generated_sha256": dict(lock["required_generated_sha256"]),
            "compiler_input_sha256": lock["exact_compiler_input_sha256"],
            "config_sha256": "1" * 64,
            "definition_sha256": "2" * 64,
            "include_headers_sha256": {},
            "network_filelists": {},
            "defines": [],
            "includes": [],
            "args": [],
            "filelist_sha256": lock["filelist_sha256"],
            "identity_sha256": "c" * 64,
        }
        self.lock["stable_compiler_inputs_sha256"] = _stable_compiler_inputs(
            self.manifest, self.lock["volatile_source_paths"])

    def test_historical_reference_matches_real_source_selection_shape(self):
        validate_lock(self.lock)
        actual = compare(self.lock, self.manifest)
        self.assertEqual(actual["selected_top_sha256"],
                         self.lock["required_generated_sha256"][TOP])
        self.assertEqual(actual["evidence"],
                         "qualified_exact_312_source_compiler_input_not_elaborated")
        self.assertEqual(actual["exact_compiler_input_sha256"],
                         self.manifest["compiler_input_sha256"])
        self.assertEqual(actual["checked_generated_sources"],
                         len(self.lock["required_generated_sha256"]))

    def test_qualified_status_requires_full_source_and_is_not_bit_proof(self):
        result = compare(self.lock, self.manifest)
        self.assertEqual(result["evidence"],
                         "qualified_exact_312_source_compiler_input_not_elaborated")
        for key in ("exact_compiler_input_sha256",
                    "reproducible_controller_source_sha256"):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.lock)
                bad.pop(key)
                with self.assertRaisesRegex(ReferenceError, "pin full compiler"):
                    validate_lock(bad)
        bad = copy.deepcopy(self.lock)
        bad["qualification_status"] = "not-verified"
        with self.assertRaisesRegex(ReferenceError, "qualification status"):
            validate_lock(bad)

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

    def test_reject_other_source_mutation_via_stable_compiler_closure(self):
        for key in ("config_sha256", "filelist_sha256", "definition_sha256"):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.manifest)
                bad[key] = "a" * 64
                with self.assertRaises(ReferenceError):
                    compare(self.lock, bad)
        bad = copy.deepcopy(self.manifest)
        bad["source_sha256"]["rtl/pinned/test_source_000.sv"] = "a" * 64
        with self.assertRaisesRegex(ReferenceError, "stable 311-source"):
            compare(self.lock, bad)

    def test_real_generated_ddr_hash_drift_is_rejected(self):
        path = self.lock["volatile_source_paths"][0]
        changed = copy.deepcopy(self.manifest)
        changed["source_sha256"][path] = "a" * 64
        with self.assertRaisesRegex(ReferenceError, "changed"):
            compare(self.lock, changed)

    def test_complete_compiler_fingerprint_drift_is_rejected(self):
        changed = copy.deepcopy(self.manifest)
        changed["compiler_input_sha256"] = "a" * 64
        with self.assertRaisesRegex(ReferenceError, "exact qualified 312-source"):
            compare(self.lock, changed)

    def test_reject_file_missing_from_compiler_even_if_generated(self):
        bad = copy.deepcopy(self.manifest)
        del bad["source_sha256"][TOP]
        with self.assertRaisesRegex(ReferenceError, "compiled closure"):
            compare(self.lock, bad)

    def test_reject_foreign_profile_missing_provenance_bad_count(self):
        for key, value in (("profile", "other"),
                           ("selected_soc_top", "fake.sv"),
                           ("source_count", 3),
                           ("filelist_sha256", "not-sha")):
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
