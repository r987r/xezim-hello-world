"""Offline DDR4 report checks: fail closed on missing or unverifiable evidence."""
from pathlib import Path
import json
import tempfile
import unittest
from report_html import load, render


class DDRHTMLReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.evidence = {
            "ddr4_functional_result.json": {
                "status": "pass", "top": "soc_ddr4_sim",
                "monitor": {"sampled_cycles": 1000},
            },
            "ddr4_latency.json": {
                "reference_clock": {"period_ps": 10000},
                "measured": {
                    "read": {"samples": 2, "min_cycles": 11, "avg_cycles": 12,
                             "max_cycles": 13},
                    "write": {"samples": 2, "min_cycles": 6, "avg_cycles": 7,
                              "max_cycles": 8},
                },
                "measured_boundary": {
                    "read": "AR→last R", "write": "AW→B",
                },
            },
            "ddr4_internal_latency.json": {
                "status": "measured_model_events",
                "internal_stages": {
                    "dfi_read_to_valid": {"status": "measured", "samples": 1,
                                          "avg_cycles": 4.0},
                    "controller_aw_to_dfi_write": {
                        "status": "unmeasured", "reason": "no DFI ID",
                    },
                },
            },
            "ddr4_traffic_summary.json": {
                "status": "pass", "sampled_cycles": 1000,
                "continuous_capture": True, "overflows": 0,
                "channels": {"aw": 2, "w": 4, "b": 2, "ar": 2, "r": 4},
            },
            "ddr4_warning_audit.json": {"status": "pass", "total_warnings": 2047},
        }
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        for name, obj in self.evidence.items():
            (self.path / name).write_text(json.dumps(obj))

    def test_measured_axi_and_unmeasured_dfi_are_unambiguous(self):
        page = render(load(self.path))
        self.assertIn("UNMEASURED", page)
        self.assertIn("AR→last R", page)
        self.assertIn("AW→B", page)
        self.assertIn("2047", page)
        self.assertIn("standalone", page)
        self.assertNotIn("FULL-CHIP PASS", page)

    def test_incomplete_or_bad_evidence_refused(self):
        self.evidence["ddr4_latency.json"]["measured"]["read"]["samples"] = 0
        self.write()
        with self.assertRaisesRegex(ValueError, "missing measured"):
            load(self.path)
        self.evidence["ddr4_latency.json"]["measured"]["read"]["samples"] = 2
        self.evidence["ddr4_traffic_summary.json"]["overflows"] = 1
        self.write()
        with self.assertRaisesRegex(ValueError, "overflow"):
            load(self.path)
        self.evidence["ddr4_traffic_summary.json"]["overflows"] = 0
        self.evidence["ddr4_traffic_summary.json"]["sampled_cycles"] = 999
        self.write()
        with self.assertRaisesRegex(ValueError, "cycle mismatch"):
            load(self.path)

    def test_missing_and_symlink_evidence_refused(self):
        (self.path / "ddr4_warning_audit.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing/unsafe"):
            load(self.path)
        (self.path / "ddr4_warning_audit.json").symlink_to(
            self.path / "ddr4_latency.json"
        )
        with self.assertRaisesRegex(ValueError, "missing/unsafe"):
            load(self.path)


if __name__ == "__main__":
    unittest.main()
