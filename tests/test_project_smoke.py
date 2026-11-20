"""Contract tests for the actual selected RTL boot smoke runner."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from project_smoke import ProjectSmokeError, check_native_boot_log

PHASES = [
    "PHASE init complete: all CPUs ready",
    "hello world from CPU0 (firmware mailbox)",
    "PHASE run complete: all CPUs greeted",
    "PHASE check complete: coordinator observed all peer checks",
    "PASS fullchip: 1 real CPUs, shared NoCs, cold boot, init/run/check",
]


class SelectedProjectNativeSmokeContractTests(unittest.TestCase):
    def test_one_cpu_accepted_only_on_complete_ordered_real_checker_log(self):
        result = check_native_boot_log("\n".join(PHASES), 1)
        self.assertTrue(result["dut_checker_pass"])
        self.assertEqual(result["observed_greetings"], [0])

    def test_two_cpu_model_requires_two_actual_firmware_greetings(self):
        complete = [
            "PHASE init complete: all CPUs ready",
            "hello world from CPU0 (firmware mailbox)",
            "hello world from CPU1 (firmware mailbox)",
            "PHASE run complete: all CPUs greeted",
            "PHASE check complete: coordinator observed all peer checks",
            "PASS fullchip: 2 real CPUs, shared NoCs, cold boot, init/run/check",
        ]
        self.assertEqual(check_native_boot_log("\n".join(complete), 2)["observed_cores"], 2)
        with self.assertRaises(ProjectSmokeError):
            check_native_boot_log("\n".join(complete), 1)
        with self.assertRaises(ProjectSmokeError):
            check_native_boot_log("\n".join(PHASES), 2)

    def test_must_reject_partial_false_or_duplicate_success(self):
        bad = [
            "\n".join(PHASES[:-1]),
            "\n".join(PHASES).replace("PHASE check complete", "PHASE run complete"),
            "\n".join(PHASES + PHASES[-1:]),
            "\n".join(PHASES + ["%Error: RTL failure"]),
            "\n".join(PHASES + ["FAIL fullchip timeout"]),
            "\n".join([PHASES[1], PHASES[0], *PHASES[2:]]),
        ]
        for line in bad:
            with self.subTest(log=line[-100:]), self.assertRaises(ProjectSmokeError):
                check_native_boot_log(line, 1)

    def test_runner_reuses_selected_source_contract(self):
        src = (ROOT / "tools/project_smoke.py").read_text()
        self.assertIn("from project_compile import selected", src)
        self.assertIn('compiled.get("filelist_sha256")', src)
        self.assertIn('"simulation_returncode"', src)
        self.assertIn('"ddr_data_qualified": False', src)
        self.assertIn('"pcie_qualified": False', src)
        self.assertIn('"ethernet_qualified": False', src)


if __name__ == "__main__":
    unittest.main()
