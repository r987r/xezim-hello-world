"""Negative tests for fail-closed CPU/BFM replay evidence correlation."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.scenario_replay_audit import audit, ReplayAuditError


class ScenarioReplayAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.cpu = root / "cpu"
        self.bfm = root / "bfm"
        plan = {"schema_version": 1, "kind": "soc_scenario_intent_only",
                "scenario_id": "shared", "seed": 12345, "execution_evidence": None,
                "actions": [{"action_instance_id": "init_source",
                             "args": {"pattern": {"kind": "constant", "seed": 90}}}],
                "allocations": [{"buffer": "src", "phys": 16},
                                {"buffer": "return", "phys": 80},
                                {"buffer": "ddr", "phys": 5368709120}]}
        self.plan = plan
        payload = (json.dumps(plan, sort_keys=True) + "\n").encode()
        sha = hashlib.sha256(payload).hexdigest()
        observed = {"src_ar": 1, "ddr_aw": 1, "ddr_ar": 1, "return_aw": 1}
        self.cpu_ev = {"profile": "real_cpu0_compiled_c", "plan_sha256": sha,
                       "scenario_id": "shared", "scenario_seed": 12345, "executed_pattern_seed": 90, "execution_state": "rtl_observed",
                       "intent_is_not_evidence": True, "cpu_result_checked": True,
                       "observed_cpu_allocations": [16, 80, 5368709120],
                       "observed_dma_axi_counts": observed}
        self.bfm_ev = {"profile": "reset_isolated_cocotb_bfm", "plan_sha256": sha,
                       "scenario_id": "shared", "scenario_seed": 12345, "executed_pattern_seed": 90, "execution_state": "rtl_observed",
                       "intent_is_not_evidence": True, "independently_readback_bytes": 64,
                       "observed_dma_axi_counts": observed}
        self.cpu_result = {"passed": True, "results": [{"passed": True, "exit_code": 0}],
                           "test_flow": {"status": "complete", "passed": True,
                                         "issues": 0, "steps": 6}}
        self.bfm_result = {"passed": True, "results": [{"passed": True, "exit_code": 0}],
                           "test_flow": {"status": "unmeasured", "steps": 0}}
        self.write()

    def write(self):
        for folder, spec, ev, result in (
            (self.cpu, self.plan, self.cpu_ev, self.cpu_result),
            (self.bfm, self.plan, self.bfm_ev, self.bfm_result),
        ):
            folder.mkdir(parents=True, exist_ok=True)
            loc = folder / ("variant/scenario-plan.json" if folder == self.cpu else "scenario-plan.json")
            loc.parent.mkdir(parents=True, exist_ok=True)
            loc.write_text(json.dumps(spec, sort_keys=True) + "\n")
            (folder / "scenario-execution.json").write_text(json.dumps(ev))
            (folder / "result.json").write_text(json.dumps(result))

    def test_correlated_real_cpu_and_bfm_pass(self):
        report = audit(self.cpu, self.bfm)
        self.assertEqual(report["status"], "validated_both_real_rtl_profiles")
        self.assertEqual(report["bfm_test_flow"], "unmeasured")
        self.assertEqual(report["memory_target"], "modeled_ddr_only")

    def test_effective_driver_seed_must_match_source_selected_pattern(self):
        self.cpu_ev["executed_pattern_seed"] = 91
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "driver pattern seed"):
            audit(self.cpu, self.bfm)
        self.cpu_ev["executed_pattern_seed"] = 90
        self.bfm_ev["executed_pattern_seed"] = 91
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "driver pattern seed"):
            audit(self.cpu, self.bfm)

    def test_random_seed_must_match_actual_cpu_and_bfm_rtl_evidence(self):
        self.cpu_ev["scenario_seed"] = 12346
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "seed differs"):
            audit(self.cpu, self.bfm)
        self.cpu_ev["scenario_seed"] = 12345
        self.bfm_ev["scenario_seed"] = 12346
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "seed differs"):
            audit(self.cpu, self.bfm)

    def test_mismatched_intent_rejected_even_when_forged_hash_adjusted(self):
        different = copy.deepcopy(self.plan)
        different["scenario_id"] = "another"
        raw = (json.dumps(different, sort_keys=True) + "\n").encode()
        self.bfm_ev["scenario_id"] = "another"
        self.bfm_ev["plan_sha256"] = hashlib.sha256(raw).hexdigest()
        self.write()
        (self.bfm / "scenario-plan.json").write_bytes(raw)
        with self.assertRaisesRegex(ReplayAuditError, "plans differ"):
            audit(self.cpu, self.bfm)

    def test_missing_axi_handshake_or_forged_result_rejected(self):
        self.cpu_ev["observed_dma_axi_counts"]["ddr_aw"] = 0
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "AXI traffic"):
            audit(self.cpu, self.bfm)
        self.cpu_ev["observed_dma_axi_counts"]["ddr_aw"] = 1
        self.bfm_result["passed"] = False
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "unverified RTL"):
            audit(self.cpu, self.bfm)

    def test_missing_cpu_mmio_or_byte_check_rejected(self):
        self.cpu_ev["observed_cpu_allocations"] = [16, 80, 100]
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "allocation MMIO"):
            audit(self.cpu, self.bfm)
        self.cpu_ev["observed_cpu_allocations"] = [16, 80, 5368709120]
        self.cpu_ev["cpu_result_checked"] = False
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "firmware"):
            audit(self.cpu, self.bfm)

    def test_falsely_claimed_bfm_firmware_steps_rejected(self):
        self.bfm_result["test_flow"] = {"status": "complete", "steps": 6}
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "falsely claims"):
            audit(self.cpu, self.bfm)

    def test_missing_plan_or_evidence_rejected(self):
        (self.cpu / "variant/scenario-plan.json").unlink()
        with self.assertRaisesRegex(ReplayAuditError, "missing scenario intent"):
            audit(self.cpu, self.bfm)
        self.write()
        (self.bfm / "scenario-execution.json").unlink()
        with self.assertRaisesRegex(ReplayAuditError, "invalid or missing JSON"):
            audit(self.cpu, self.bfm)


if __name__ == "__main__":
    unittest.main()
