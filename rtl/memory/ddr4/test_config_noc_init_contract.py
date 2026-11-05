"""Negative and positive contracts for DDR-B independent Config NoC init."""
import copy
import json
from pathlib import Path
import sys
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_noc_init_contract import compile_transport, config_window


def fixture():
    root = Path(__file__).resolve().parents[3]
    soc = yaml.safe_load((root / "config/soc.yaml").read_text())
    names = (
        "ddrctrl_init_done", "ddrctrl_init_error", "sdram_dfii_control",
        "sdram_dfii_pi0_address", "sdram_dfii_pi0_baddress",
        "sdram_dfii_pi0_command", "sdram_dfii_pi0_command_issue",
    )
    # Synthetic CSR addresses deliberately use a non-zero generated
    # Wishbone offset; actual CSR layout is tested on generated core in CI.
    csr = {"csr_registers": {
        name: {"addr": 0x2000 + i * 4, "type": "rw", "size": 1}
        for i, name in enumerate(names)
    }}
    steps = [
        {"name": "Release reset", "address": 0, "bank": 0,
         "kind": "control", "mask": 12, "upstream_delay_units": 50000},
        {"name": "Bring CKE high", "address": 0, "bank": 0,
         "kind": "control", "mask": 14, "upstream_delay_units": 10000},
    ]
    for i in (3, 6, 5, 4, 2, 1, 0):
        steps.append({"name": f"Load Mode Register {i}", "address": 0x100,
                      "bank": i, "kind": "command", "mask": 15,
                      "upstream_delay_units": 0})
    steps.append({"name": "ZQ Calibration", "address": 1024, "bank": 0,
                  "kind": "command", "mask": 3, "upstream_delay_units": 200})
    plan = {"status": "plan-only-not-executed", "steps": steps}
    return soc, plan, csr


class DDRBConfigNoCContractTests(unittest.TestCase):
    def setUp(self):
        self.soc, self.plan, self.csr = fixture()

    def run_contract(self):
        return compile_transport(self.soc, self.plan, self.csr)

    def test_real_soc_separate_data_and_config_paths(self):
        base, size = config_window(self.soc)
        self.assertEqual(base, 0x40030000)
        self.assertEqual(size, 4096)
        report = self.run_contract()
        self.assertEqual(report["status"], "contract_only_not_driven_in_full_chip")
        self.assertEqual(report["generated_wb_base"], 0x2000)
        self.assertEqual(report["config_plane"],
                         "global_config -> memory0.local_config")
        self.assertIn("independent", report["data_plane"])
        commands = report["actions"]
        self.assertEqual(commands[0]["op"], "config_write32")
        self.assertEqual(commands[0]["config_addr"], base)
        self.assertEqual(commands[0]["wishbone_word_addr"], 0x2000 // 4)
        self.assertEqual(commands[0]["byte_strobes"], 15)
        self.assertEqual(commands[0]["required_axi_response"], "OKAY")
        self.assertEqual(commands[-3]["op"], "config_read32")
        self.assertEqual(commands[-2]["csr"], "ddrctrl_init_error")
        self.assertEqual(commands[-2]["expect_value"], 0)
        self.assertEqual(commands[-1]["csr"], "sdram_dfii_control")
        self.assertEqual(commands[-1]["expect_value"], 1)
        self.assertEqual([x["cycles"] for x in commands if x["op"] == "wait_cycles"],
                         [100000, 20000, 400])

    def test_missing_memory_config_route_fails(self):
        self.soc["networks"]["global_config"]["reachable_subsystems"] = ["compute0"]
        with self.assertRaisesRegex(ValueError, "not reachable"):
            self.run_contract()

    def test_invalid_or_overlapping_ddr_csr_window_fails(self):
        self.soc["address_map"]["config"] = [
            x for x in self.soc["address_map"]["config"]
            if x["name"] != "memory0.ctrl"
        ]
        with self.assertRaisesRegex(ValueError, "exist exactly once"):
            self.run_contract()

    def test_csr_map_exceeding_aperture_fails_closed(self):
        self.csr["csr_registers"]["sdram_dfii_pi0_command_issue"]["addr"] += 4096
        with self.assertRaisesRegex(ValueError, "exceeds Config NoC"):
            self.run_contract()

    def test_explicit_translator_alignment_and_pin_width_checked(self):
        with self.assertRaisesRegex(ValueError, "not aligned"):
            compile_transport(self.soc, self.plan, self.csr,
                              generated_wb_base=0x2004)
        with self.assertRaisesRegex(ValueError, "would truncate"):
            compile_transport(self.soc, self.plan, self.csr,
                              generated_wb_adr_bits=10)
        self.assertEqual(compile_transport(
            self.soc, self.plan, self.csr,
            generated_wb_base=0x2000, generated_wb_adr_bits=12
        )["generated_wb_base_status"], "explicit")

    def test_fabric_width_and_invalid_status_gate_rejected(self):
        self.soc["buses"]["config"]["data_bits"] = 64
        with self.assertRaisesRegex(ValueError, "independent 32-bit"):
            self.run_contract()
        self.soc, self.plan, self.csr = fixture()
        self.csr["csr_registers"]["ddrctrl_init_error"]["type"] = "ro"
        with self.assertRaisesRegex(ValueError, "generated"):
            self.run_contract()

    def test_actions_not_forged_as_executed(self):
        report = self.run_contract()
        self.assertTrue(report["requires_hardware_translator"])
        self.assertTrue(all(x["phase"] == "init" for x in report["actions"]))
        self.assertFalse(any(x.get("status") == "pass" for x in report["actions"]))
        self.assertIn("no RTL wishbone bridge", report["evidence"])


if __name__ == "__main__":
    unittest.main()
