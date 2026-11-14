"""Prevent a green CI job from misreporting unexecuted Cocotb tests."""
import unittest

from tools.ci_require_cocotb import require_passing_cocotb


class CocotbResultGateTests(unittest.TestCase):
    def test_success_requires_executed_test(self):
        self.assertEqual(
            require_passing_cocotb("TESTS=2 PASS=2 FAIL=0 SKIP=0"), (2, 2)
        )

    def test_import_failure_with_zero_simulator_exit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "failed import"):
            require_passing_cocotb(
                "CRITICAL cocotb.regression Failed to import module test_pcie_core "
                "No module named 'cocotbext'\nVerilog $finish\n"
            )

    def test_missing_summary_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            require_passing_cocotb("Verilator: build succeeded\nVerilog $finish")

    def test_multiple_summaries_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            require_passing_cocotb(
                "TESTS=1 PASS=1 FAIL=0 SKIP=0\nTESTS=1 PASS=1 FAIL=0 SKIP=0"
            )

    def test_failed_or_skipped_or_empty_test_is_rejected(self):
        for text in (
            "TESTS=0 PASS=0 FAIL=0 SKIP=0",
            "TESTS=2 PASS=1 FAIL=1 SKIP=0",
            "TESTS=2 PASS=1 FAIL=0 SKIP=1",
            "TESTS=2 PASS=1 FAIL=0 SKIP=0",
        ):
            with self.subTest(text=text), self.assertRaisesRegex(
                ValueError, "unqualified Cocotb tests"
            ):
                require_passing_cocotb(text)


if __name__ == "__main__":
    unittest.main()
