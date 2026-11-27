"""Archive identity and evidence must not turn an incomplete probe into PASS."""
import unittest
from unittest.mock import patch

from tools.run_csr_runtime_probe import PASS_MARKER, ROOT, checkout_provenance, verify_simulation


class CsrRuntimeArchiveTests(unittest.TestCase):
    def test_requires_successful_original_test_and_marker(self):
        verify_simulation((1, 0), b"native transcript " + PASS_MARKER + b"\n")
        for result, log in (
            ((1, 1), PASS_MARKER),
            ((0, 0), PASS_MARKER),
            ((2, 0), PASS_MARKER),
            ((1, 0), b""),
            ((1, 0), PASS_MARKER + b"\n" + PASS_MARKER),
        ):
            with self.subTest(result=result, log=log), self.assertRaises(ValueError):
                verify_simulation(result, log)

    def test_checks_exact_clean_ci_checkout_and_explicit_attempt(self):
        env = {"GITHUB_SHA": "a" * 40, "GITHUB_ACTIONS": "true",
               "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "2"}
        with patch("tools.run_csr_runtime_probe.subprocess.check_output",
                   side_effect=[("a" * 40) + "\n", b""]):
            self.assertEqual(checkout_provenance(ROOT, env), ("a" * 40, False))
        for supplied, status in (
            ({**env, "GITHUB_SHA": "b" * 40}, b""),
            ({**env, "GITHUB_RUN_ATTEMPT": ""}, b""),
            ({**env, "GITHUB_RUN_ATTEMPT": "0"}, b""),
            ({**env, "GITHUB_RUN_ID": "0"}, b""),
            (env, b" M fixture\n"),
        ):
            with self.subTest(supplied=supplied, status=status), patch(
                    "tools.run_csr_runtime_probe.subprocess.check_output",
                    side_effect=[("a" * 40) + "\n", status]), self.assertRaises(ValueError):
                checkout_provenance(ROOT, supplied)
