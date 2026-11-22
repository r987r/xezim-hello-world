"""Negative tests for fail-closed CPU/BFM replay evidence correlation."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.scenario_replay_audit import audit, verify_replay_input, ReplayAuditError


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
                       "cpu_plan_sha_axi_witness": {
                           "status": "full_sha_observed_on_real_cpu_axi",
                           "plan_sha256": sha, "witness_phys": hex(16 + 0x1000),
                           "accepted_writes": 8, "checked_bytes": 32,
                           "evidence": "original_passive_axi_aw_w_b_not_firmware_self_report",
                           "scenario_action_completion_proven": False},
                       "cpu_action_trace": {
                           "status": "source_selected_cpu_action_driver_observed_on_real_axi",
                           "plan_sha256": sha, "trace_phys": hex(16 + 0x1000 + 32),
                           "action_ids": ["init_source"],
                           "accepted_writes": 2, "checked_bytes": 8,
                           "issued": 1, "driver_done": 1,
                           "evidence": "original_passive_axi_aw_w_b_driver_events_only",
                           "hardware_completion_proven": False},
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

    def test_replay_input_rejects_stale_seed_and_foreign_selected_envelope(self):
        import yaml
        from tools.run_workspace import reserve_run
        from tools.runtime_contract import SCHEMA, PHASES, digest
        from tools.test_identity import relative_path, selected

        root = Path(__file__).resolve().parents[1]
        definition = yaml.safe_load((root / "config/regression.yaml").read_text())["tests"]
        raw = (self.bfm / "scenario-plan.json").read_bytes()
        for target in ("chip-cpu-scenario", "chip-dma-scenario"):
            with self.subTest(target=target):
                base = Path(self.tmp.name) / ".tools/runs"
                files = b"selected/soc_top.sv\n"
                identity = selected(target, definition[target], filelist_bytes=files,
                                    run_id="ci-2345-a2-123456789abc")
                folder = reserve_run(base, identity, plan=definition[target])
                (folder / "sources.f").write_bytes(files)
                plan = folder / ("variant" if target == "chip-cpu-scenario" else "") / "scenario-plan.json"
                plan.parent.mkdir(parents=True, exist_ok=True)
                plan.write_bytes(raw)
                result = {"target": target, "canonical_id": relative_path(identity).as_posix(),
                          "identity_sha256": identity["identity_sha256"], "stage": "all",
                          "passed": True}
                (folder / "result.json").write_text(json.dumps(result))
                payload = {
                    "schema_version": SCHEMA, "target": target, "stage": "all",
                    "source_revision": "a"*40, "adapter": "scenario_dispatch_adapter",
                    "evidence_kind": "selected_definition_not_runtime_execution",
                    "intent": {"target": target, "phases": {p: [] for p in PHASES},
                               "declared_actions": 1},
                    "scenario_plan_sha256": hashlib.sha256(raw).hexdigest(),
                    "identity_sha256": identity["identity_sha256"],
                }
                def save():
                    (folder / "selected-test-plan.json").write_text(json.dumps(
                        {**payload, "plan_sha256": digest(payload)}))
                def verify(seed=12345, source="a"*40, prefix="ci-2345-a2-"):
                    return verify_replay_input(folder, target, seed=seed, plan_bytes=raw,
                                               source_revision=source, run_prefix=prefix)
                save()
                self.assertEqual(verify(), relative_path(identity).as_posix())
                for seed, source in ((12346, "a"*40), (12345, "b"*40)):
                    with self.assertRaisesRegex(ReplayAuditError, "invocation/seed"):
                        verify(seed, source)
                with self.assertRaisesRegex(ReplayAuditError, "invocation/seed"):
                    verify(prefix="ci-2345-a1-")
                (folder / "sources.f").write_bytes(b"unexpected source filelist\n")
                with self.assertRaisesRegex(ReplayAuditError, "invocation/seed"):
                    verify()
                (folder / "sources.f").write_bytes(files)
                payload["identity_sha256"] = "b"*64
                save()
                with self.assertRaisesRegex(ReplayAuditError, "invocation/seed"):
                    verify()

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

    def test_missing_or_modified_full_cpu_plan_sha_axi_witness_is_rejected(self):
        self.cpu_ev.pop("cpu_plan_sha_axi_witness")
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "full SHA"):
            audit(self.cpu, self.bfm)
        self.cpu_ev["cpu_plan_sha_axi_witness"] = {
            "status": "full_sha_observed_on_real_cpu_axi",
            "plan_sha256": "0"*64, "witness_phys": hex(16+0x1000),
            "accepted_writes": 8, "checked_bytes": 32,
            "evidence": "original_passive_axi_aw_w_b_not_firmware_self_report",
            "scenario_action_completion_proven": False}
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "full SHA"):
            audit(self.cpu, self.bfm)

    def test_missing_or_forged_cpu_action_trace_fails_closed(self):
        original = copy.deepcopy(self.cpu_ev["cpu_action_trace"])
        self.cpu_ev.pop("cpu_action_trace")
        self.write()
        with self.assertRaisesRegex(ReplayAuditError, "action dispatch"):
            audit(self.cpu, self.bfm)
        for field, bad in (
            ("action_ids", ["not_selected"]),
            ("accepted_writes", 0),
            ("checked_bytes", 0),
            ("driver_done", 0),
            ("hardware_completion_proven", True),
            ("trace_phys", "0x0"),
        ):
            self.cpu_ev["cpu_action_trace"] = copy.deepcopy(original)
            self.cpu_ev["cpu_action_trace"][field] = bad
            self.write()
            with self.subTest(field=field), self.assertRaisesRegex(
                    ReplayAuditError, "action dispatch"):
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
