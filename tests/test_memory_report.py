"""Regression contract: shared memory evidence, no separate report or runner."""
import tempfile
import unittest
from pathlib import Path

from tools.memory_report import read_memory_report


def evidence():
    modes = [
        ("init", "frontdoor"), ("check", "frontdoor"),
        ("init", "backdoor"), ("check", "backdoor"),
        ("init", "backdoor"), ("check", "backdoor+frontdoor-sample"),
    ]
    return {
        "schema_version": 1, "source": "real_floonoc_host_sparse",
        "route_initiator": "from_config", "memory_target": "from_routing",
        "region": "memory0.ddr0", "address": "0x140008100",
        "size_bytes": 256, "clock_period_ps": 10000,
        "validation": "two-way AXI/backdoor proof plus scratch restoration",
        "events": [
            {"operation": op, "method": method, "bytes": 256,
             "wall_ns": 100, "simulated_cycles": 2}
            for op, method in modes
        ]
    }


def axi():
    return [
        {"role": "initiator", "operation": operation, "address": "0x140008100",
         "status": "complete", "response": "0x0"}
        for operation in ("write", "read")
    ]


class MemoryReportTests(unittest.TestCase):
    def check(self, value, rows=None, period=10000):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/"memory-operations.json").write_text(__import__("json").dumps(value))
            return read_memory_report(folder, axi() if rows is None else rows, period)

    def test_valid_model_and_real_axi_evidence(self):
        section, issues = self.check(evidence())
        self.assertEqual(issues, [])
        self.assertEqual(len(section["events"]), 6)

    def test_missing_memory_file_is_fatal(self):
        with tempfile.TemporaryDirectory() as folder:
            section, issues = read_memory_report(folder, axi(), 10000)
        self.assertIsNone(section)
        self.assertIn("missing", issues[0])

    def test_invalid_method_or_missing_axi_is_fatal(self):
        bad=evidence()
        bad["events"][3]["method"]="frontdoor"
        self.assertTrue(self.check(bad)[1])
        self.assertIn("write", " ".join(self.check(evidence(), rows=axi()[1:])[1]))
        self.assertIn("read", " ".join(self.check(evidence(), rows=axi()[:1])[1]))

    def test_mismatched_clock_and_wrong_backdoor_proof_fail(self):
        self.assertTrue(self.check(evidence(),period=5000)[1])
        bad=evidence()
        bad["validation"]="assumed"
        self.assertTrue(self.check(bad)[1])
