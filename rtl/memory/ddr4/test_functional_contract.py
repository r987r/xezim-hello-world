"""Standalone Wishbone DDR4 initialization script negative tests (no HDL needed)."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from init_plan import wishbone_script


class DDR4CSRScriptTests(unittest.TestCase):
    def setUp(self):
        names = (
            "ddrctrl_init_done", "ddrctrl_init_error", "sdram_dfii_control",
            "sdram_dfii_pi0_address", "sdram_dfii_pi0_baddress",
            "sdram_dfii_pi0_command", "sdram_dfii_pi0_command_issue",
        )
        self.csr = {"csr_registers": {
            name: {"addr": i * 4, "type": "rw", "size": 1}
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
        steps += [{"name": "ZQ Calibration", "address": 1024, "bank": 0,
                   "kind": "command", "mask": 3, "upstream_delay_units": 200}]
        self.plan = {"status": "plan-only-not-executed", "steps": steps}

    def test_normal_sequence_and_status_handoff(self):
        ops = wishbone_script(self.plan, self.csr, delay_multiplier=2)
        writes = [x for x in ops if x["op"] == "write"]
        self.assertEqual(writes[0]["csr"], "ddrctrl_init_done")
        self.assertEqual(writes[0]["value"], 0)
        self.assertEqual(writes[1]["csr"], "ddrctrl_init_error")
        self.assertEqual(writes[2]["csr"], "sdram_dfii_control")
        self.assertEqual(writes[2]["value"], 14)
        self.assertEqual(writes[-2]["csr"], "sdram_dfii_control")
        self.assertEqual(writes[-2]["value"], 1)
        self.assertEqual(writes[-1]["csr"], "ddrctrl_init_done")
        self.assertEqual(writes[-1]["value"], 1)
        self.assertEqual(sum(1 for w in writes if w["csr"] == "sdram_dfii_pi0_command_issue"), 8)
        self.assertEqual([w["cycles"] for w in ops if w["op"] == "wait"], [100000, 20000, 400])

    def test_addresses_come_from_generated_csr_map(self):
        self.csr["csr_registers"]["sdram_dfii_pi0_command"]["addr"] = 0x1234
        ops = wishbone_script(self.plan, self.csr)
        self.assertTrue(any(x.get("byte_address") == 0x1234 and x["op"] == "write" for x in ops))

    def test_reject_incomplete_mode_sequence(self):
        self.plan["steps"].pop(2)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            wishbone_script(self.plan, self.csr)

    def test_reject_alias_csr(self):
        self.csr["csr_registers"]["sdram_dfii_control"]["addr"] = 0
        with self.assertRaisesRegex(ValueError, "alias"):
            wishbone_script(self.plan, self.csr)

    def test_reject_unaligned_csr(self):
        self.csr["csr_registers"]["sdram_dfii_control"]["addr"] = 3
        with self.assertRaisesRegex(ValueError, "invalid generated"):
            wishbone_script(self.plan, self.csr)

    def test_reject_status_not_writable(self):
        self.csr["csr_registers"]["ddrctrl_init_done"]["type"] = "ro"
        with self.assertRaisesRegex(ValueError, "ddrctrl_init_done"):
            wishbone_script(self.plan, self.csr)

    def test_reject_bad_control_step(self):
        self.plan["steps"][1]["kind"] = "unsupported"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            wishbone_script(self.plan, self.csr)

    def test_reject_invalid_delay_scale(self):
        with self.assertRaisesRegex(ValueError, "multiplier"):
            wishbone_script(self.plan, self.csr, delay_multiplier=1)


if __name__ == "__main__":
    unittest.main()
