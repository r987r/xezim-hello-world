"""The DDR archive is not replacement simulation or chip evidence."""
import unittest
from unittest.mock import patch

from tools.ddr_foundation_unit_workspace import LANES, ROOT, checkout_provenance, verify_transcript


class DDRFoundationUnitWorkspaceTests(unittest.TestCase):
    def test_requires_exactly_one_original_marker_not_another_lane(self):
        for lane, (_, _, marker) in LANES.items():
            with self.subTest(lane=lane):
                verify_transcript(lane, b"start\n" + marker + b"\nnative finish\n")
                for invalid in (b"", marker[:-1], b"prefixed " + marker, marker + b"\n" + marker):
                    with self.assertRaises(ValueError):
                        verify_transcript(lane, invalid)
                for other in LANES.keys() - {lane}:
                    with self.assertRaises(ValueError):
                        verify_transcript(other, marker)

    def test_ci_binds_exact_checkout_and_nonzero_run_attempt(self):
        sha = "a" * 40
        env = {"GITHUB_ACTIONS": "true", "GITHUB_SHA": sha,
               "GITHUB_RUN_ID": "5", "GITHUB_RUN_ATTEMPT": "2"}
        with patch("tools.ddr_foundation_unit_workspace.subprocess.check_output",
                   side_effect=[sha + "\n", b""]):
            self.assertEqual(checkout_provenance(ROOT, env), (sha, False))
        for overrides, status in (({"GITHUB_SHA": "b" * 40}, b""),
                                  ({"GITHUB_RUN_ATTEMPT": ""}, b""),
                                  ({"GITHUB_RUN_ATTEMPT": "0"}, b""),
                                  ({}, b" M changed\n")):
            with self.subTest(overrides=overrides, status=status), patch(
                    "tools.ddr_foundation_unit_workspace.subprocess.check_output",
                    side_effect=[sha + "\n", status]), self.assertRaises(ValueError):
                checkout_provenance(ROOT, {**env, **overrides})
