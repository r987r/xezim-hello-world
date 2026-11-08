"""Every configured regression exposes an intended flow without simulation evidence."""
from __future__ import annotations

import copy
from html import unescape
import json
from pathlib import Path
import unittest
import yaml

from tools.test_intent import catalog, plan, render, snapshot, validate_snapshot

ROOT=Path(__file__).resolve().parents[1]


class TestIntentFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=yaml.safe_load((ROOT/"config/regression.yaml").read_text())
        cls.scenario=json.loads((ROOT/"config/scenarios/cpu-bfm-ddr-roundtrip.json").read_text())
        cls.entries=catalog(cls.config,scenario=cls.scenario)

    def test_every_regression_has_a_definition_even_without_evidence(self):
        self.assertEqual(set(self.entries),set(self.config["tests"]))
        for name,entry in self.entries.items():
            self.assertEqual(set(entry["phases"]),{"init","run","check"})
            self.assertEqual(entry["provenance"],"configured_test_definition_not_execution")
            self.assertIs(entry["evidence_required_for_display"],False)
            self.assertNotIn("passed",entry)
            self.assertIn(entry["detail_status"],("declared_steps","no_detailed_phase_steps_declared"))

    def test_runtime_adoption_coverage_cannot_silently_regress(self):
        from collections import Counter
        status=Counter(v["execution_adoption"] for v in self.entries.values())
        self.assertEqual(status["not_applicable_compile_or_lint"],3)
        self.assertEqual(status["canonical_resolved_scenario"],2)
        # New opt-in PeakRDL full-chip reset now emits real checker-observed
        # CPU INIT/RUN/CHECK signals, not opaque or invented action events.
        self.assertEqual(status["instrumented_legacy_flow"],7)
        self.assertEqual(self.entries["chip-peakrdl-reset"]["execution_adoption"],
                         "instrumented_legacy_flow")
        # Existing unmigrated test count is the strict upper bound;
        # a newly added legacy target must be migrated along with another.
        self.assertLessEqual(status["legacy_runtime_without_action_contract"],18)
        self.assertEqual(sum(status.values()),len(self.entries))
        for item in self.entries.values():
            if item["execution_adoption"]=="not_applicable_compile_or_lint":
                self.assertFalse(item["runtime_phases_applicable"])
            else:
                self.assertTrue(item["runtime_phases_applicable"])

    def test_pcie_init_run_check_are_from_regression_not_sim_logs(self):
        intent=self.entries["chip-pcie-host"]
        self.assertTrue(intent["declared_actions"]>=15)
        self.assertIn("enumerate",[a["label"] for a in intent["phases"]["init"]])
        self.assertIn("bar_roundtrip",[a["label"] for a in intent["phases"]["run"]])
        self.assertIn("final_verify",[a["label"] for a in intent["phases"]["check"]])

    def test_scenario_catalog_is_selected_from_yaml_not_firmware_name(self):
        intent=self.entries["chip-cpu-scenario"]
        self.assertEqual(intent["scenario_source"],
                         self.config["tests"]["chip-cpu-scenario"]["flow_plan"])
        with self.assertRaisesRegex(ValueError,"unsafe scenario declaration"):
            mutated=copy.deepcopy(self.config)
            mutated["tests"]["chip-dma-scenario"]["flow_plan"]="../evil.json"
            catalog(mutated)
        with self.assertRaisesRegex(ValueError,"declared scenario differs"):
            altered=copy.deepcopy(self.scenario)
            altered["seed"]+=1
            catalog(self.config,scenario=altered)

    def test_scenario_actions_expose_dependencies_and_inputs(self):
        intent=self.entries["chip-dma-scenario"]
        actions=[a for phase in intent["phases"].values() for a in phase]
        self.assertEqual(intent["scenario_id"],self.scenario["scenario_id"])
        self.assertTrue(any(a["kind"]=="dma.copy" for a in actions))
        self.assertTrue(any(a["depends_on"] for a in actions))
        self.assertTrue(any(a["args"].get("buffer") for a in actions))
        self.assertEqual(intent["phases"]["check"][0]["kind"],"memory.check")

    def test_every_test_has_reviewable_authored_stimulus_without_fake_actions(self):
        from tools.stimulus_catalog import load as load_stimuli
        specs=load_stimuli(self.config)
        self.assertEqual(set(specs),set(self.entries))
        self.assertEqual(len(specs),30)
        self.assertEqual(sum(v["execution"]=="scenario_native" for v in specs.values()),2)
        self.assertEqual(sum(v["execution"]=="observed_milestones" for v in specs.values()),7)
        self.assertEqual(sum(v["execution"]=="legacy_opaque" for v in specs.values()),18)
        self.assertEqual(sum(v["execution"]=="non_runtime" for v in specs.values()),3)
        for target, intent in self.entries.items():
            self.assertEqual(intent["stimulus_source"],"config/stimulus/tests.yaml")
            self.assertEqual(intent["stimulus_sha256"],specs[target]["sha256"])
            self.assertEqual(intent["stimulus_execution"],specs[target]["execution"])
            self.assertTrue(intent["stimulus_outline_is_not_dispatch_evidence"])
            self.assertNotIn("passed",intent)
        self.assertEqual(self.entries["smoke"]["declared_actions"],0)
        self.assertEqual(len(self.entries["smoke"]["stimulus_outline"]["run"]),1)

    def test_no_phase_instrumentation_stays_not_described(self):
        simple=self.entries["smoke"]
        self.assertEqual(simple["declared_actions"],0)
        self.assertEqual(simple["detail_status"],"no_detailed_phase_steps_declared")
        html=render(simple)
        self.assertIn("Detailed INIT steps are not declared",html)
        self.assertIn("Detailed RUN steps are not declared",html)
        self.assertIn("Detailed CHECK steps are not declared",html)
        self.assertIn("hello_world_tb",html)

    def test_negative_acceptance_never_claims_passed(self):
        intent=self.entries["memory-negative"]
        self.assertEqual(intent["acceptance_kind"],"expected_failure")
        self.assertIs(intent["evidence_required_for_display"],False)
        self.assertNotIn("passed",intent)

    def test_render_escapes_metadata_without_html_injection(self):
        test={"engine":"xezim","top":"<script>evil</script>",
              "pass":"<b>PASSED</b>",
              "report":{"context":"<img src=x onerror=evil()>",
                        "flow":{"required_steps":{"init":["host0.setup"],"run":["host0.dma_copy"],
                                                  "check":["host0.check"]}}}}
        html=render(plan("safe",test))
        self.assertNotIn("<script>",html)
        self.assertNotIn("<img",html)
        self.assertIn("&lt;script&gt;",html)
        self.assertIn("&lt;img",html)

    def test_pre_run_plan_snapshot_tampering_rejected(self):
        test=copy.deepcopy(self.config["tests"]["chip-pcie-host"])
        test["args"]=["+CASE=0","--seed","17"]
        original=snapshot("chip-pcie-host",test)
        self.assertEqual(validate_snapshot(original,target="chip-pcie-host"),
                         original["intent"])
        self.assertEqual(original["intent"]["selected_args"],test["args"])
        tampered=copy.deepcopy(original)
        tampered["intent"]["selected_args"].append("+MUTATED=1")
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            validate_snapshot(tampered,target="chip-pcie-host")
        with self.assertRaisesRegex(ValueError,"target mismatch"):
            validate_snapshot(original,target="chip-ethernet-cpu")

    def test_declared_plan_hash_stable_and_does_not_assert_dispatch(self):
        test=copy.deepcopy(self.config["tests"]["chip-dma-scenario"])
        s1=snapshot("chip-dma-scenario",test,scenario=self.scenario)
        s2=snapshot("chip-dma-scenario",test,scenario=copy.deepcopy(self.scenario))
        self.assertEqual(s1["plan_sha256"],s2["plan_sha256"])
        self.assertEqual(s1["kind"],"source_declared_plan_not_execution")
        self.assertNotIn("dispatched",s1["intent"])
        self.assertNotIn("passed",s1["intent"])
        changed=copy.deepcopy(test)
        changed["seed"]=123
        self.assertNotEqual(s1["plan_sha256"],
            snapshot("chip-dma-scenario",changed,scenario=self.scenario)["plan_sha256"])

    def test_runtime_snapshots_written_before_simulation(self):
        source=(ROOT/"tools/regress.py").read_text()
        write=source.index("(out/'planned-flow.json').write_text")
        run=source.index("run_process(command",write)
        self.assertLess(write,run)
        site=(ROOT/"tools/publish_site.py").read_text()
        self.assertIn("validate_snapshot(declared,target=target)",site)
        self.assertIn("legacy_run_selection_not_archived",site)
        self.assertNotIn("if target in ('chip-cpu-scenario','chip-dma-scenario'):",site)
        self.assertIn("flow_result['planned_flow_sha256']=selected['plan_sha256']",source)
        self.assertIn("observed test-flow evidence references a different selected plan",site)

    def test_site_uses_same_definition_catalog_not_data_from_passed_tests(self):
        site=(ROOT/"tools/publish_site.py").read_text()
        page=(ROOT/"tools/templates/site_runs.html").read_text()
        self.assertIn("'test_intents':flow_intents",site)
        self.assertIn("dump(output/'data/test-intents.json',flow_intents)",site)
        self.assertIn("flowSelect.addEventListener",page)
        self.assertIn("View intended flow",page)
        self.assertIn("Authored stimulus specification",page)
        self.assertIn("selected?.planned_flow_intent||intentMap[name]",page)
        self.assertIn("openFlow.onclick=()=>markFlow(e.target,e)",page)
        self.assertIn("No recorded result yet. Planned flow remains available.",page)


if __name__=="__main__":
    unittest.main()
