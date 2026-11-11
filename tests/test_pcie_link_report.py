"""Test isolated PCIe evidence without inventing host/device transaction proof."""
from __future__ import annotations
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from tools.pcie_link_report import summarize, render, export_shared_protocol_timeline

PLAN="a"*64
GOOD=f"""PCIE_EP_SIM_FAST_LTSSM: ENABLED timer_divider=512 min_tx_ts1=16 1ms_cycles=195
PCIE_SCN_DRIVER: plan={PLAN} action=train_link stage=issued
PCIE_DEVICE_PRELINK: committed BAR0 size=00001000 target=12000000 mask=fffff000
PCIE_DEVICE_PRELINK: LTSSM enable released after BAR commit
PCIE_EP_STATE: 000000 -> 000041 at 244000
PCIE_TRACE: receiver-detect request
PCIE_EP_STATE: 000041 -> 000061 at 18996000
PCIE_TRACE: PHY receiver present
PCIE_PIPE_WIDTH_MATCH: RC 16-bit and EP 16-bit PIPE @125MHz
PCIE_EP_STATE: 000061 -> 000002 at 19052000
PCIE_EP_STATE: 000002 -> 000022 at 19060000
PCIE_EP_STATE: 000022 -> 000042 at 20044000
PCIE_EP_STATE: 000042 -> 000023 at 21396000
PCIE_EP_STATE: 000023 -> 000043 at 21644000
PCIE_EP_STATE: 000043 -> 000083 at 22220000
PCIE_EP_STATE: 000083 -> 000063 at 22348000
PCIE_EP_STATE: 000063 -> 0000a3 at 22924000
PCIE_EP_STATE: 0000a3 -> 0000e3 at 24140000
PCIE_ENDPOINT_L0: original endpoint asserts link_up after receiver-detect and bidirectional PIPE traffic
PCIE_HOST_L0: original InitLink(1) returned for action=train_link
PCIE_SCN_DRIVER: plan={PLAN} action=train_link stage=driver_done
"""

class PcieLinkEvidenceTests(unittest.TestCase):
    def test_independent_l0_observed_and_other_claims_unmeasured(self):
        row=summarize(GOOD)
        self.assertTrue(row["qualified_digital_link_l0"],row["issues"])
        self.assertEqual(row["scenario_plan_sha256"],PLAN)
        self.assertTrue(row["host_l0_observed"])
        self.assertTrue(row["endpoint_l0_observed"])
        self.assertGreater(row["observed_endpoint_state_transitions"],5)
        self.assertEqual(row["capabilities"]["host_bar_enumeration"],"unmeasured")
        self.assertEqual(row["capabilities"]["noc_axi_transfer"],"unmeasured")
        html=render(row)
        self.assertIn("No invented timings",html)
        self.assertIn("unmeasured",html)

    def test_negative_missing_independent_l0(self):
        for marker in ("PCIE_ENDPOINT_L0:", "PCIE_HOST_L0:", "PCIE_TRACE: PHY receiver present",
                       "PCIE_PIPE_WIDTH_MATCH:", "PCIE_SCN_DRIVER:"):
            with self.subTest(marker=marker):
                lines=[l for l in GOOD.splitlines() if not l.startswith(marker)]
                result=summarize("\n".join(lines))
                self.assertFalse(result["qualified_digital_link_l0"])

    def test_negative_invalid_timing_and_broken_order(self):
        for value in (
            GOOD.replace("timer_divider=512","timer_divider=1"),
            GOOD.replace("min_tx_ts1=16","min_tx_ts1=1024"),
            GOOD.replace("PCIE_DEVICE_PRELINK: LTSSM enable released after BAR commit",
                         "PCIE_DEVICE_PRELINK: LTSSM enable released after BAR commit\n"
                         "PCIE_DEVICE_PRELINK: LTSSM enable released after BAR commit"),
            "\n".join(l for l in GOOD.splitlines() if not l.startswith("PCIE_EP_STATE: 000061 -> 000002") and not l.startswith("PCIE_EP_STATE: 000002 -> 000022")),
            GOOD.replace(f"plan={PLAN} action=train_link stage=driver_done",
                         f"plan={'b'*64} action=train_link stage=driver_done"),
        ):
            with self.subTest(text=value[:80]):
                self.assertFalse(summarize(value)["qualified_digital_link_l0"])

    def test_reuses_existing_protocol_explorer_without_fake_tlp(self):
        with TemporaryDirectory() as temp:
            output=Path(temp)
            report=export_shared_protocol_timeline(summarize(GOOD),output)
            self.assertTrue(report["capture_complete"],report["issues"])
            self.assertTrue((output/"protocol-events.jsonl").is_file())
            self.assertTrue((output/"protocol-transactions.json").is_file())
            self.assertTrue((output/"protocols.html").is_file())
            self.assertGreater(len(report["records"]),4)
            self.assertTrue(all(x["kind"]=="event" and x["operation"]=="ltssm_transition"
                                for x in report["records"]))
            self.assertTrue(all(x["source"]=="pcie0.ltssm" for x in report["records"]))
            self.assertEqual({x["protocol"] for x in report["records"]},{"pcie"})
            self.assertFalse(any(x["kind"]=="transaction" for x in report["records"]))

    def test_no_fake_protocol_timestamps_or_bar_completion(self):
        row=summarize(GOOD)
        host_event=next(e for e in row["events"] if e["kind"]=="host_l0")
        self.assertIsNone(host_event["time_ps"])
        self.assertNotIn("bar_tlp_complete",row["capabilities"])
        self.assertEqual(row["capabilities"]["memory_bytes"],"unmeasured")

if __name__=="__main__":
    unittest.main()
