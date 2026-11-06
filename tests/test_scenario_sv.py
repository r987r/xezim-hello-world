"""SCN-3 tests for source-neutral SV ABI, deterministic emission and driver logs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

import yaml

from dv.common.scenario import canonical_json, resolve_scenario
from tools.scenario_sv import SVContractError, audit_sv_transcript, load_plan, render_package

ROOT = Path(__file__).resolve().parents[1]


class ScenarioSystemVerilogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        spec = json.loads((ROOT / "config/scenarios/dma-roundtrip.json").read_text())
        cls.resolved = resolve_scenario(spec, cfg)
        cls.raw = canonical_json(cls.resolved).encode("ascii")
        cls.sha = hashlib.sha256(cls.raw).hexdigest()
        cls.first = cls.resolved["actions"][0]

    def line(self, aid=None, phase=None, stage="issued", tick=12, sha=None):
        return ("SOC_SCN_SV_V1|" + self.resolved["scenario_id"] + "|" +
                (self.sha if sha is None else sha) + "|" +
                (self.first["action_instance_id"] if aid is None else aid) + "|" +
                (self.first["phase"] if phase is None else phase) + "|" + stage +
                "|" + str(tick))

    def test_scenario_schema_is_identical_to_python_compiler(self):
        doc, sha = load_plan(self.raw)
        self.assertEqual(doc, self.resolved)
        self.assertEqual(sha, self.sha)
        self.assertEqual(render_package(self.raw), render_package(self.raw))

    def test_sv_package_contains_all_action_ids_phases_and_typed_args(self):
        sv = render_package(self.raw)
        self.assertIn("package soc_scenario_contract_pkg;", sv)
        self.assertIn(self.sha, sv)
        self.assertIn(f"SCN_ACTION_COUNT = {len(self.resolved['actions'])}", sv)
        for a in self.resolved["actions"]:
            self.assertIn(f'return "{a["action_instance_id"]}";', sv)
            self.assertIn(f'return "{a["expected_result_id"]}";', sv)
        self.assertIn('input string stage', sv)
        self.assertIn('"issued"', sv)
        self.assertIn('"driver_done"', sv)
        self.assertNotIn('SV scenario is RTL PASS', sv)

    def test_interleaved_independent_actions_supported_without_global_phase_engine(self):
        first, second = self.resolved["actions"][:2]
        parts = [
            self.line(stage="issued", tick=10),
            self.line(aid=second["action_instance_id"], phase=second["phase"], stage="issued", tick=11),
            self.line(stage="driver_done", tick=13),
            self.line(aid=second["action_instance_id"], phase=second["phase"], stage="driver_done", tick=14),
        ]
        result = audit_sv_transcript(self.raw, "startup\n" + "\n".join(parts) + "\nPASS adapter mock")
        self.assertEqual(result["status"], "driver_log_unverified")
        self.assertIsNone(result["rtl_evidence"])
        self.assertEqual(result["action_instances_seen"], 2)
        self.assertEqual(result["event_count"], 4)
        self.assertTrue(all(v["provenance"] == "sv_driver_reported_only"
                            and v["rtl_observed"] is False for v in result["events"]))

    def test_empty_driver_log_never_passes_as_hardware_evidence(self):
        report = audit_sv_transcript(self.raw, "PASS fake\n")
        self.assertEqual(report["status"], "driver_log_unverified")
        self.assertEqual(report["event_count"], 0)
        self.assertIsNone(report["rtl_evidence"])

    def test_wrong_sha_unknown_action_or_phase_fail_closed(self):
        for log, match in (
            (self.line(sha="0" * 64), "wrong scenario/plan SHA"),
            (self.line(aid="not_a_real_action"), "unknown action"),
            (self.line(phase="check" if self.first["phase"] != "check" else "run"), "phase mismatch"),
        ):
            with self.subTest(log=log), self.assertRaisesRegex(SVContractError, match):
                audit_sv_transcript(self.raw, log)

    def test_orphan_duplicate_and_time_travel_fail(self):
        tests = (
            (self.line(stage="driver_done"), "orphan"),
            (self.line() + "\n" + self.line(), "duplicate issue"),
            (self.line(stage="issued", tick=15) + "\n" +
             self.line(stage="driver_done", tick=14), "out-of-order"),
            (self.line() + "\n" + self.line(stage="driver_done") +
             "\n" + self.line(stage="driver_done"), "duplicate"),
        )
        for log, match in tests:
            with self.subTest(log=log), self.assertRaisesRegex(SVContractError, match):
                audit_sv_transcript(self.raw, log)

    def test_malformed_and_disallowed_complete_stage_fail_closed(self):
        for log in (self.line() + "|surprise",
                    self.line(stage="checked"),
                    "SOC_SCN_SV_V1|invalid"):
            with self.subTest(log=log), self.assertRaisesRegex(SVContractError, "malformed"):
                audit_sv_transcript(self.raw, log)

    def test_plan_requires_canonical_bytes_and_no_hardware_claim(self):
        padded = json.dumps(self.resolved, indent=2).encode("ascii")
        with self.assertRaisesRegex(SVContractError, "canonical JSON"):
            load_plan(padded)
        fake = copy.deepcopy(self.resolved)
        fake["execution_evidence"] = {"passed": True}
        with self.assertRaisesRegex(SVContractError, "intent-only"):
            render_package(canonical_json(fake).encode("ascii"))

    def test_unbound_action_or_unrepresentable_arg_fails(self):
        bad = copy.deepcopy(self.resolved)
        bad["actions"][0]["actor"] = "not_declared"
        with self.assertRaisesRegex(SVContractError, "undeclared actor"):
            render_package(canonical_json(bad).encode("ascii"))
        bad = copy.deepcopy(self.resolved)
        bad["actions"][0]["args"]["bad"] = [1, 2, 3]
        with self.assertRaisesRegex(SVContractError, "unsupported SV argument type"):
            render_package(canonical_json(bad).encode("ascii"))


if __name__ == "__main__":
    unittest.main()
