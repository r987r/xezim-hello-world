"""Variant builder must regenerate from actual runner selection, never fake RTL."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_hardware_variant as subject


class StubCompleted:
    def __init__(self, code=0):
        self.returncode = code
        self.stderr = "failed source selection"


class HardwareVariantBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "config").mkdir()
        (self.root / "tools").mkdir()
        (self.root / ".tools").mkdir()
        (self.root / "config/soc.yaml").write_text("name: demo_soc\n")
        (self.root / "config/regression.yaml").write_text(
            "tests:\n"
            "  chip-combined:\n"
            "    firmware_mode: ethernet_ddr_pcie\n"
            "    top: full_chip_tb\n"
            "    sources: noc\n"
            "  chip-default:\n"
            "    top: full_chip_tb\n"
            "    sources: noc\n")
        self.output = self.root / ".tools/reviews"
        self.selected = {
            "schema_version": 1,
            "project": "demo_soc",
            "hardware_variant": "soc-ethernet-ddr-pcie",
            "selected_top_sha256": "a"*64,
            "compiler_input_sha256": "b"*64,
        }
        self.calls = []

    def runner(self, cmd, cwd):
        self.calls.append((cmd, cwd))
        return StubCompleted()

    def stage(self, root, profile, definition, out):
        self.assertEqual(profile, "chip-combined")
        self.assertEqual(definition["firmware_mode"], "ethernet_ddr_pcie")
        self.assertEqual(root, self.root)
        folder = out / "demo_soc" / "soc-ethernet-ddr-pcie"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "manifest.json").write_text(json.dumps(self.selected))
        return copy.deepcopy(self.selected)

    def verify(self, folder):
        return json.loads((folder / "manifest.json").read_text())

    def test_generator_invokes_real_single_runner_and_stages_selected_source(self):
        with patch.object(subject, "stage", side_effect=self.stage), \
             patch.object(subject, "verify_stage", side_effect=self.verify):
            got = subject.rebuild(self.root, "chip-combined", self.output,
                                  runner=self.runner)
        self.assertEqual(got["selected_soc_top_sha256"], "a"*64)
        self.assertEqual(got["compiler_input_sha256"], "b"*64)
        self.assertEqual(got["status"], "selected_sources_generated_not_simulated")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0][-3:], ["chip-combined", "--stage", "files"])
        self.assertEqual(self.calls[0][1], self.root)

    def test_check_rebuilds_and_detects_source_drift_without_overwrite(self):
        original = self.output / "demo_soc" / "soc-ethernet-ddr-pcie"
        original.mkdir(parents=True)
        (original / "manifest.json").write_text(json.dumps(self.selected))
        with patch.object(subject, "stage", side_effect=self.stage), \
             patch.object(subject, "verify_stage", side_effect=self.verify):
            got = subject.rebuild(self.root, "chip-combined", self.output,
                                  check=True, runner=self.runner)
        self.assertIn("rebuilt_exactly", got["status"])
        self.assertEqual(self.verify(original), self.selected)
        altered = {**self.selected, "compiler_input_sha256": "c"*64}
        def modified_stage(root, profile, definition, out):
            self.stage(root, profile, definition, out)
            target = out / "demo_soc" / "soc-ethernet-ddr-pcie" / "manifest.json"
            target.write_text(json.dumps(altered))
            return altered
        with patch.object(subject, "stage", side_effect=modified_stage), \
             patch.object(subject, "verify_stage", side_effect=self.verify):
            with self.assertRaisesRegex(subject.VariantBuildError, "differs"):
                subject.rebuild(self.root, "chip-combined", self.output,
                                check=True, runner=self.runner)
        self.assertEqual(self.verify(original), self.selected)

    def test_drift_diagnostics_are_bounded_and_identify_source_fields(self):
        old = {"source_sha256": {"rtl/top.sv": "a"*64},
               "filelist_sha256": "b"*64}
        new = {"source_sha256": {"rtl/top.sv": "c"*64},
               "filelist_sha256": "b"*64}
        changed = subject._stage_differences(old, new)
        self.assertEqual(changed, ["source_sha256.rtl/top.sv: changed"])
        self.assertEqual(subject._stage_differences(old, new, limit=0), [])

    def test_run_specific_manifest_identity_is_not_a_source_replay_failure(self):
        baseline = {**self.selected, "schema_version": 1,
                    "manifest_sha256": "1"*64, "source_manifest_sha256": "2"*64,
                    "source_sha256": {"rtl/top.sv": "3"*64},
                    "filelist_sha256": "4"*64}
        replay = {**baseline, "manifest_sha256": "5"*64,
                  "source_manifest_sha256": "6"*64}
        self.assertEqual(subject._source_equivalent_stage(baseline),
                         subject._source_equivalent_stage(replay))
        for field, value in (("selected_top_sha256", "9"*64),
                             ("compiler_input_sha256", "8"*64),
                             ("source_sha256", {"rtl/top.sv": "7"*64}),
                             ("filelist_sha256", "0"*64)):
            with self.subTest(field=field):
                changed = {**replay, field: value}
                self.assertNotEqual(subject._source_equivalent_stage(baseline),
                                    subject._source_equivalent_stage(changed))

    def test_reject_unknown_or_default_only_profile_before_runner(self):
        for profile in ("bad/name", "missing", "chip-default"):
            with self.subTest(profile=profile), self.assertRaises(subject.VariantBuildError):
                subject.rebuild(self.root, profile, self.output, runner=self.runner)
        self.assertFalse(self.calls)

    def test_reject_generator_owned_or_outside_review(self):
        for output in (self.root / "gen", self.root / "gen/projects",
                       self.root / "outside", Path("/tmp")):
            with self.subTest(output=str(output)), self.assertRaises(subject.VariantBuildError):
                subject.rebuild(self.root, "chip-combined", output, runner=self.runner)
        self.assertFalse(self.calls)

    def test_runner_failure_cannot_create_a_pass_or_review_artifact(self):
        def bad_runner(cmd, cwd):
            return StubCompleted(code=12)
        with self.assertRaisesRegex(subject.VariantBuildError, "source generation failed"):
            subject.rebuild(self.root, "chip-combined", self.output,
                            runner=bad_runner)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
