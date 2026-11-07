"""Canonical regression integration: memory map is derived only after RTL PASS."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv.common.action_events import ActionEvidenceError
from tools.scenario_memory_trace import finalize_scenario_run
from tests.test_scenario_memory_trace import fixture, axi, evidence, result


class ScenarioMemoryFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        _, self.plan, self.sha = fixture()
        (self.directory / "variant").mkdir()
        (self.directory / "variant" / "scenario-plan.json").write_bytes(self.plan)
        (self.directory / "scenario-plan.json").write_bytes(self.plan)
        (self.directory / "axi-transactions.json").write_text(json.dumps(axi()))
        (self.directory / "scenario-execution.json").write_text(
            json.dumps(evidence(self.sha)))
        (self.directory / "report.html").write_text(
            "<html><main><h2>Existing AXI report</h2></main></html>")

    def cpu(self):
        report = result()
        report["stage"] = "all"
        return report

    def test_cpu_adds_one_real_provenance_table_to_original_report(self):
        view = finalize_scenario_run(
            self.directory, firmware_mode="cpu_dma_scenario", result=self.cpu())
        self.assertEqual(view["status"], "cpu_phys_correlated_lifetimes_planned_only")
        self.assertEqual(len(view["buffers"]), 3)
        self.assertTrue((self.directory / "memory-lifetimes.json").is_file())
        page = (self.directory / "report.html").read_text()
        self.assertEqual(page.count("<!-- DV-MEM-LIFETIME-V1 -->"), 1)
        self.assertIn("Existing AXI report", page)
        self.assertIn("rtl_cpu_mailbox_checked_by_existing_test", page)
        with self.assertRaisesRegex(ActionEvidenceError, "already contains"):
            finalize_scenario_run(
                self.directory, firmware_mode="cpu_dma_scenario", result=self.cpu())

    def test_bfm_cannot_claim_actual_cpu_allocation(self):
        self.directory.joinpath("scenario-execution.json").write_text(
            json.dumps(evidence(self.sha, "reset_isolated_cocotb_bfm")))
        bfm = result("reset_isolated_cocotb_bfm")
        bfm["stage"] = "all"
        view = finalize_scenario_run(
            self.directory, firmware_mode="scenario_bfm", result=bfm)
        self.assertEqual(view["status"], "bfm_traffic_observed_allocation_unmeasured")
        self.assertTrue(all(b["token_provenance"] == "planner_only"
                            and b["phys_provenance"] == "planner_only"
                            for b in view["buffers"]))

    def test_missing_or_corrupt_real_axi_cannot_be_green(self):
        self.directory.joinpath("axi-transactions.json").unlink()
        with self.assertRaisesRegex(ActionEvidenceError, "missing/unsafe"):
            finalize_scenario_run(
                self.directory, firmware_mode="cpu_dma_scenario", result=self.cpu())
        self.assertNotIn("DV-MEM-LIFETIME-V1",
                         (self.directory / "report.html").read_text())
        self.assertFalse((self.directory / "memory-lifetimes.json").exists())

    def test_failed_run_never_fabricates_lifetimes(self):
        report = self.cpu()
        report["passed"] = False
        with self.assertRaisesRegex(ActionEvidenceError, "passing real RTL"):
            finalize_scenario_run(
                self.directory, firmware_mode="cpu_dma_scenario", result=report)
        report = self.cpu()
        report["stage"] = "files"
        with self.assertRaisesRegex(ActionEvidenceError, "passing real RTL"):
            finalize_scenario_run(
                self.directory, firmware_mode="cpu_dma_scenario", result=report)

    def test_shared_regression_runner_is_gated_to_scenario_modes_only(self):
        root = Path(__file__).resolve().parents[1]
        runner = (root / "tools/regress.py").read_text()
        self.assertIn("from scenario_memory_trace import finalize_scenario_run", runner)
        self.assertIn("('cpu_dma_scenario', 'scenario_bfm')", runner)
        self.assertIn("and options.stage in ('all', 'run')", runner)
        self.assertIn("result['passed'] = False", runner)


if __name__ == "__main__":
    unittest.main()
