"""Negative contracts for every regression's selected runtime plan."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from tools.runtime_contract import (
    RunContractError, check_events, dispatch_event, load, save, selection,
    validate, validate_migration_inventory, qualify_selected_scenario,
    catalog_provenance, qualify_observed_phase_milestones,
)

ROOT=Path(__file__).resolve().parents[1]


class SelectedRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=yaml.safe_load((ROOT/"config/regression.yaml").read_text())

    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out=Path(self.dir.name)

    def plan(self, name="memory", commands=None):
        test=copy.deepcopy(self.config["tests"][name])
        return selection(name,{**test,"stage":"all"},self.out,
                         commands=commands if commands is not None else
                         [(name,["python3","tools/sim.py",name])])

    def test_migration_allowlist_exact_and_new_test_fails_closed(self):
        status=validate_migration_inventory(self.config)
        self.assertEqual(sum(v=="resolved_scenario_adapter" for v in status.values()),2)
        self.assertEqual(sum(v=="not_applicable" for v in status.values()),3)
        self.assertEqual(sum(v=="legacy_internal_stimulus_opaque" for v in status.values()),22)
        changed=copy.deepcopy(self.config)
        changed["tests"]["new-uninstrumented-test"] = copy.deepcopy(
            changed["tests"]["memory"])
        with self.assertRaisesRegex(RunContractError,"unregistered="):
            validate_migration_inventory(changed)

    def test_non_scenario_runner_is_honestly_opaque(self):
        p=self.plan()
        self.assertEqual(p["adapter"],"legacy_entrypoint_adapter")
        self.assertEqual(p["intent"]["declared_actions"],0)
        self.assertEqual(p["adapter_scope"],"legacy_internal_stimulus_opaque")
        self.assertIsNone(p["scenario_plan_sha256"])
        save(self.out/"selected-test-plan.json",p)
        self.assertEqual(load(self.out/"selected-test-plan.json","memory"),p)

    def test_all_regressions_require_a_selection_and_three_phase_catalog(self):
        for name,test in self.config["tests"].items():
            with self.subTest(target=name):
                if test.get("firmware_mode") in ("cpu_dma_scenario","scenario_bfm"):
                    continue
                snapshot=self.plan(name)
                self.assertEqual(set(snapshot["intent"]["phases"]),{"init","run","check"})
                self.assertEqual(snapshot["target"],name)
                self.assertEqual(snapshot["intent"]["target"],name)
        self.assertEqual(len(self.config["tests"]),27)

    def test_compile_and_lint_are_explicit_not_applicable(self):
        for name in ("chip-xezim-compile","noc-verilator","noc-xezim"):
            s=self.plan(name)
            self.assertEqual(s["adapter"],"non_runtime")
            self.assertEqual(s["intent"]["declared_actions"],0)
            self.assertEqual(s["intent"]["detail_status"],
                             "not_applicable_to_nonruntime_target")
            self.assertTrue(all(not v for v in s["intent"]["phases"].values()))

    def test_selected_cpu_and_bfm_scenario_are_source_resolved(self):
        scenario={"schema_version":1,"kind":"soc_scenario_intent_only",
                  "scenario_id":"cpu_bfm_ddr_roundtrip","seed":79,
                  "actions":[
                      {"action_instance_id":"alloc_source","phase":"init",
                       "actor":"cpu0","kind":"memory.allocate",
                       "args":{"buffer":"src"},"depends_on":[]},
                      {"action_instance_id":"copy_out","phase":"run",
                       "actor":"dma0","kind":"dma.copy",
                       "args":{"src":"src","dst":"ddr"},
                       "depends_on":["alloc_source"]},
                      {"action_instance_id":"check_return","phase":"check",
                       "actor":"cpu0","kind":"memory.check",
                       "args":{"buffer":"return"},
                       "depends_on":["copy_out"]}]}
        for target,loc in (("chip-cpu-scenario",self.out/"variant"),
                           ("chip-dma-scenario",self.out)):
            with self.subTest(target=target):
                loc.mkdir(parents=True,exist_ok=True)
                (loc/"scenario-plan.json").write_text(json.dumps(scenario))
                snapshot=self.plan(target)
                self.assertEqual(snapshot["adapter"],"scenario_dispatch_adapter")
                self.assertEqual(snapshot["intent"]["scenario_id"],
                                 "cpu_bfm_ddr_roundtrip")
                self.assertEqual(snapshot["intent"]["phases"]["run"][0]["label"],
                                 "copy_out")
                self.assertEqual(len(snapshot["scenario_plan_sha256"]),64)

    def test_live_phase_milestones_require_matching_run_selected_flow(self):
        directory=self.out
        selected=self.plan("chip-cpu-dma")
        phases=selected["intent"]["phases"]
        expected={}
        rows=[]
        for phase,actions in phases.items():
            expected[phase]=[]
            for a in actions:
                if a.get("kind")!="required_milestone":continue
                expected[phase].append(a["actor"]+"."+a["label"])
                rows.append({"phase":phase,"actor":a["actor"],
                             "step":a["label"],"status":"pass"})
        self.assertTrue(rows)
        outcome={"schema_version":1,"expected_steps":expected,
                 "passed":True,"issues":[],"rows":rows}
        with self.assertRaisesRegex(RunContractError,"lacks observed"):
            qualify_observed_phase_milestones(selected,directory,result={"passed":True})
        (directory/"test-flow.json").write_text(json.dumps(outcome))
        observed=qualify_observed_phase_milestones(
            selected,directory,result={"passed":True})
        self.assertEqual(observed["plan_sha256"],selected["plan_sha256"])
        outcome["rows"][0]["status"]="fail"
        (directory/"test-flow.json").write_text(json.dumps(outcome))
        with self.assertRaisesRegex(RunContractError,"incomplete"):
            qualify_observed_phase_milestones(selected,directory,result={"passed":True})
        self.assertEqual(qualify_observed_phase_milestones(
            selected,directory,result={"passed":False})["status"],"run_not_passed")

    def test_selected_scenario_requires_independent_observed_hash(self):
        folder=self.out/"variant"
        folder.mkdir(parents=True,exist_ok=True)
        resolved={"schema_version":1,"kind":"soc_scenario_intent_only",
                  "scenario_id":"cpu_bfm_ddr_roundtrip",
                  "actions":[{"action_instance_id":"run_copy","phase":"run",
                              "actor":"dma0","kind":"dma.copy","args":{"src":"src","dst":"ddr"}}]}
        (folder/"scenario-plan.json").write_text(json.dumps(resolved))
        selected=self.plan("chip-cpu-scenario")
        with self.assertRaisesRegex(RunContractError,"no independently observed"):
            qualify_selected_scenario(selected,self.out,result={"passed":True})
        evidence={"plan_sha256":selected["scenario_plan_sha256"],
                  "scenario_id":selected["intent"]["scenario_id"],
                  "execution_state":"rtl_observed","intent_is_not_evidence":True}
        (self.out/"scenario-execution.json").write_text(json.dumps(evidence))
        qualify_selected_scenario(selected,self.out,result={"passed":True})
        evidence["plan_sha256"]="0"*64
        (self.out/"scenario-execution.json").write_text(json.dumps(evidence))
        with self.assertRaisesRegex(RunContractError,"do not match selected"):
            qualify_selected_scenario(selected,self.out,result={"passed":True})
        qualify_selected_scenario(selected,self.out,result={"passed":False})

    def test_missing_scenario_is_never_a_legacy_fallback(self):
        with self.assertRaisesRegex(RunContractError,"scenario plan absent"):
            self.plan("chip-dma-scenario")

    def test_mutated_snapshot_or_unowned_target_rejected(self):
        p=self.plan()
        bad=copy.deepcopy(p)
        bad["intent"]["phases"]["run"].append({"label":"forged"})
        with self.assertRaisesRegex(RunContractError,"hash mismatch"):
            validate(bad)
        with self.assertRaisesRegex(RunContractError,"missing or unsafe"):
            load(self.out/"invalid.json","foreign")
        save(self.out/"selected-test-plan.json",p)
        with self.assertRaisesRegex(RunContractError,"target mismatch"):
            load(self.out/"selected-test-plan.json","foreign")

    def test_variant_actor_monitor_catalog_provenance_never_claims_live(self):
        (self.out/"variant").mkdir()
        (self.out/"variant/actors.json").write_text(json.dumps({
            "axi_actors":{"cpu0":{"kind":"rtl"},"target":{"kind":"rtl"}}}))
        (self.out/"variant/monitors.json").write_text(json.dumps({
            "monitors":[{"id":"cpu0","role":"initiator"},
                        {"id":"target","role":"target"},
                        {"id":"noc0","role":"link"}]}))
        selected={"report":{"axi":{"actors":"variant/actors.json",
                                   "catalog":"variant/monitors.json"}}}
        data=catalog_provenance(selected,root=self.out)
        self.assertEqual(data["actors"]["count"],2)
        self.assertEqual(data["monitors"]["count"],3)
        self.assertEqual(data["monitors"]["declared_initiators"],["cpu0"])
        self.assertEqual(data["monitors"]["declared_links"],["noc0"])
        self.assertEqual(data["unlabeled_initiators"],[])
        self.assertEqual(data["monitors"]["status"],
                         "source_catalog_loaded_not_runtime_bound")
        selected["report"]["axi"]["actors"]="../foreign.json"
        with self.assertRaisesRegex(RunContractError,"escapes source"):
            catalog_provenance(selected,root=self.out)
        selected["report"]["axi"]["actors"]="variant/actors.json"
        (self.out/"variant/monitors.json").write_text(json.dumps({
            "monitors":[{"id":"cpu0","role":"initiator"},{"id":"cpu0","role":"link"}]}))
        with self.assertRaisesRegex(RunContractError,"duplicates"):
            catalog_provenance(selected,root=self.out)

    def test_runner_events_are_not_passed_stimulus_actions(self):
        p=self.plan(commands=[("a",["sim","-f","rtl.f"])])
        start=dispatch_event(p,"a",status="started")
        end=dispatch_event(p,"a",status="completed",duration_s=0.2,
                           passed=False,reason="timeout")
        check_events(p,[start,end])
        self.assertEqual(start["evidence_kind"],
                         "runner_command_status_not_internal_action_dispatch")
        with self.assertRaisesRegex(RunContractError,"event does not match"):
            dispatch_event(p,"foreign",status="started")
        with self.assertRaisesRegex(RunContractError,"status missing or invented"):
            check_events(p,[start,{**end,"passed":None}])
        with self.assertRaisesRegex(RunContractError,"count mismatch"):
            check_events(p,[start])

    def test_selected_source_and_actual_invocation_cannot_be_reinterpreted(self):
        p=self.plan(commands=[("chip",["xezim","--max-time","200us"])])
        save(self.out/"selected-test-plan.json",p)
        tampered=copy.deepcopy(p)
        tampered["command_argv"][0]["argv"][-1]="1us"
        (self.out/"selected-test-plan.json").write_text(json.dumps(tampered))
        with self.assertRaisesRegex(RunContractError,"hash mismatch"):
            load(self.out/"selected-test-plan.json")


if __name__=="__main__":
    unittest.main()
