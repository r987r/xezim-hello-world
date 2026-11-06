"""Every configured regression exposes an intended flow without simulation evidence."""
from __future__ import annotations

import copy
from html import unescape
import json
from pathlib import Path
import unittest
import yaml

from tools.test_intent import catalog, plan, render

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

    def test_pcie_init_run_check_are_from_regression_not_sim_logs(self):
        intent=self.entries["chip-pcie-host"]
        self.assertTrue(intent["declared_actions"]>=15)
        self.assertIn("enumerate",[a["label"] for a in intent["phases"]["init"]])
        self.assertIn("bar_roundtrip",[a["label"] for a in intent["phases"]["run"]])
        self.assertIn("final_verify",[a["label"] for a in intent["phases"]["check"]])

    def test_scenario_actions_expose_dependencies_and_inputs(self):
        intent=self.entries["chip-dma-scenario"]
        actions=[a for phase in intent["phases"].values() for a in phase]
        self.assertEqual(intent["scenario_id"],self.scenario["scenario_id"])
        self.assertTrue(any(a["kind"]=="dma.copy" for a in actions))
        self.assertTrue(any(a["depends_on"] for a in actions))
        self.assertTrue(any(a["args"].get("buffer") for a in actions))
        self.assertEqual(intent["phases"]["check"][0]["kind"],"memory.check")

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

    def test_site_uses_same_definition_catalog_not_data_from_passed_tests(self):
        site=(ROOT/"tools/publish_site.py").read_text()
        page=(ROOT/"tools/templates/site_runs.html").read_text()
        self.assertIn("'test_intents':flow_intents",site)
        self.assertIn("dump(output/'data/test-intents.json',flow_intents)",site)
        self.assertIn("flowSelect.addEventListener",page)
        self.assertIn("View intended flow",page)
        self.assertIn("No recorded result yet. Planned flow remains available.",page)


if __name__=="__main__":
    unittest.main()
