"""Native OpenPCIe decoder adapter feeds the existing protocol sink only."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.pcie_native_pipe_capture import SOURCE, capture
from tools.protocol_report import parse_capture
from tools.pcie_native_pipe_capture import source_catalog


def example(*, result="TESTS=1 PASS=0 FAIL=1 SKIP=0", bad=""):
    return (
        "PCIE_UPSTREAM_PIPE_MON_TLP: direction=EP_TO_RC time_ps=1200 bytes=4 raw=0102aabb\n"
        "PCIE_UPSTREAM_PIPE_MON_DLLP: direction=EP_TO_RC time_ps=1400 bytes=3 raw=000102\n"
        "PCIE_UPSTREAM_PIPE_MON_TLP: direction=EP_TO_RC time_ps=1400 bytes=4 raw=0102aabb\n"
        + bad + result + "\n"
    )


class NativePciePipeAdapterTests(unittest.TestCase):
    def test_native_packet_replays_keep_original_bytes_and_test_failure(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            info = capture(example(), root)
            self.assertEqual(info["counts"], {"tlp": 2, "dllp": 1})
            self.assertFalse(info["original_test_pass"])
            source = parse_capture(root / "protocol-events.jsonl", source_catalog())
            self.assertEqual([r["operation"] for r in source["records"]],
                             ["tlp_frame", "dllp_frame", "tlp_frame"])
            self.assertEqual([r["start_ps"] for r in source["records"]],
                             [1200, 1400, 1400])
            self.assertEqual([r["fields"]["data_hex"] for r in source["records"]],
                             ["0102aabb", "000102", "0102aabb"])
            self.assertEqual(set(r["source"] for r in source["records"]), {SOURCE})
            self.assertTrue((root / "protocols.html").exists())
            report = json.loads((root / "protocol-transactions.json").read_text())
            self.assertTrue(report["capture_complete"])
            self.assertEqual(report["run"]["test_status"], "fail")
            self.assertEqual(report["run"]["qualification"], "capture_only_original_upstream")
            self.assertEqual(report["run"]["link_scope"], "endpoint_tx_only_rc_receipt_not_measured")
            self.assertFalse((root / "result.json").exists())

    def test_green_test_can_have_capture_but_still_only_capture_scope(self):
        with TemporaryDirectory() as folder:
            report = capture(example(result="TESTS=1 PASS=1 FAIL=0 SKIP=0"), Path(folder))
            self.assertTrue(report["original_test_pass"])
            self.assertEqual(json.loads(
                (Path(folder) / "protocol-transactions.json").read_text()
            )["run"]["qualification"], "capture_only_original_upstream")

    def test_original_test_summary_required(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "result table missing"):
                capture(example(result="not completed"), Path(folder))

    def test_absent_tlp_or_dllp_is_not_a_successful_capture(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "missing original native"):
                capture("PCIE_UPSTREAM_PIPE_MON_TLP: direction=EP_TO_RC "
                        "time_ps=1 bytes=1 raw=aa\nTESTS=1 PASS=1 FAIL=0 SKIP=0", Path(folder))

    def test_corruption_is_fail_closed(self):
        for event in (
            "PCIE_UPSTREAM_PIPE_MON_TLP: direction=EP_TO_RC time_ps=2 bytes=4 raw=aa",
            "PCIE_UPSTREAM_PIPE_MON_DLLP_UNDECODED: direction=EP_TO_RC time_ps=3",
            "PCIE_UPSTREAM_PIPE_MON_TLP: direction=RC_TO_EP time_ps=3 bytes=1 raw=aa",
            "PCIE_UPSTREAM_PIPE_MON_TLP: direction=EP_TO_RC time_ps=3 bytes=1 raw=zz",
        ):
            with self.subTest(event=event), TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError, "malformed native|byte count"):
                    capture(example(bad=event + "\n"), Path(folder))

    def test_monotonic_source_time_and_event_bound(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, "out-of-order"):
                capture(example(bad="PCIE_UPSTREAM_PIPE_MON_DLLP: direction=EP_TO_RC "
                        "time_ps=3 bytes=1 raw=ff\n"), Path(folder))
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, "overflow"):
                capture(example(), Path(folder), max_events=2)


if __name__ == "__main__":
    unittest.main()
