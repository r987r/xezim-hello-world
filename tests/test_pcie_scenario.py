"""Source-selected PCIe link-training action shares canonical SCN execution."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
import unittest

import yaml

from dv.common.scenario import ScenarioError, canonical_json, resolve_scenario
from dv.common.action_runtime import ActionDispatcher, ActionDispatchError

ROOT = Path(__file__).resolve().parents[1]


class PcieScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / "config/scenarios/pcie-link-training.json").read_text())
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def resolve(self, spec=None):
        return resolve_scenario(spec or self.spec, self.soc, source_revision="a" * 40)

    def test_exact_selected_plan_no_fake_hardware_pass(self):
        p = self.resolve()
        self.assertEqual(len(p["actions"]), 1)
        self.assertEqual(p["actions"][0]["kind"], "pcie.link.train")
        self.assertEqual(p["actions"][0]["args"]["link"], "pcie0")
        self.assertIsNone(p["execution_evidence"])
        self.assertEqual(p["kind"], "soc_scenario_intent_only")

    def test_invalid_provider_and_wrong_phase_fail_closed(self):
        for field, value in (("lanes", 2), ("generation", 2),
                             ("data_width_bits", 16), ("link", "ethernet0")):
            with self.subTest(field=field):
                spec = copy.deepcopy(self.spec)
                spec["actions"][0]["args"][field] = value
                with self.assertRaises(ScenarioError):
                    self.resolve(spec)
        spec = copy.deepcopy(self.spec)
        spec["actions"][0]["phase"] = "init"
        with self.assertRaisesRegex(ScenarioError, "RUN action"):
            self.resolve(spec)

    def test_real_registered_handler_dispatches_same_action_and_hash(self):
        raw = canonical_json(self.resolve()).encode("ascii")
        seen = []

        async def host_driver(action, context):
            context.append((action["action_instance_id"], action["args"]["lanes"]))
            seen.append(action["kind"])

        runner = ActionDispatcher(
            raw, {"pcie.link.train": host_driver},
            expected_sha=hashlib.sha256(raw).hexdigest(),
        )
        result = []
        asyncio.run(runner.run(result))
        self.assertEqual(result, [("train_link", 1)])
        self.assertEqual(seen, ["pcie.link.train"])
        with self.assertRaisesRegex(ActionDispatchError, "no registered handler"):
            ActionDispatcher(raw, {})

    def test_duplicate_link_training_needs_ordering(self):
        spec = copy.deepcopy(self.spec)
        other = copy.deepcopy(spec["actions"][0])
        other["action_instance_id"] = "again"
        spec["actions"].append(other)
        with self.assertRaisesRegex(ScenarioError, "unordered concurrent training"):
            self.resolve(spec)
        spec["actions"][0]["depends_on"] = ["again"]
        # One directed training can be ordered after the other.
        self.assertEqual(len(self.resolve(spec)["actions"]), 2)


if __name__ == "__main__":
    unittest.main()
