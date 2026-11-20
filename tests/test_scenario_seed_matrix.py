"""SCN seed matrix uses one resolver, preserves exact plan and seed provenance."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.scenario_seed_matrix import (
    MatrixError, check_matrix, choose_seeds, select_distinct_cases, write_matrix,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "config/scenarios/dma-roundtrip.json"
SOC = ROOT / "config/soc.yaml"


class SeedMatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / "matrix"

    def test_directed_and_random_come_from_same_executable_intent(self):
        matrix = write_matrix(SCENARIO, SOC, self.output,
                              seeds=[7, 31337, 12], source_revision="a" * 40)
        self.assertEqual([c["seed"] for c in matrix["cases"]], [7, 31337, 12])
        self.assertEqual(check_matrix(SCENARIO, SOC, self.output), matrix)
        docs = [json.loads((self.output / c["file"]).read_text())
                for c in matrix["cases"]]
        self.assertEqual(len({c["scenario_id"] for c in docs}), 1)
        self.assertTrue(all(c["execution_evidence"] is None for c in docs))
        self.assertTrue(all(c["kind"] == "soc_scenario_intent_only" for c in docs))
        self.assertEqual([d["seed"] for d in docs], [7, 31337, 12])
        self.assertEqual(len({c["plan_sha256"] for c in matrix["cases"]}), 3)
        actions = [{a["action_instance_id"] for a in d["actions"]} for d in docs]
        self.assertEqual(actions[0], actions[1])
        self.assertEqual(actions[1], actions[2])
        self.assertTrue(all(d["provenance"]["source_revision"] == "a" * 40
                            for d in docs))

    def test_random_seed_selection_is_unique_and_replayable(self):
        spec = json.loads(SCENARIO.read_text())
        seeds = choose_seeds(spec, random_runs=24)
        self.assertEqual(len(seeds), len(set(seeds)))
        self.assertEqual(len(seeds), 24)
        write_matrix(SCENARIO, SOC, self.output, seeds=seeds)
        self.assertEqual([c["seed"] for c in check_matrix(
            SCENARIO, SOC, self.output)["cases"]], seeds)

    def test_reusable_argument_diversity_selection_is_not_seed_hardcoded(self):
        source = ROOT / "config/scenarios/cpu-bfm-ddr-roundtrip.json"
        write_matrix(source, SOC, self.output, seeds=list(range(32)))
        selected = select_distinct_cases(
            source, SOC, self.output, action_instance_id="init_source",
            argument_path=("pattern", "seed"), count=2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(len({entry["seed"] for entry in selected}), 2)
        values = set()
        for entry in selected:
            plan = json.loads((self.output / entry["file"]).read_text())
            action = next(x for x in plan["actions"]
                          if x["action_instance_id"] == "init_source")
            values.add(action["args"]["pattern"]["seed"])
        self.assertEqual(values, {90, 91})
        self.assertNotIn(79, [entry["seed"] for entry in selected])

    def test_diversity_selector_fails_closed_on_missing_capability_and_tamper(self):
        source = ROOT / "config/scenarios/cpu-bfm-ddr-roundtrip.json"
        write_matrix(source, SOC, self.output, seeds=list(range(12)))
        with self.assertRaisesRegex(MatrixError, "insufficient distinct"):
            select_distinct_cases(
                source, SOC, self.output, action_instance_id="init_source",
                argument_path=("pattern", "seed"), count=3)
        with self.assertRaisesRegex(MatrixError, "missing or ambiguous"):
            select_distinct_cases(
                source, SOC, self.output, action_instance_id="not_registered",
                argument_path=("pattern", "seed"), count=1)
        with self.assertRaisesRegex(MatrixError, "unavailable"):
            select_distinct_cases(
                source, SOC, self.output, action_instance_id="init_source",
                argument_path=("pattern", "unknown"), count=1)
        for bad in (0, True, 129):
            with self.subTest(count=bad), self.assertRaisesRegex(MatrixError, "invalid"):
                select_distinct_cases(
                    source, SOC, self.output, action_instance_id="init_source",
                    argument_path=("pattern", "seed"), count=bad)
        index = self.output / "matrix.json"
        index.write_text(index.read_text().replace(
            "source_selected_intent_only_not_hardware_execution", "hardware_pass"))
        with self.assertRaises(MatrixError):
            select_distinct_cases(
                source, SOC, self.output, action_instance_id="init_source",
                argument_path=("pattern", "seed"), count=2)

    def test_duplicate_invalid_seed_or_overwrite_is_rejected(self):
        spec = json.loads(SCENARIO.read_text())
        for seeds in ([1, 1], [], [-1], [2**32], [True], list(range(129))):
            with self.subTest(seeds=str(seeds)[:25]), self.assertRaises(MatrixError):
                choose_seeds(spec, seeds=seeds)
        with self.assertRaises(MatrixError):
            choose_seeds(spec, seeds=[1], random_runs=1)
        with self.assertRaises(MatrixError):
            choose_seeds(spec, random_runs=129)
        write_matrix(SCENARIO, SOC, self.output, seeds=[42])
        with self.assertRaisesRegex(MatrixError, "overwrite"):
            write_matrix(SCENARIO, SOC, self.output, seeds=[42])

    def test_tamper_missing_extra_and_untrusted_status_rejected(self):
        write_matrix(SCENARIO, SOC, self.output, seeds=[42, 43])
        index = self.output / "matrix.json"
        baseline = json.loads(index.read_text())
        first = self.output / baseline["cases"][0]["file"]
        first.write_text(first.read_text().replace("intent_only", "rtl_observed"))
        with self.assertRaisesRegex(MatrixError, "tampered"):
            check_matrix(SCENARIO, SOC, self.output)
        first.write_text(json.dumps(json.loads(first.read_text())))  # not canonical
        with self.assertRaises(MatrixError):
            check_matrix(SCENARIO, SOC, self.output)
        index.unlink()
        with self.assertRaisesRegex(MatrixError, "missing"):
            check_matrix(SCENARIO, SOC, self.output)

    def test_changed_input_cannot_relabel_existing_seed_results(self):
        write_matrix(SCENARIO, SOC, self.output, seeds=[3, 9])
        local_scenario = Path(self.tmp.name) / "scenario.json"
        local_scenario.write_bytes(SCENARIO.read_bytes())
        spec = json.loads(local_scenario.read_text())
        spec["seed"] += 1
        local_scenario.write_text(json.dumps(spec))
        with self.assertRaisesRegex(MatrixError, "source changed"):
            check_matrix(local_scenario, SOC, self.output)
        index = self.output / "matrix.json"
        doc = json.loads(index.read_text())
        doc["evidence"] = "hardware_passed"
        from dv.common.scenario import canonical_json
        index.write_text(canonical_json(doc))
        with self.assertRaisesRegex(MatrixError, "falsely claims"):
            check_matrix(SCENARIO, SOC, self.output)


if __name__ == "__main__":
    unittest.main()
