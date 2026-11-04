"""Tests of external Slang tool adapters without pretending vendor binaries ran."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import design_netlist
import design_elaborate


class ExternalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / ".tools/regression/fake").mkdir(parents=True)
        (self.root / "config/regression.yaml").write_text(
            "schema_version: 1\ntests:\n  fake:\n    top: fake_tb\n")
        (self.root / ".tools/regression/fake/sources.f").write_text("fake.sv\n")

    def test_fail_closed_missing_binary(self):
        with patch("design_netlist.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "source-built binary not found"):
                design_netlist.analyze(self.root, "fake", "ports",
                                       self.root / "out/ports.json")
        with patch("design_elaborate.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "executable not found"):
                design_elaborate.analyze(self.root, "fake")

    def test_export_uses_real_profile_and_output(self):
        outfile = self.root / "out/ports.json"
        def run(argv, **kwargs):
            self.assertEqual(argv[1:5], ["--top", "fake_tb", "-f",
                                           str(self.root / ".tools/regression/fake/sources.f")])
            self.assertEqual(argv[-1], str(outfile))
            outfile.write_text('[{"name":"fake_tb.clk","direction":"input"}]')
            return subprocess.CompletedProcess(argv, 0, "", "")
        with patch("design_netlist.shutil.which", return_value="/mock/slang-report"), \
             patch("design_netlist.subprocess.run", side_effect=run):
            meta = design_netlist.analyze(self.root, "fake", "ports", outfile)
        self.assertEqual(meta["evidence"], "elaborated_slang_netlist")
        self.assertEqual(json.loads(outfile.read_text())[0]["name"], "fake_tb.clk")
        self.assertTrue((outfile.parent / (outfile.name + ".meta.json")).exists())

    def test_tool_failure_removes_stale_output(self):
        outfile = self.root / "netlist.json"
        outfile.write_text('{"stale":true}')
        with patch("design_netlist.shutil.which", return_value="/mock/slang-netlist"), \
             patch("design_netlist.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "bad RTL")):
            with self.assertRaisesRegex(ValueError, "bad RTL"):
                design_netlist.analyze(self.root, "fake", "netlist", outfile)
        self.assertFalse(outfile.exists())

    def test_elaboration_custom_format(self):
        def run(argv, **kwargs):
            self.assertIn("--custom-format", argv)
            self.assertIn("|||", argv[-1])
            return subprocess.CompletedProcess(argv, 0,
                                               "fake_tb|||fake_tb|||fake.sv\n", "")
        with patch("design_elaborate.shutil.which", return_value="/mock/slang-hier"), \
             patch("design_elaborate.subprocess.run", side_effect=run):
            result = design_elaborate.analyze(self.root, "fake")
        self.assertEqual(result["instances"][0]["module"], "fake_tb")
        self.assertEqual(result["evidence"], "elaborated_slang_hier")


if __name__ == "__main__":
    unittest.main()
