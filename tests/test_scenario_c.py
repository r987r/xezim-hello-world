"""SCN-C action metadata shares exactly one canonical source plan with SV."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from dv.common.scenario import canonical_json, resolve_scenario
from tools.scenario_c import render_header, argument_key_hash
from tools.scenario_sv import load_plan, render_package

ROOT = Path(__file__).resolve().parents[1]


class ScenarioCContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        spec = json.loads((ROOT / "config/scenarios/dma-roundtrip.json").read_text())
        cls.plan = resolve_scenario(spec, soc, source_revision="a" * 40)
        cls.raw = canonical_json(cls.plan).encode("ascii")

    def test_exact_c_and_sv_share_all_action_ids_and_sha(self):
        c = render_header(self.raw)
        sv = render_package(self.raw)
        sha = hashlib.sha256(self.raw).hexdigest()
        self.assertEqual(load_plan(self.raw)[1], sha)
        self.assertIn(sha, c)
        self.assertIn(sha, sv)
        self.assertIn("SOC_SCN_ACTION_COUNT " + str(len(self.plan["actions"])), c)
        for action in self.plan["actions"]:
            self.assertIn('"' + action["action_instance_id"] + '"', c)
            self.assertIn('"' + action["expected_result_id"] + '"', c)
        self.assertIn("NOT hardware-issued", c)
        self.assertEqual(c, render_header(self.raw))

    def test_only_canonical_intent_without_fake_execution(self):
        tampered = json.dumps(self.plan, indent=2).encode("ascii")
        with self.assertRaisesRegex(ValueError, "canonical"):
            render_header(tampered)
        wrong = copy.deepcopy(self.plan)
        wrong["execution_evidence"] = {"status": "PASS"}
        with self.assertRaisesRegex(ValueError, "intent-only"):
            render_header(canonical_json(wrong).encode("ascii"))

    def test_firmware_action_table_preserves_selected_args_and_deps(self):
        c = render_header(self.raw)
        self.assertIn("soc_scn_dependencies", c)
        self.assertIn("soc_scn_arguments", c)
        self.assertIn("soc_scn_action_at", c)
        self.assertIn("soc_scn_dependency_at", c)
        self.assertIn("soc_scn_argument_at", c)
        for action in self.plan["actions"]:
            for key, value in action["args"].items():
                if type(value) is int:
                    self.assertIn("UINT64_C(" + str(value) + ")", c)
        self.assertNotIn("PASS: hardware", c)

    def test_generated_indices_and_hashes_are_derived_from_same_source(self):
        c = render_header(self.raw)
        actions = self.plan["actions"]
        dependencies = []
        for i, action in enumerate(actions):
            for dependency in action["depends_on"]:
                prior = [j for j, item in enumerate(actions[:i])
                         if item["action_instance_id"] == dependency]
                self.assertEqual(len(prior), 1)
                dependencies.append(prior[0])
        self.assertIn("soc_scn_dependency_indices", c)
        self.assertIn("soc_scn_dependency_index_at", c)
        for prior in set(dependencies):
            self.assertIn("UINT16_C(" + str(prior) + ")", c)
        for key in ("alignment", "buffer", "region", "size",
                    "pattern.kind", "pattern.seed", "engine"):
            expected = 5381
            for byte in key.encode("ascii"):
                expected = (((expected << 5) + expected) ^ byte) & 0xffffffff
            self.assertEqual(argument_key_hash(key), expected)
            self.assertIn("UINT32_C(" + str(expected) + ")", c)
        self.assertEqual(c, render_header(self.raw))
        self.assertNotIn("hardware_pass", c)

    def test_unsupported_c_argument_is_rejected_by_existing_sv_schema(self):
        bad = copy.deepcopy(self.plan)
        bad["actions"][0]["args"]["unsupported"] = [1, 2, 3]
        with self.assertRaisesRegex(ValueError, "unsupported SV argument type"):
            render_header(canonical_json(bad).encode("ascii"))


if __name__ == "__main__":
    unittest.main()
