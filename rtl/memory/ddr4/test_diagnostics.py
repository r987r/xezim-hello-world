"""Gate future regressions in generated RTL warnings and cocotb VPI flags."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selective_verilator import restrict_vpi_visibility
from warning_audit import assess


class DiagnosticGateTests(unittest.TestCase):
    def test_known_warning_inventory(self):
        raw = "%Warning-WIDTHEXPAND: a\n%Warning-WIDTHTRUNC: b\n"
        result = assess(raw, {"WIDTHEXPAND": 1, "WIDTHTRUNC": 1})
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["total_warnings"], 2)

    def test_new_warning_fails_even_when_process_exits_zero(self):
        raw = "%Warning-WIDTHEXPAND: a\n%Warning-LATCH: new\n"
        result = assess(raw, {"WIDTHEXPAND": 1})
        self.assertEqual(result["status"], "fail")
        self.assertIn("LATCH", result["changes"])

    def test_missing_or_changed_warning_fails(self):
        self.assertEqual(assess("", {"WIDTHEXPAND": 1})["status"], "fail")
        self.assertEqual(assess("%Warning-WIDTHEXPAND: a\n",
                                {"WIDTHEXPAND": 2})["status"], "fail")

    def test_verilator_error_fails(self):
        result = assess("%Warning-WIDTHEXPAND: a\n%Error: broken\n",
                        {"WIDTHEXPAND": 1})
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["verilator_errors"], 1)

    def test_selective_vpi_rejects_global_visibility_or_missing_control(self):
        ctl = Path("/tmp/ddr4_dfi_probes.vlt")
        base = [["perl", "/usr/bin/verilator", "--vpi", "--public-flat-rw",
                 str(ctl), "soc_ddr4_sim.v"],
                ["make", "-f", "Vtop.mk"]]
        amended = restrict_vpi_visibility(base, ctl)
        self.assertNotIn("--public-flat-rw", amended[0])
        self.assertIn(str(ctl), amended[0])
        self.assertIn("--public-flat-rw", base[0])
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            restrict_vpi_visibility([["verilator", "--vpi", str(ctl)]], ctl)
        with self.assertRaisesRegex(ValueError, "omitted"):
            restrict_vpi_visibility([["verilator", "--vpi", "--public-flat-rw"]], ctl)


if __name__ == "__main__":
    unittest.main()
