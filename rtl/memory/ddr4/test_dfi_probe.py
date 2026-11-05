"""Fail-closed selected DFI/BankModel probes and modeled timing tests."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dfi_probe_contract import signal_names, verify_generated_signals, write_control_file, top_level_port_names
from dfi_probe import DFIProbe
from dfi_latency_report import calculate_internal


def idle_phases():
    return [{
        "cs_n": 1, "act_n": 1, "ras_n": 1, "cas_n": 1,
        "we_n": 1, "bank": 0, "address": 0,
        "rddata_en": 0, "rddata_valid": 0, "wrdata_en": 0,
    } for _ in range(4)]


def idle_banks():
    return [{"read": 0, "write_port_we": 0} for _ in range(16)]


def mk_event(kind, cycle, **fields):
    return {"kind": kind, "time_ps": cycle * 10000,
            "test_phase": "traffic", **fields}


class GeneratedProbeContractTests(unittest.TestCase):
    def test_expose_only_selected_nets(self):
        names = signal_names()
        self.assertEqual(len(names), 72)
        self.assertEqual(len(set(names)), 72)
        self.assertFalse(any("mem" == n or "_mem" in n for n in names))
        self.assertIn("soc_ddrphy_dfi_p3_rddata_valid", names)
        self.assertIn("soc_ddrphy_bankmodel15_write_port_we", names)

    def test_actual_declaration_shape_contract(self):
        lines = ["module soc_ddr4_sim (input clk);"]
        lines += [f"wire {name};" for name in signal_names()]
        lines += ["endmodule"]
        text = "\n".join(lines)
        self.assertEqual(verify_generated_signals(text), signal_names())
        with self.assertRaisesRegex(ValueError, "contract changed"):
            verify_generated_signals(text.replace("wire soc_ddrphy_dfi_p0_cs_n;", ""))

    def test_only_declared_top_level_pins_get_rw_access(self):
        text = ("module soc_ddr4_sim (input wire clk, input wire sim_trace, "
                "output wire init_done);\n"
                "wire hidden_storage;\nendmodule\n")
        ports = top_level_port_names(text)
        self.assertEqual(ports, ["clk", "sim_trace", "init_done"])
        self.assertNotIn("hidden_storage", ports)
        with self.assertRaisesRegex(ValueError, "unreviewed"):
            top_level_port_names(text.replace("input wire clk, ", ""))

    def test_generated_verilator_control_has_no_global_public(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            verilog = root / "gen.v"
            verilog.write_text("module soc_ddr4_sim (input clk);\n" +
                               "".join("wire " + n + ";\n" for n in signal_names()) +
                               "endmodule\n")
            ctl = write_control_file(verilog, root / "dfi.vlt")
            data = ctl.read_text()
            self.assertEqual(data.count("public_flat_rd"), 72)
            self.assertNotIn("--public-flat-rw", data)
            # Explicit port RW visibility is safe; internal arrays stay private.
            self.assertEqual(data.count("public_flat_rw -module"), 1)
            self.assertIn('public_flat_rw -module "soc_ddr4_sim" -var "clk"', data)
            self.assertNotIn('public_flat_rw -module "soc_ddr4_sim" -var "soc_ddrphy', data)
            self.assertTrue((root / "ddr4_probe_contract.json").is_file())


class DFIModelProbeTests(unittest.TestCase):
    def test_actual_dfi_commands_and_bank_storage_access(self):
        with tempfile.TemporaryDirectory() as d:
            probe = DFIProbe(Path(d))
            phases, banks = idle_phases(), idle_banks()
            # READ uses !CS && ACT_N && RAS_N && !CAS_N && WE_N
            phases[0].update(cs_n=0, act_n=1, ras_n=1, cas_n=0,
                             we_n=1, bank=3, address=0x40,
                             rddata_en=1)
            banks[3]["read"] = 1
            probe.record(5000, phases, banks, "traffic", 10000)
            phases, banks = idle_phases(), idle_banks()
            phases[2].update(rddata_valid=1)
            probe.record(15000, phases, banks, "traffic", 10000)
            phases, banks = idle_phases(), idle_banks()
            phases[1].update(cs_n=0, act_n=1, ras_n=1, cas_n=0,
                             we_n=0, bank=2, wrdata_en=1)
            banks[2]["write_port_we"] = 0b111
            probe.record(25000, phases, banks, "traffic", 10000)
            summary = probe.finish("pass")
            self.assertEqual(summary["counters"]["dfi_read"], 1)
            self.assertEqual(summary["counters"]["bankmodel_read"], 1)
            self.assertEqual(summary["counters"]["dfi_rddata_valid"], 1)
            self.assertEqual(summary["counters"]["dfi_write"], 1)
            self.assertEqual(summary["counters"]["bankmodel_storage_write"], 1)
            events = [json.loads(x) for x in probe.events_path.read_text().splitlines()]
            self.assertEqual(events[0]["kind"], "probe_start")
            self.assertEqual(events[-1]["kind"], "probe_end")

    def test_lost_clock_edge_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            probe = DFIProbe(Path(d))
            probe.record(5000, idle_phases(), idle_banks(), "pre_init", 10000)
            with self.assertRaisesRegex(AssertionError, "missed"):
                probe.record(25000, idle_phases(), idle_banks(), "pre_init", 10000)
            probe.finish("fail")

    def test_missing_bank_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            probe = DFIProbe(Path(d))
            with self.assertRaisesRegex(AssertionError, "incomplete"):
                probe.record(5000, idle_phases(), [], "traffic", 10000)
            probe.finish("fail")


class InternalLatencyTests(unittest.TestCase):
    def test_serial_model_intervals_are_observed(self):
        axi = {"transactions": [
            {"operation": "read", "id": 1, "address": 0x4000,
             "start_cycle": 10, "end_cycle": 30},
            {"operation": "write", "id": 2, "address": 0x8000,
             "start_cycle": 40, "end_cycle": 60},
        ]}
        events = [
            mk_event("dfi_read", 12, bank=0),
            mk_event("bankmodel_read", 14, bank=0),
            mk_event("dfi_rddata_valid", 18),
            mk_event("dfi_write", 42, bank=1),
            mk_event("bankmodel_storage_write", 44, bank=1),
        ]
        result = calculate_internal(axi, events, 10000)
        self.assertEqual(result["status"], "measured_model_events")
        self.assertEqual(result["internal_stages"]["controller_ar_to_dfi_read"]["avg_cycles"], 2)
        self.assertEqual(result["internal_stages"]["dfi_read_to_bankmodel_access"]["avg_cycles"], 2)
        self.assertEqual(result["internal_stages"]["bankmodel_access_to_dfi_valid"]["avg_cycles"], 4)
        self.assertEqual(result["internal_stages"]["controller_aw_to_dfi_write"]["status"], "unmeasured")

    def test_deferred_dfi_write_does_not_get_false_axi_attribution(self):
        # DFI WRITE from AW1 arrives after B1, during AW2's interval.
        # A time-window algorithm would incorrectly assign it to AW2.
        axi = {"transactions": [
            {"operation":"write", "id":1, "address":0x4000,
             "start_cycle":10, "end_cycle":20},
            {"operation":"write", "id":2, "address":0x8000,
             "start_cycle":22, "end_cycle":35},
        ]}
        events = [
            mk_event("dfi_write", 25, bank=0),
            mk_event("bankmodel_storage_write", 27, bank=0),
            mk_event("dfi_write", 40, bank=1),
            mk_event("bankmodel_storage_write", 42, bank=1),
        ]
        report = calculate_internal(axi, events, 10000)
        self.assertEqual(report["internal_stages"]["controller_aw_to_dfi_write"]["status"],
                         "unmeasured")
        self.assertEqual(report["internal_stages"]["dfi_write_to_bankmodel_storage"]["samples"], 2)
        self.assertEqual(report["internal_stages"]["dfi_write_to_bankmodel_storage"]["avg_cycles"], 2)
        self.assertTrue(all(t["status"] == "unmeasured_axi_dfi_write_attribution"
                            for t in report["transactions"]))
        self.assertTrue(all("first_dfi_command_ps" not in t
                            for t in report["transactions"]))

    def test_ambiguous_same_bank_storage_refuses_fabricated_pairing(self):
        axi = {"transactions": [
            {"operation":"write","id":0,"address":0x0,"start_cycle":10,"end_cycle":20}
        ]}
        events = [
            mk_event("dfi_write", 25, bank=2),
            mk_event("bankmodel_storage_write", 27, bank=2),
            mk_event("bankmodel_storage_write", 28, bank=2),
        ]
        report = calculate_internal(axi, events, 10000)
        self.assertEqual(report["dfi_write_model_pairs"][0]["status"],
                         "unmeasured_ambiguous_bank_storage")
        self.assertEqual(report["internal_stages"]["dfi_write_to_bankmodel_storage"]["status"],
                         "unmeasured")

    def test_overlap_is_explicitly_unmeasured(self):
        axi = {"transactions": [
            {"operation": "read", "start_cycle": 10, "end_cycle": 20,
             "id": 0, "address": 0},
            {"operation": "read", "start_cycle": 15, "end_cycle": 25,
             "id": 1, "address": 8},
        ]}
        result = calculate_internal(axi, [mk_event("dfi_read", 17)], 10000)
        self.assertEqual(result["status"], "measured_model_events")
        self.assertEqual(result["overlapping_axi_attribution"]["status"], "unmeasured")
        self.assertEqual(result["overlapping_axi_attribution"]["ambiguous_transactions"], 2)
        self.assertEqual(result["internal_stages"]["controller_ar_to_dfi_read"]["status"], "unmeasured")
        self.assertTrue(all(txn["status"] == "unmeasured_overlapping_axi_dfi"
                            for txn in result["transactions"]))

    def test_serial_measured_intervals_survive_later_overlapping_requests(self):
        axi = {"transactions": [
            {"operation": "read", "start_cycle": 10, "end_cycle": 20,
             "id": 0, "address": 0x1000},
            {"operation": "read", "start_cycle": 30, "end_cycle": 50,
             "id": 1, "address": 0x2000},
            {"operation": "read", "start_cycle": 34, "end_cycle": 49,
             "id": 2, "address": 0x3000},
        ]}
        events = [
            mk_event("dfi_read", 12, bank=0),
            mk_event("bankmodel_read", 14, bank=0),
            mk_event("dfi_rddata_valid", 16),
            mk_event("dfi_read", 38, bank=1),
            mk_event("dfi_rddata_valid", 43),
        ]
        result = calculate_internal(axi, events, 10000)
        self.assertEqual(result["overlapping_axi_attribution"]["ambiguous_transactions"], 2)
        self.assertEqual(result["internal_stages"]["controller_ar_to_dfi_read"]["samples"], 1)
        self.assertEqual(result["internal_stages"]["controller_ar_to_dfi_read"]["avg_cycles"], 2)
        self.assertEqual(result["transactions"][0]["status"], "first_command_measured")
        self.assertEqual(result["transactions"][1]["status"], "unmeasured_overlapping_axi_dfi")
        self.assertEqual(result["transactions"][2]["status"], "unmeasured_overlapping_axi_dfi")

    def test_missing_internal_command_does_not_fabricate(self):
        axi = {"transactions": [{"operation": "read", "start_cycle": 10,
                                 "end_cycle": 20, "id": 0, "address": 0}]}
        result = calculate_internal(axi, [], 10000)
        self.assertEqual(result["transactions"][0]["status"], "unmeasured_no_dfi_command")
        self.assertEqual(result["internal_stages"]["controller_ar_to_dfi_read"]["status"], "unmeasured")

    def test_bad_interval_rejected(self):
        axi = {"transactions": [{"operation": "read", "start_cycle": 30,
                                 "end_cycle": 20, "id": 0, "address": 0}]}
        with self.assertRaisesRegex(ValueError, "predates"):
            calculate_internal(axi, [], 10000)


if __name__ == "__main__":
    unittest.main()
