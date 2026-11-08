"""#34 fail-closed checks: one-run Ethernet -> LiteDRAM -> iDMA -> PCIe/TX."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

from dv.integration.combined34_scoreboard import check_accepted_axi, write_pass, verify_controller

BASES = {
    "ethernet0.sram": (0x70000000, 0x4000),
    "ethernet0.ctrl": (0x40060000, 0x1000),
    "memory0.ddr0": (0x140000000, 0x2000000),
    "pcie0.sram": (0x60000000, 0x4000),
    "compute1.sram": (0x20000000, 0x4000),
}

def row(monitor, channel, address=0):
    return {"monitor": monitor, "channel": channel, "fields": {"addr": hex(address)}}

def good_events():
    eth=BASES["ethernet0.sram"][0]
    ddr=BASES["memory0.ddr0"][0]
    pcie=BASES["pcie0.sram"][0]
    peer=BASES["compute1.sram"][0]
    ctrl=BASES["ethernet0.ctrl"][0]
    return [
        row("compute0_local_config.cpu", "aw", ctrl + 0x20),
        row("compute0_local_data.cpu", "aw", eth + 0x1000),
        row("compute0_local_data.cpu", "ar", eth + 0x1200),
        row("ethernet0_local_data.packet_dma", "ar", eth + 0x1000),
        row("ethernet0_local_data.packet_dma", "aw", ddr + 0x1000),
        row("compute0_local_data.dma", "ar", ddr + 0x1000),
        row("compute0_local_data.dma", "aw", pcie + 0x600),
        row("compute0_local_data.dma", "aw", eth + 0x2100),
        row("compute0_local_data.dma", "aw", peer + 0x2000),
        row("ethernet0_local_data.packet_dma", "ar", eth + 0x2100),
        row("ethernet0_local_data.packet_dma", "b"),
        row("compute0_local_data.dma", "b"),
    ]

def controller():
    numbers = {
        "controller_axi_aw_count": 3, "controller_axi_b_count": 3,
        "controller_axi_ar_count": 4, "controller_axi_rlast_count": 4,
        "dfi_read_count": 5, "dfi_write_count": 6,
        "bank_storage_write_count": 7,
        "ddr_init_done_o": 1, "ddr_init_error_o": 0,
    }
    return N(**{key:N(value=value) for key,value in numbers.items()})

class CompositeProofTest(unittest.TestCase):
    def test_success_has_all_ten_real_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            plan=Path(directory)/"plan.json"
            (plan.parent/"axi-events.jsonl").write_text("{}\n")
            with patch("dv.integration.combined34_scoreboard.selected_aperture",
                       side_effect=lambda name, plane, plan_path: BASES[name]), \
                 patch("tools.axi_report.read_events", return_value=(good_events(), [])):
                actual=check_accepted_axi(plan)
                self.assertEqual(len(actual),12)
                self.assertTrue(all(actual.values()))

    def test_missing_actual_ethernet_ddr_write_cannot_pass(self):
        events=[r for r in good_events() if not (
            r["monitor"]=="ethernet0_local_data.packet_dma" and
            r["channel"]=="aw")]
        with tempfile.TemporaryDirectory() as directory:
            plan=Path(directory)/"plan.json"
            (plan.parent/"axi-events.jsonl").write_text("{}\n")
            with patch("dv.integration.combined34_scoreboard.selected_aperture",
                       side_effect=lambda name, plane, plan_path: BASES[name]), \
                 patch("tools.axi_report.read_events", return_value=(events, [])):
                with self.assertRaisesRegex(AssertionError, "eth_rx_to_ddr"):
                    check_accepted_axi(plan)

    def test_incomplete_passive_capture_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            plan=Path(directory)/"plan.json"
            (plan.parent/"axi-events.jsonl").write_text("{}\n")
            with patch("dv.integration.combined34_scoreboard.selected_aperture",
                       side_effect=lambda name, plane, plan_path: BASES[name]), \
                 patch("tools.axi_report.read_events",
                       return_value=(good_events(), ["capture_overflow"])):
                with self.assertRaisesRegex(AssertionError, "incomplete"):
                    check_accepted_axi(plan)

    def test_controller_rejects_absent_bank_write_or_mismatched_b(self):
        counts={"dfi_read":5,"dfi_write":6,"bankmodel_storage_write":7}
        self.assertEqual(verify_controller(controller(), counts)
                         ["controller_axi_b"],3)
        bad=controller()
        bad.controller_axi_b_count.value=0
        with self.assertRaisesRegex(AssertionError, "controller"):
            verify_controller(bad,counts)
        with self.assertRaisesRegex(AssertionError, "controller"):
            verify_controller(controller(),{**counts,"bankmodel_storage_write":0})

    def test_pass_evidence_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"combined34_evidence.json"
            plan={"target":"chip-ethernet-ddr-pcie","identity":{"identity_sha256":"a"*64},"seed":1}
            write_pass(path,plan,{"eth_rx":1},{"dfi":1},{"tlp":1},b"abc")
            result=json.loads(path.read_text())
            self.assertEqual(result["status"],"pass")
            self.assertTrue(result["one_run_only"])
            with self.assertRaisesRegex(AssertionError,"preexisting"):
                write_pass(path,plan,{"eth_rx":1},{"dfi":1},{"tlp":1},b"abc")

if __name__=="__main__":
    unittest.main()
