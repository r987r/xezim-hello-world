"""The archive cannot substitute policy output for the original direct RTL test."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.ethernet_frame_workspace import LOCK, ROOT, SOURCES, checkout_provenance, fetched_provenance, verify_transcript


class EthernetFrameWorkspaceTests(unittest.TestCase):
    def test_original_marker_must_be_present_once_as_a_complete_line(self):
        marker = b"PASS ethernet_rx_frame_stager_tb checks=716 good_beats=19 drops=3"
        verify_transcript(marker + b"\noriginal finish\n")
        for log in (b"", b"banner " + marker, marker + b"\n" + marker, marker[:-1]):
            with self.subTest(log=log), self.assertRaises(ValueError):
                verify_transcript(log)

    def test_requires_clean_exact_ci_checkout_and_explicit_attempt(self):
        env = {"GITHUB_SHA": "a" * 40, "GITHUB_ACTIONS": "true",
               "GITHUB_RUN_ID": "4", "GITHUB_RUN_ATTEMPT": "3"}
        head = b"a" * 40 + b"\n"
        for override, delta in (({}, b""), ({"GITHUB_SHA": "b" * 40}, b""),
                                ({"GITHUB_RUN_ATTEMPT": ""}, b""), ({}, b" M source\n")):
            with self.subTest(override=override, delta=delta), patch(
                    "tools.ethernet_frame_workspace.git", side_effect=[head, delta]):
                if not override and not delta:
                    self.assertEqual(checkout_provenance(ROOT, env), ("a" * 40, False))
                else:
                    with self.assertRaises(ValueError):
                        checkout_provenance(ROOT, {**env, **override})

    def test_rejects_modified_compiler_input_with_same_upstream_head(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lock = root / LOCK
            lock.parent.mkdir(parents=True)
            lock.write_text("third_party:\n  verilog_ethernet: {commit: " + "a" * 40
                            + "}\n  verilog_axis: {commit: " + "b" * 40 + "}\n")
            fifo = root / SOURCES[-1]
            fifo.parent.mkdir(parents=True)
            fifo.write_bytes(b"not the pinned FIFO")
            with patch("tools.ethernet_frame_workspace.git",
                       side_effect=[b"a" * 40, b"b" * 40, b"pinned FIFO"]), self.assertRaisesRegex(
                       ValueError, "differs from the pinned source"):
                fetched_provenance(root)
