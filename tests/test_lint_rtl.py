"""slang lint inventory: no false green results, stable diagnostics and dynamic profiles."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import lint_rtl


class SlangLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "config/regression.yaml").write_text(
            "schema_version: 1\ntests:\n"
            "  soc-e2e:\n    sources: noc\n    engine: cocotb-verilator\n    top: new_top\n"
            "  soc-e2e-negative:\n    sources: noc\n    engine: cocotb-verilator\n"
            "    top: new_top\n    reuse_build: true\n    expect_failure: bad\n"
            "  unknown-ip-test:\n    sources: noc\n    engine: cocotb-verilator\n    top: another_top\n"
            "  noc-elaborate:\n    sources: noc\n    engine: verilator-lint\n"
            "  optional-real-memory:\n    sources: noc\n    engine: cocotb-verilator\n"
            "    top: full_chip_tb\n    opt_in: true\n")
        self.folder = self.root / ".tools/regression/soc-e2e"
        self.folder.mkdir(parents=True)
        (self.folder / "sources.f").write_text("fake.sv\n")
        (self.folder / "plan.json").write_text(
            json.dumps({"target": "soc-e2e", "top": "new_top", "sources": ["fake.sv"]}))

    def test_discovers_new_unknown_subsystem_profiles(self):
        self.assertEqual(lint_rtl.select_profiles(self.root, []),
                         ["soc-e2e", "unknown-ip-test"])
        with self.assertRaisesRegex(ValueError, "unknown lint profiles"):
            lint_rtl.select_profiles(self.root, ["missing"])
        # Real DDR controller variant only exists after its pinned runtime
        # generation; ordinary source-filelist lint must stay source-true.
        self.assertNotIn("optional-real-memory", lint_rtl.select_profiles(self.root, []))
        self.assertEqual(lint_rtl.select_profiles(self.root, ["optional-real-memory"]),
                         ["optional-real-memory"])

    def test_source_location_and_severity(self):
        raw = self.root / "diagnostics.json"
        raw.write_text(json.dumps([
            {"severity": "error", "code": "InvalidPort", "location": str(self.root / "rtl/net.sv") + ":16:7",
             "message": "bad width", "symbolPath": "soc_top.noc0"},
            {"severity": "warning", "code": "Unused", "message": "unused signal"},
        ]))
        found = lint_rtl.parse_diagnostics(raw, self.root, "soc-e2e", "lint")
        self.assertEqual(found[0]["file"], "rtl/net.sv")
        self.assertEqual(found[0]["line"], 16)
        self.assertEqual(found[0]["column"], 7)
        self.assertEqual(found[0]["symbol_path"], "soc_top.noc0")
        self.assertEqual(found[1]["severity"], "warning")

    def test_writes_full_report_even_with_design_errors(self):
        def fake(command, **kwargs):
            loc = Path(command[command.index("--diag-json") + 1])
            if "--lint-only" in command:
                loc.write_text(json.dumps([{"severity": "error", "code": "Example",
                                            "message": "test design error"}]))
                return subprocess.CompletedProcess(command, 1, "", "design error")
            loc.write_text("[]")
            return subprocess.CompletedProcess(command, 0, "", "")
        report = lint_rtl.analyze(self.root, "soc-e2e", "new_top", "/bin/slang",
                                  self.root / "results", execute=fake)
        self.assertEqual(report["summary"]["error"], 1)
        self.assertEqual(report["policy"], "report_only")
        self.assertEqual(len(report["modes"]), 2)
        self.assertTrue((self.root / "results/report.json").exists())

    def test_fails_closed_tool_crash_or_bad_json(self):
        def crash(command, **kwargs):
            return subprocess.CompletedProcess(command, 139, "", "segfault")
        with self.assertRaisesRegex(ValueError, "without design diagnostics"):
            lint_rtl.analyze(self.root, "soc-e2e", "new_top", "/bin/slang",
                             self.root / "crash", execute=crash)
        def bad(command, **kwargs):
            path = Path(command[command.index("--diag-json") + 1])
            path.write_text("bad-json")
            return subprocess.CompletedProcess(command, 0, "", "")
        with self.assertRaisesRegex(ValueError, "invalid diagnostics JSON"):
            lint_rtl.analyze(self.root, "soc-e2e", "new_top", "/bin/slang",
                             self.root / "bad", execute=bad)

    def test_rejects_wrong_plan(self):
        (self.folder / "plan.json").write_text(
            json.dumps({"target": "other", "top": "new_top", "sources": ["fake.sv"]}))
        with self.assertRaisesRegex(ValueError, "does not match"):
            lint_rtl.verify_plan(self.root, "soc-e2e", "new_top")


if __name__ == "__main__":
    unittest.main()
