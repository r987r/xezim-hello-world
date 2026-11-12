"""Unit-negative tests: virtual SystemRDL DDR4 MRs and observed DFI MRS.

No simulator or external CSR toolchain required. The separate CSR workflow
compiles the SystemRDL with the project's pinned compiler.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mrs_check import MRValidationError, ORDER, RDL, catalog, expected_mrs, verify_capture, verify_observed
from dfi_probe import DFIProbe


def fixture():
    layout = catalog()
    commands = []
    for i, reg in enumerate(ORDER):
        value = (1 << layout["registers"][reg]["fields"][0]["lsb"])
        commands.append({"name": f"Load Mode Register {reg}", "bank": reg,
                         "address": value, "kind": "command", "mask": 15})
    plan = {"status": "plan-only-not-executed", "steps": commands}
    events = [
        {"kind": "dfi_mrs", "bank": r["bank"], "address": r["address"],
         "dfi_phase": 0, "test_phase": "initialization",
         "cycle": i * 30 + 100, "time_ps": i * 300000 + 1000000}
        for i, r in enumerate(commands)
    ]
    events += [{"kind": "dfi_read", "time_ps": 3000000, "test_phase": "traffic"}]
    return plan, events


class DDR4MRContract(unittest.TestCase):
    def test_virtual_systemrdl_layout(self):
        layout = catalog()
        self.assertEqual(list(sorted(layout["registers"])), list(range(7)))
        self.assertTrue(layout["kind"].endswith("not_mmio"))
        self.assertEqual(layout["registers"][0]["fields"][0]["name"], "burst_length")
        self.assertEqual(layout["registers"][5]["fields"][0]["mask"], 1 << 10)
        self.assertEqual(len(layout["rdl_sha256"]), 64)

    def test_correct_observed_sequence(self):
        plan, events = fixture()
        result = verify_observed(plan, events)
        self.assertEqual(result["observed_mrs_count"], 7)
        self.assertEqual([r["mr"] for r in result["records"]], list(ORDER))
        self.assertFalse(result["model_enforces_mr_state"])
        self.assertFalse(result["jedec_mrs_timing_verified"])

    def test_corrupted_mr_fails(self):
        plan, events = fixture()
        events[3]["address"] ^= 1
        with self.assertRaisesRegex(MRValidationError, "MRS mismatch"):
            verify_observed(plan, events)

    def test_missing_mrs_fails(self):
        plan, events = fixture()
        del events[1]
        with self.assertRaisesRegex(MRValidationError, "observed 6"):
            verify_observed(plan, events)

    def test_extra_mrs_fails(self):
        plan, events = fixture()
        events.append(copy.deepcopy(events[1]))
        with self.assertRaisesRegex(MRValidationError, "observed 8"):
            verify_observed(plan, events)

    def test_order_fails(self):
        plan, events = fixture()
        events[1], events[2] = events[2], events[1]
        with self.assertRaisesRegex(MRValidationError, "MRS mismatch"):
            verify_observed(plan, events)

    def test_wrong_phase_fails(self):
        plan, events = fixture()
        events[2]["dfi_phase"] = 1
        with self.assertRaisesRegex(MRValidationError, "wrong DFI phase"):
            verify_observed(plan, events)

    def test_early_access_fails(self):
        plan, events = fixture()
        events[-1]["time_ps"] = 1000001
        with self.assertRaisesRegex(MRValidationError, "before MR"):
            verify_observed(plan, events)

    def test_illegal_plan_bits_fail(self):
        plan, events = fixture()
        plan["steps"][0]["address"] |= 0x8000
        with self.assertRaisesRegex(MRValidationError, "invalid command"):
            verify_observed(plan, events)

    def test_model_capture_reconciled(self):
        plan, events = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "plan.json").write_text(json.dumps(plan))
            start = {"kind": "probe_start", "scope": "fullchip_litedram_dfi_sim"}
            end = {"kind": "probe_end", "status": "pass", "sampled_cycles": 1000}
            raw = [start, *events, end]
            (folder / "ddr4_dfi_events.jsonl").write_text(
                "\n".join(json.dumps(x) for x in raw) + "\n")
            (folder / "ddr4_dfi_summary.json").write_text(
                json.dumps({"status": "pass", "sampled_cycles": 1000,
                            "counters": {"dfi_mrs": 7}}))
            result = verify_capture(folder, folder/"plan.json", folder/"mrs.json")
            self.assertEqual(result["capture_scope"], "fullchip_litedram_dfi_sim")
            self.assertTrue((folder/"mrs.json").is_file())
            summary = json.loads((folder/"ddr4_dfi_summary.json").read_text())
            summary["counters"]["dfi_mrs"] = 6
            (folder/"ddr4_dfi_summary.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(MRValidationError, "counters mismatch"):
                verify_capture(folder, folder/"plan.json")

    def test_passive_capture_classifies_mrs_before_act(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = DFIProbe(Path(tmp))
            idle = {"cs_n": 1, "act_n": 1, "ras_n": 1,
                    "cas_n": 1, "we_n": 1, "bank": 0, "address": 0,
                    "rddata_en": 0, "rddata_valid": 0, "wrdata_en": 0}
            phases = [dict(idle) for _ in range(4)]
            # Even if ACT_N is low, all-low RAS/CAS/WE is MRS.
            phases[0].update(cs_n=0, act_n=0, ras_n=0, cas_n=0,
                             we_n=0, bank=3, address=0x40)
            banks = [{"read": 0, "write_port_we": 0} for _ in range(16)]
            probe.record(10000, phases, banks, "initialization", 10000)
            summary = probe.finish("pass")
            kinds = [json.loads(s) for s in
                     (Path(tmp)/"ddr4_dfi_events.jsonl").read_text().splitlines()]
            self.assertEqual(summary["counters"]["dfi_mrs"], 1)
            self.assertFalse(any(e["kind"] == "dfi_activate" for e in kinds))
            observed = next(e for e in kinds if e["kind"] == "dfi_mrs")
            self.assertEqual((observed["bank"], observed["address"]), (3, 0x40))

    def test_missing_rdl_bits_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = RDL.read_text().replace("mr5 @0x14;", "mr5 @0x44;")
            rdl = Path(tmp)/"bad.rdl"
            rdl.write_text(text)
            with self.assertRaisesRegex(MRValidationError, "virtual offset"):
                catalog(rdl)


if __name__ == "__main__":
    unittest.main()
