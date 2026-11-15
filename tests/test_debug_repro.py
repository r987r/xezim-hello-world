"""Source provenance, fail-closed runner behavior and no fabricated RTL PASS."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from tools import debug_repro


class DebugRecipeTests(unittest.TestCase):
    def test_repo_recipes_parse(self):
        profiles = debug_repro.load_profiles(debug_repro.ROOT / "config/debug.yaml")
        self.assertIn("framework-unit", profiles)
        self.assertIn("regression-unit", profiles)

    def test_reject_invalid_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.yaml"
            for body in (
                "schema_version: 2\nprofiles: {foo: {command: [python3], timeout_s: 5}}",
                "schema_version: 1\nprofiles: {foo: {command: [], timeout_s: 5}}",
                "schema_version: 1\nprofiles: {foo: {command: [python3], timeout_s: 0}}",
                "schema_version: 1\nprofiles: {foo: {command: [python3], timeout_s: 5, tool_versions: [curl]}}",
            ):
                path.write_text(body)
                with self.subTest(body=body), self.assertRaises(ValueError):
                    debug_repro.load_profiles(path)

    def test_no_path_escape(self):
        root = debug_repro.ROOT / ".tools/debug-runs"
        self.assertEqual(debug_repro.safe_output_dir(root, Path(".tools/debug-runs/a")), root / "a")
        for name in (".", "../escape", ".tools/debug-runs/../../bad",
                     ".tools/debug-runs/../bad"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                debug_repro.safe_output_dir(root, Path(name))

    def test_cannot_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory(dir=debug_repro.ROOT / ".tools") as temporary:
            output = Path(temporary)
            with mock.patch.object(debug_repro, "git_output", return_value=""):
                with self.assertRaises(FileExistsError):
                    debug_repro.run_profile("x", {"command": [sys.executable, "-c", "pass"],
                                                   "timeout_s": 5}, output)

    def test_dirty_tree_requires_explicit_override(self):
        with tempfile.TemporaryDirectory(dir=debug_repro.ROOT / ".tools") as temporary:
            output = Path(temporary) / "run"
            with mock.patch.object(debug_repro, "git_output", return_value=" M rtl/example.sv"):
                with self.assertRaisesRegex(ValueError, "tracked source is dirty"):
                    debug_repro.run_profile("x", {"command": [sys.executable, "-c", "pass"],
                                                   "timeout_s": 5}, output)
            self.assertFalse(output.exists())

    def test_subprocess_failure_is_not_qualified(self):
        with tempfile.TemporaryDirectory(dir=debug_repro.ROOT / ".tools") as temporary:
            output = Path(temporary) / "failed"
            profile = {"command": [sys.executable, "-c", "import sys; print('failed');sys.exit(7)"],
                       "timeout_s": 5, "tool_versions": ["python3"]}
            with mock.patch.object(debug_repro, "git_output", return_value=""):
                result = debug_repro.run_profile("failure", profile, output)
            self.assertEqual(result, 7)
            record = json.loads((output / "run.json").read_text())
            self.assertEqual(record["qualification"], "exploratory_only")
            self.assertEqual(record["exit_code"], 7)
            self.assertFalse(record["timed_out"])
            self.assertIn("failed", (output / "stdout-stderr.log").read_text())

    def test_zero_exit_does_not_claim_rtl_pass(self):
        with tempfile.TemporaryDirectory(dir=debug_repro.ROOT / ".tools") as temporary:
            output = Path(temporary) / "success"
            profile = {"command": [sys.executable, "-c", "print('smoke')"], "timeout_s": 5}
            with mock.patch.object(debug_repro, "git_output", return_value=""):
                result = debug_repro.run_profile("smoke", profile, output)
            self.assertEqual(result, 0)
            record = json.loads((output / "run.json").read_text())
            self.assertEqual(record["qualification"], "exploratory_only")
            self.assertNotIn("test_pass", record)
            self.assertIsNone(record["seed"] if "SEED" not in __import__("os").environ else None)


if __name__ == "__main__":
    unittest.main()
