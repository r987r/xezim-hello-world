"""P2 TB-only portability: two compatible SCN source selections, one runtime/ABI.

This is NOT a test of two different hardware SoCs and does not introduce
new DMA/PCIe/Ethernet protocol traffic or claim RTL completion.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

from dv.common.action_events import ActionEventRecorder
from dv.common.action_runtime import ActionDispatcher, ActionDispatchError, HandlerSpec
from dv.common.scenario import canonical_json
from dv.common.scenario_dma import EXAMPLE, materialize
from tools.scenario_c import render_header
from tools.scenario_seed_matrix import check_matrix, write_matrix
from tools.scenario_sv import audit_sv_transcript, render_package

ROOT = Path(__file__).resolve().parents[1]


class ScenarioPortabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc_path = ROOT / "config/soc.yaml"
        cls.soc = yaml.safe_load(cls.soc_path.read_text())
        cls.source = json.loads((ROOT / EXAMPLE).read_text())

    def test_two_source_selections_reuse_cpu_bfm_python_c_sv_and_event_contracts(self):
        # Deliberately preserve the EXISTING eight action kinds, actors, RTL
        # platform and resource map. Only selected source identity/seed vary.
        # No extra scenario or new hardware adapter is checked into the repo.
        if str(ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(ROOT / "tools"))
        from tools.regress import load_config

        sources = []
        results = {}
        try:
            with tempfile.TemporaryDirectory() as scratch:
                temp = Path(scratch)
                for label, seed in (("a", 79), ("b", 80)):
                    authored = copy.deepcopy(self.source)
                    authored["scenario_id"] = f"cpu_bfm_portability_{label}"
                    authored["seed"] = seed
                    with tempfile.NamedTemporaryFile(
                            mode="w", prefix=f"scn_p2_{label}_", suffix=".json",
                            dir=ROOT / "config/scenarios", delete=False) as source_file:
                        source = Path(source_file.name)
                        source_file.write(json.dumps(authored))
                    sources.append(source)
                    selected = source.relative_to(ROOT).as_posix()

                    # The existing regression config is copied, not replaced.
                    # Both existing real CPU and BFM targets consume the same
                    # selected flow_plan for THIS configuration.
                    regression = yaml.safe_load((ROOT / "config/regression.yaml").read_text())
                    for name in ("chip-cpu-scenario", "chip-dma-scenario"):
                        regression["tests"][name]["flow_plan"] = selected
                    path = temp / f"regression-{label}.yaml"
                    path.write_text(yaml.safe_dump(regression))
                    checked = load_config(path)
                    for name in ("chip-cpu-scenario", "chip-dma-scenario"):
                        self.assertEqual(checked["tests"][name]["flow_plan"], selected)

                    cpu_dir, bfm_dir = temp / f"{label}-cpu", temp / f"{label}-bfm"
                    cpu_plan, cpu_contract = materialize(
                        self.soc, cpu_dir, scenario_source=selected)
                    bfm_plan, bfm_contract = materialize(
                        self.soc, bfm_dir, scenario_source=selected)
                    raw = (cpu_dir / "scenario-plan.json").read_bytes()
                    sha = hashlib.sha256(raw).hexdigest()
                    self.assertEqual(raw, canonical_json(cpu_plan).encode("ascii"))
                    self.assertEqual(raw, (bfm_dir / "scenario-plan.json").read_bytes())
                    self.assertEqual(cpu_plan, bfm_plan)
                    self.assertEqual(cpu_contract, bfm_contract)
                    self.assertEqual(cpu_contract["plan_sha256"], sha)
                    self.assertEqual(cpu_plan["execution_evidence"], None)

                    # P0's canonical matrix and P1's source selection feed
                    # the SAME immutable plan used by C, SV and Python.
                    matrix_dir = temp / f"{label}-matrix"
                    matrix = write_matrix(source, self.soc_path, matrix_dir,
                                          seeds=[seed])
                    self.assertEqual(check_matrix(source, self.soc_path, matrix_dir),
                                     matrix)
                    self.assertEqual(
                        (matrix_dir / matrix["cases"][0]["file"]).read_bytes(), raw)
                    self.assertEqual(matrix["cases"][0]["plan_sha256"], sha)
                    c_header = render_header(raw)
                    sv_package = render_package(raw)
                    self.assertEqual(
                        (cpu_dir / "soc_scenario_contract.h").read_text(), c_header)
                    self.assertIn(sha, c_header)
                    self.assertIn(sha, sv_package)
                    self.assertIn("SCN_ACTION_COUNT = 8", sv_package)

                    # Reuse the original typed Python dispatcher, preserving
                    # driver-only event evidence. These noop adapters verify
                    # the framework contract, NOT real iDMA completions.
                    selected_ids = {a["action_instance_id"] for a in cpu_plan["actions"]}
                    dispatched = []
                    async def driver(action, _context):
                        dispatched.append(action["action_instance_id"])

                    registry = {
                        kind: HandlerSpec(
                            driver, actors=frozenset(
                                a["actor"] for a in cpu_plan["actions"]
                                if a["kind"] == kind))
                        for kind in {a["kind"] for a in cpu_plan["actions"]}
                    }
                    recorder_path = temp / f"{label}-events.jsonl"
                    recorder = ActionEventRecorder(raw, recorder_path, lambda: 0)
                    dispatcher = ActionDispatcher(
                        raw, registry, expected_sha=sha, recorder=recorder,
                        max_inflight=1, task_backend="asyncio")
                    asyncio.run(dispatcher.run())
                    recorder.close()
                    self.assertEqual(set(dispatched), selected_ids)
                    self.assertEqual(len(dispatched), 8)
                    events = [json.loads(line) for line in
                              recorder_path.read_text().splitlines()]
                    self.assertEqual(len(events), 16)
                    self.assertTrue(all(
                        event["origin"] == "python_driver" and
                        not event["evidence"] for event in events))

                    # The original SV reporter must still label fake/empty
                    # driver output unverified, never as observed RTL PASS.
                    report = audit_sv_transcript(raw, "PASS synthetic only")
                    self.assertEqual(report["status"], "driver_log_unverified")
                    self.assertIsNone(report["rtl_evidence"])

                    results[label] = {
                        "sha": sha, "raw": raw, "registry": registry,
                        "scenario_id": cpu_plan["scenario_id"],
                        "pattern_seed": cpu_contract["seed"],
                        "action_ids": selected_ids,
                        "event_count": len(events),
                    }

                self.assertEqual(results["a"]["action_ids"], results["b"]["action_ids"])
                self.assertNotEqual(results["a"]["scenario_id"],
                                    results["b"]["scenario_id"])
                self.assertNotEqual(results["a"]["pattern_seed"],
                                    results["b"]["pattern_seed"])
                self.assertNotEqual(results["a"]["sha"], results["b"]["sha"])
                self.assertEqual(results["a"]["event_count"], 16)
                self.assertEqual(results["b"]["event_count"], 16)

                # A foreign C/SV/Python plan identity cannot be relabeled
                # as the other configuration, even with identical action IDs.
                with self.assertRaisesRegex(ActionDispatchError, "SHA"):
                    ActionDispatcher(
                        results["b"]["raw"], results["b"]["registry"],
                        expected_sha=results["a"]["sha"])
        finally:
            for source in sources:
                source.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
