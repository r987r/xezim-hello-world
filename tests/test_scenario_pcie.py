"""Canonical PCIe stimulus: selected SCN-C/Python/SV actions, not L0 proof."""
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
from tools.scenario_c import render_header
from tools.scenario_sv import render_package

ROOT = Path(__file__).resolve().parents[1]


class PcieScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(
            (ROOT / "config/scenarios/pcie-gen1-link.json").read_text())
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def resolve(self, spec=None):
        return resolve_scenario(
            spec if spec is not None else self.source, self.soc,
            source_revision="a" * 40)

    def test_selected_plan_identical_for_python_c_and_sv(self):
        plan = self.resolve()
        self.assertEqual(len(plan["actions"]), 1)
        action = plan["actions"][0]
        self.assertEqual(action["kind"], "pcie.link.train")
        self.assertEqual(action["phase"], "run")
        self.assertEqual(action["actor"], "host0")
        self.assertEqual(action["args"],
                         {"link": "pcie0", "lanes": 1,
                          "generation": 1, "data_width_bits": 32})
        self.assertIsNone(plan["execution_evidence"])
        raw = canonical_json(plan).encode("ascii")
        digest = hashlib.sha256(raw).hexdigest()
        self.assertIn("SOC_SCN_PLAN_SHA256 \"" + digest + "\"",
                      render_header(raw))
        self.assertIn("SCN_PLAN_SHA256 = \"" + digest + "\"",
                      render_package(raw))

    def test_nonqualified_link_configs_and_phases_fail(self):
        for param, value in (
            ("lanes", 2), ("generation", 2), ("data_width_bits", 16),
            ("link", "ethernet0"), ("link", "../pcie0")
        ):
            with self.subTest(param=param, value=value):
                spec = copy.deepcopy(self.source)
                spec["actions"][0]["args"][param] = value
                with self.assertRaises(ScenarioError):
                    self.resolve(spec)
        spec = copy.deepcopy(self.source)
        spec["actions"][0]["phase"] = "init"
        with self.assertRaisesRegex(ScenarioError, "RUN action"):
            self.resolve(spec)

    def test_unordered_same_link_training_fails_closed(self):
        spec = copy.deepcopy(self.source)
        other = copy.deepcopy(spec["actions"][0])
        other["action_instance_id"] = "train_again"
        spec["actions"].append(other)
        with self.assertRaisesRegex(ScenarioError, "unordered concurrent training"):
            self.resolve(spec)
        other["depends_on"] = ["train_link"]
        self.assertEqual(len(self.resolve(spec)["actions"]), 2)

    def test_dispatch_requires_selected_real_handler_and_sha(self):
        raw = canonical_json(self.resolve()).encode("ascii")
        with self.assertRaisesRegex(ActionDispatchError, "no registered handler"):
            ActionDispatcher(raw, {})
        with self.assertRaisesRegex(ActionDispatchError, "SHA"):
            ActionDispatcher(raw, {"pcie.link.train": lambda *_: None},
                             expected_sha="0" * 64)
        seen = []
        async def execute(action, context):
            seen.append((action["action_instance_id"], action["args"]["lanes"]))
        dispatcher = ActionDispatcher(
            raw, {"pcie.link.train": execute},
            expected_sha=hashlib.sha256(raw).hexdigest())
        self.assertEqual(asyncio.run(dispatcher.run()), ["train_link"])
        self.assertEqual(seen, [("train_link", 1)])
        # Driver completion is never independent endpoint L0 qualification.
        self.assertIsNone(self.resolve()["execution_evidence"])


if __name__ == "__main__":
    unittest.main()
