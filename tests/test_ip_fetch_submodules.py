"""Existing IP fetcher must hydrate only the root-commit-pinned gitlinks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.ip_fetch import hydrate_submodules


class PinSubmoduleTests(unittest.TestCase):
    def test_no_submodules_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("tools.ip_fetch.subprocess.run") as call:
                hydrate_submodules(Path(tmp), [])
            call.assert_not_called()

    def test_unsafe_or_duplicate_names_fail_before_git(self):
        for names in (["../escape"], ["/absolute"], ["a", "a"], ["."], [""]):
            with tempfile.TemporaryDirectory() as tmp:
                with self.subTest(names=names), patch(
                        "tools.ip_fetch.subprocess.run") as run, self.assertRaises(ValueError):
                    hydrate_submodules(Path(tmp), names)
                run.assert_not_called()

    def test_declared_submodule_checked_and_bad_pin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src/verilog-pcie").mkdir(parents=True)
            (root / "src/verilog-pcie/rtl.v").write_text("module rtl; endmodule")
            calls = []
            def runner(args, **kwargs):
                calls.append(args)
                if "status" in args:
                    return SimpleNamespace(stdout=" 1234567 src/verilog-pcie (pinned)\n")
                return SimpleNamespace(stdout="")
            with patch("tools.ip_fetch.subprocess.run", side_effect=runner):
                hydrate_submodules(root, ["src/verilog-pcie"])
            self.assertEqual(len(calls), 3)
            self.assertIn("--recursive", calls[1])
            self.assertEqual(calls[1][-1], "src/verilog-pcie")
            with patch("tools.ip_fetch.subprocess.run", return_value=SimpleNamespace(
                    stdout="+1234567 src/verilog-pcie (drift)\n")):
                with self.assertRaisesRegex(ValueError, "pin"):
                    hydrate_submodules(root, ["src/verilog-pcie"])


if __name__ == "__main__":
    unittest.main()
