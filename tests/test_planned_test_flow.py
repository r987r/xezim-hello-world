"""Tests for plan-only INIT/RUN/CHECK view independent of RTL evidence."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from tools.planned_test_flow import (
    PlannedFlowError, compile_flow, validate_snapshot, render_fragment,
)

ROOT = Path(__file__).resolve().parents[1]


class DeclaredFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = yaml.safe_load((ROOT / "config/regression.yaml").read_text())

    def test_every_configured_target_has_three_phases_without_simulation(self):
        self.assertGreater(len(self.catalog["tests"]), 15)
        for name, test in self.catalog["tests"].items():
            with self.subTest(target=name):
                flow = compile_flow(name, test, root=ROOT)
                self.assertEqual(tuple(flow["phases"]), ("init", "run", "check"))
                self.assertTrue(flow["intent_only"])
                self.assertEqual(flow["target"], name)
                self.assertFalse(any("observed" in r or "passed" in r
                                     for r in flow["phases"].values()))
                self.assertTrue(all(
                    p["milestones"] or p["actions"] or p["runner_outline"]
                    for p in flow["phases"].values()))

    def test_cpu_and_bfm_share_same_resolved_stimulus_even_without_events(self):
        cpu = compile_flow("chip-cpu-scenario",
                           self.catalog["tests"]["chip-cpu-scenario"], root=ROOT)
        bfm = compile_flow("chip-dma-scenario",
                           self.catalog["tests"]["chip-dma-scenario"], root=ROOT)
        self.assertEqual(cpu["scenario"], bfm["scenario"])
        self.assertEqual(cpu["scenario"]["scenario_id"], "cpu_bfm_ddr_roundtrip")
        self.assertEqual(cpu["scenario"]["seed"], 79)
        self.assertEqual(cpu["phase_detail"], "scenario_actions_and_milestones")
        actions = cpu["phases"]["run"]["actions"]
        self.assertEqual(len(actions), 7)
        self.assertIn("copy_out", [a["id"] for a in actions])
        self.assertIn("copy_back", [a["id"] for a in actions])
        self.assertEqual(cpu["phases"]["check"]["actions"][0]["id"], "check_return")
        self.assertIn("cpu0.firmware_init",
                      [x["id"] for x in cpu["phases"]["init"]["milestones"]])
        self.assertFalse(bfm["phases"]["init"]["milestones"])
        self.assertIn("not declared", bfm["phases"]["init"]["runner_outline"])

    def test_ethernet_pcie_real_ddr_milestones_work_without_typed_scenario(self):
        for target, expected in (
            ("chip-ethernet-cpu", "cpu0.eth_rx"),
            ("chip-pcie-host", "host0.bar_roundtrip"),
            ("chip-ddr4-real", "cpu0.dma_roundtrip"),
        ):
            with self.subTest(target=target):
                data = compile_flow(target, self.catalog["tests"][target], root=ROOT)
                run_ids = [item["id"] for item in data["phases"]["run"]["milestones"]]
                self.assertIn(expected, run_ids)
                self.assertEqual(data["phase_detail"], "expected_milestones_only")
                self.assertFalse(data["phases"]["run"]["actions"])
                self.assertIsNone(data["scenario"])

    def test_runner_only_test_does_not_fabricate_internal_steps(self):
        plan = compile_flow("smoke", self.catalog["tests"]["smoke"], root=ROOT)
        self.assertEqual(plan["phase_detail"], "runner_outline")
        self.assertTrue(all(not p["milestones"] and not p["actions"]
                            for p in plan["phases"].values()))
        self.assertIn("not declared", plan["phases"]["run"]["runner_outline"])

    def test_historical_run_without_snapshot_keeps_only_archived_milestones(self):
        test = deepcopy(self.catalog["tests"]["chip-cpu-scenario"])
        archived = compile_flow("chip-cpu-scenario", test, root=ROOT,
                                include_actions=False, source="archived_runner_plan")
        self.assertIsNone(archived["scenario"])
        self.assertEqual(archived["phase_detail"], "expected_milestones_only")
        self.assertFalse(archived["phases"]["run"]["actions"])
        self.assertIn("cpu0.dma_roundtrip",
                      [step["id"] for step in archived["phases"]["run"]["milestones"]])

    def test_snapshot_acceptance_and_milestones_cannot_be_forged(self):
        name = "chip-cpu-scenario"
        test = deepcopy(self.catalog["tests"][name])
        source = compile_flow(name, test, root=ROOT, source="run_snapshot")
        self.assertIs(validate_snapshot(source, name, test), source)
        corrupt = deepcopy(source)
        corrupt["phases"]["run"]["milestones"] = []
        with self.assertRaisesRegex(PlannedFlowError, "milestones"):
            validate_snapshot(corrupt, name, test)
        corrupt = deepcopy(source)
        corrupt["acceptance"]["pass_marker"] = "PASS unauthorized"
        with self.assertRaisesRegex(PlannedFlowError, "acceptance"):
            validate_snapshot(corrupt, name, test)
        corrupt = deepcopy(source)
        corrupt["intent_only"] = False
        with self.assertRaisesRegex(PlannedFlowError, "invalid or mismatched"):
            validate_snapshot(corrupt, name, test)

    def test_path_traversal_and_missing_scenario_fail_closed(self):
        base = deepcopy(self.catalog["tests"]["smoke"])
        for path in ("/tmp/foreign.json", "../secret.json",
                     "config/scenarios/../../secret.json",
                     "config/scenarios/not-found.json"):
            with self.subTest(path=path):
                base["flow_plan"] = path
                with self.assertRaises(PlannedFlowError):
                    compile_flow("smoke", base, root=ROOT)

    def test_safe_static_html_escapes_source_fields_and_args(self):
        test = deepcopy(self.catalog["tests"]["smoke"])
        test["report"] = {"context": '<script>alert("unsafe")</script>'}
        plan = compile_flow("smoke", test, root=ROOT)
        html = render_fragment(plan)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("INIT", html)
        self.assertIn("RUN", html)
        self.assertIn("CHECK", html)
        self.assertIn("not RTL evidence", html)

    def test_regression_runner_snapshots_flow_before_any_hdl_execution(self):
        source = (ROOT / "tools/regress.py").read_text()
        self.assertIn("out/'planned-flow.json'", source)
        self.assertLess(source.index("out/'planned-flow.json'"),
                        source.index("if options.stage == 'files':"))
        self.assertIn("'flow_plan'", source)
        html = (ROOT / "tools/templates/site_runs.html").read_text()
        self.assertIn('id="flow-target"', html)
        self.assertIn('id="flow-phases"', html)
        self.assertIn("View planned flow", html)
        pub = (ROOT / "tools/publish_site.py").read_text()
        self.assertIn("'test_flows':declared_flows", pub)
        self.assertIn("'planned_flow':declared_flow", pub)


if __name__ == "__main__":
    unittest.main()
