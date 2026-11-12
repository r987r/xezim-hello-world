"""Test isolated PCIe evidence without inventing host/device transaction proof."""
from __future__ import annotations
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import copy

from tests.test_pcie_bar0_evidence import sample
from tools.pcie_bar0_evidence import check as checked_real_config
from tools.pcie_link_report import summarize, render, render_actions_summary, export_shared_protocol_timeline

PLAN="a"*64
GOOD=f"""PCIE_EP_SIM_FAST_LTSSM: ENABLED timer_divider=512 min_tx_ts1=16 1ms_cycles=195
PCIE_SCN_DRIVER: plan={PLAN} action=train_link stage=issued
PCIE_DEVICE_PRELINK: committed BAR0 size=00001000 target=12000000 mask=fffff000
PCIE_DEVICE_PRELINK: LTSSM enable released after BAR commit
---> Detect Quiet (node 0)
---> Detect Active (node 0)
---> rcvr_idle_status = 0 (node 0)
---> Polling Active (node 0)
PCIE_EP_STATE: 000000 -> 000041 at 244000
PCIE_TRACE: receiver-detect request
PCIE_EP_STATE: 000041 -> 000061 at 18996000
PCIE_TRACE: PHY receiver present
PCIE_PIPE_WIDTH_MATCH: RC 16-bit and EP 16-bit PIPE @125MHz
PCIE_EP_STATE: 000061 -> 000002 at 19052000
PCIE_EP_STATE: 000002 -> 000022 at 19060000
PCIE_PIPE_RC_TO_EP: data=00000204 k=0 idle=0 valid=1 at 19052000
PCIE_PIPE_EP_TO_RC: data=0000e55a k=0 idle=0 valid=1 at 19052000
PCIE_EP_STATE: 000022 -> 000042 at 20044000
---> Polling Config (node 0)
---> Active lanes = 0x0001 (node 0)
---> Configuration Start (node 0)
PCIE_EP_STATE: 000042 -> 000023 at 21396000
PCIE_EP_STATE: 000023 -> 000043 at 21644000
---> Configuration Linkwidth Accept (node 0)
---> Configuration Lanenum Wait (node 0)
PCIE_EP_STATE: 000043 -> 000083 at 22220000
PCIE_EP_STATE: 000083 -> 000063 at 22348000
---> Configuration Lanenum Accept (node 0)
PCIE_EP_STATE: 000063 -> 0000a3 at 22924000
---> Configuration Complete (node 0)
PCIE_EP_STATE: 0000a3 -> 0000e3 at 24140000
PCIE_ENDPOINT_L0: original endpoint asserts link_up after receiver-detect and bidirectional PIPE traffic
---> Configuration Idle (node 0)
---> Configuration exit to L0 (node 0)
PCIE_HOST_L0: original InitLink(1) returned for action=train_link
PCIE_SCN_DRIVER: plan={PLAN} action=train_link stage=driver_done
PCIE_EP_STATE: 0000e3 -> 000005 at 25556000
"""

class PcieLinkEvidenceTests(unittest.TestCase):
    def test_independent_l0_observed_and_other_claims_unmeasured(self):
        row=summarize(GOOD)
        self.assertTrue(row["qualified_digital_link_l0"],row["issues"])
        self.assertEqual(row["scenario_plan_sha256"],PLAN)
        self.assertTrue(row["host_l0_observed"])
        self.assertTrue(row["endpoint_l0_observed"])
        self.assertGreater(row["observed_endpoint_state_transitions"],5)
        self.assertGreater(row["observed_host_ltssm_stages"],9)
        self.assertEqual(row["pipe_traffic_samples"],{"host_to_device":1,"device_to_host":1})
        self.assertTrue(row["host_ltssm_stage_trace_observed"])
        host=[x for x in row["events"] if x["kind"]=="host_ltssm"]
        self.assertTrue(all(x["time_ps"] is None for x in host))
        self.assertIn("Configuration exit to L0",[x["stage"] for x in host])
        ep=[x for x in row["events"] if x["kind"]=="endpoint_ltssm"]
        self.assertEqual(ep[-1]["stage"],"L0")
        self.assertEqual(row["capabilities"]["host_bar_enumeration"],"unmeasured")
        self.assertEqual(row["capabilities"]["noc_axi_transfer"],"unmeasured")
        html=render(row)
        self.assertIn("No invented timings",html)
        self.assertIn("Root Complex / host LTSSM",html)
        self.assertIn("Endpoint RTL LTSSM",html)
        self.assertIn("Configuration.Linkwidth.Accept",html)
        self.assertIn("Bidirectional observed PIPE data",html)
        self.assertIn("unmeasured",html)

    def test_host_stage_missing_or_out_of_order_and_missing_pipe_fail_closed(self):
        for edited in (
            GOOD.replace("---> Polling Config (node 0)\n",""),
            GOOD.replace("---> Configuration exit to L0 (node 0)\n",""),
            GOOD.replace("---> Active lanes = 0x0001", "---> Active lanes = 0x0000"),
            GOOD.replace("---> Configuration Start (node 0)",
                         "---> Configuration IdLE (node 0)"),
            GOOD.replace("PCIE_PIPE_EP_TO_RC:", "PCIE_UNUSED_EP_TO_RC:"),
            GOOD.replace("PCIE_PIPE_RC_TO_EP:", "PCIE_UNUSED_RC_TO_EP:"),
            GOOD.replace("---> Detect Quiet (node 0)\n", "").replace(
                         "---> Polling Active (node 0)",
                         "---> Polling Active (node 0)\n---> Detect Quiet (node 0)"),
        ):
            with self.subTest(replacement=edited[-100:]):
                self.assertFalse(summarize(edited)["qualified_digital_link_l0"])

    def test_actions_webpage_summary_exposes_both_original_ltssms(self):
        row=summarize(GOOD)
        markdown=render_actions_summary(row)
        self.assertIn("Host stage (original C model)",markdown)
        self.assertIn("Endpoint stage (original RTL)",markdown)
        self.assertIn("Detect Quiet",markdown)
        self.assertIn("Polling.Active",markdown)
        self.assertIn("Configuration exit to L0",markdown)
        self.assertIn("| L0 |",markdown)
        self.assertIn("Not emitted",markdown)
        self.assertIn("25556.000",markdown)
        self.assertNotIn("NoC SRAM writes qualified",markdown)

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

    def test_only_real_ltssm_l0_qualifies_not_early_link_up(self):
        # OpenPCIe link_up_o can assert while LTSSM is still in Config.Idle.
        early = GOOD.replace("PCIE_EP_STATE: 0000e3 -> 000005 at 25556000\n", "")
        row = summarize(early)
        self.assertFalse(row["qualified_digital_link_l0"])
        self.assertFalse(row["endpoint_ltssm_l0_observed"])
        self.assertTrue(row["endpoint_l0_observed"])

        # Re-entry into recovery after L0 is a real bug, not report noise.
        retrain = GOOD + "PCIE_EP_STATE: 000005 -> 000024 at 25600000\n"
        row = summarize(retrain)
        self.assertFalse(row["qualified_digital_link_l0"])
        self.assertIn("endpoint not in actual LTSSM ST_L0", str(row["issues"]))

        stable = summarize(GOOD)
        self.assertTrue(stable["qualified_digital_link_l0"],stable["issues"])
        self.assertTrue(stable["endpoint_ltssm_l0_observed"])

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

    def test_source_qualified_config_tlps_share_unified_protocol_view(self):
        # These log fixtures exercise the exporter only; hardware proof
        # remains the actual cross-provider Verilator job and RC callbacks.
        checked=checked_real_config(sample())
        self.assertTrue(checked["qualified_over_link_bar0"],checked["issues"])
        with TemporaryDirectory() as temp:
            report=export_shared_protocol_timeline(
                summarize(GOOD),Path(temp),bar_evidence=checked,mode="bar0")
            self.assertTrue(report["capture_complete"],report["issues"])
            self.assertEqual(report["run"]["target"],"pcie-bar0-isolated")
            rows=[row for row in report["records"]
                  if row["source"]=="pcie0.config"]
            self.assertEqual([x["operation"] for x in rows],
                             ["cfg_wr0","cfg_rd0"]*3)
            self.assertEqual([x["id"] for x in rows],list(range(6)))
            self.assertTrue(all(x["kind"]=="transaction" and
                                x["status"]=="complete" and
                                x["fields"]["host_completion_observed"]
                                for x in rows))
            self.assertEqual(rows[2]["fields"]["axi_accepted_wdata"],
                             "0x80001000")
            self.assertEqual(rows[1]["fields"]["endpoint_cpld_payload"],
                             "0xfffff000")
            self.assertEqual(rows[0]["start_ps"],500)
            self.assertEqual(rows[0]["end_ps"],800)
            self.assertEqual(rows[0]["fields"]["time_scope"],
                             "endpoint_accepted_pins_ps")
            self.assertFalse(any(row["operation"]=="mem_write"
                                 for row in rows))
            html=(Path(temp)/"protocols.html").read_text()
            self.assertIn("cfg_wr0",html)
            self.assertIn("pcie0.config",html)

    def test_missing_config_provenance_cannot_be_promoted_to_view(self):
        checked=checked_real_config(sample())
        for field,value in (("endpoint_first_rx_ps",None),
                            ("endpoint_last_cpl_ps",None),
                            ("host_completion_observed",False)):
            bad=copy.deepcopy(checked)
            bad["transactions"][0][field]=value
            with self.subTest(field=field),TemporaryDirectory() as temp:
                with self.assertRaisesRegex(ValueError,
                                            "accepted pins and RC completion"):
                    export_shared_protocol_timeline(
                        summarize(GOOD),Path(temp),bar_evidence=bad,mode="bar0")
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,"required"):
                export_shared_protocol_timeline(
                    summarize(GOOD),Path(temp),mode="bar0")

    def test_no_fake_protocol_timestamps_or_bar_completion(self):
        row=summarize(GOOD)
        host_event=next(e for e in row["events"] if e["kind"]=="host_l0")
        self.assertIsNone(host_event["time_ps"])
        self.assertNotIn("bar_tlp_complete",row["capabilities"])
        self.assertEqual(row["capabilities"]["memory_bytes"],"unmeasured")

if __name__=="__main__":
    unittest.main()
