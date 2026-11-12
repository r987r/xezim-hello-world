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
        cls.spec = json.loads((ROOT / "config/scenarios/pcie-gen1-link.json").read_text())
        cls.bar_spec = json.loads((ROOT / "config/scenarios/pcie-gen1-bar0.json").read_text())
        cls.mem_spec = json.loads((ROOT / "config/scenarios/pcie-gen1-mem-ingress.json").read_text())
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def resolve(self, spec=None):
        return resolve_scenario(spec or self.spec, self.soc, source_revision="a" * 40)

    def test_exact_selected_plan_no_fake_hardware_pass(self):
        p = self.resolve()
        self.assertEqual(len(p["actions"]), 1)
        e=self.resolve(self.bar_spec)
        self.assertEqual(len(e["actions"]),2)
        self.assertEqual(e["actions"][1]["kind"], "pcie.config.bar0")
        self.assertEqual(e["actions"][1]["depends_on"],["train_link"])
        self.assertEqual(p["actions"][0]["kind"], "pcie.link.train")
        self.assertEqual(p["actions"][0]["args"]["link"], "pcie0")
        self.assertIsNone(p["execution_evidence"])
        self.assertEqual(p["kind"], "soc_scenario_intent_only")

    def test_invalid_provider_and_wrong_phase_fail_closed(self):
        for field, value in (("lanes", 2), ("generation", 2),
                             ("data_width_bits", 32), ("link", "ethernet0")):
            with self.subTest(field=field):
                spec = copy.deepcopy(self.spec)
                spec["actions"][0]["args"][field] = value
                with self.assertRaises(ScenarioError):
                    self.resolve(spec)
        spec = copy.deepcopy(self.spec)
        spec["actions"][0]["phase"] = "run"
        with self.assertRaisesRegex(ScenarioError, "INIT action"):
            self.resolve(spec)

    def test_host_bar_enumeration_is_causal_and_bounded(self):
        for key, value in (("link", "pcie7"), ("bar_index", 1),
                           ("aperture_bytes", 3000), ("aperture_bytes", 2097152),
                           ("host_bus_base", 0x80001001),
                           ("host_bus_base", 0xfffff001)):
            spec=copy.deepcopy(self.bar_spec)
            spec["actions"][1]["args"][key]=value
            with self.subTest(key=key,value=value), self.assertRaises(ScenarioError):
                self.resolve(spec)
        for mutation in ("no_dependency", "wrong_phase", "no_training"):
            spec=copy.deepcopy(self.bar_spec)
            if mutation=="no_dependency":
                spec["actions"][1]["depends_on"]=[]
            elif mutation=="wrong_phase":
                spec["actions"][1]["phase"]="run"
            else:
                spec["actions"]=spec["actions"][1:]
            with self.subTest(mutation=mutation),self.assertRaises(ScenarioError):
                self.resolve(spec)

    def test_real_registered_handler_dispatches_same_action_and_hash(self):
        raw = canonical_json(self.resolve(self.bar_spec)).encode("ascii")
        seen = []

        async def host_driver(action, context):
            context.append((action["action_instance_id"], action["args"]["lanes"]))
            seen.append(action["kind"])

        async def host_config(action, context):
            context.append((action["action_instance_id"], action["args"]["bar_index"]))
            seen.append(action["kind"])

        runner = ActionDispatcher(
            raw, {"pcie.link.train": host_driver, "pcie.config.bar0": host_config},
            expected_sha=hashlib.sha256(raw).hexdigest(),
        )
        result = []
        asyncio.run(runner.run(result))
        self.assertEqual(result, [("train_link", 1), ("enumerate_bar0", 0)])
        self.assertEqual(seen, ["pcie.link.train", "pcie.config.bar0"])
        with self.assertRaisesRegex(ActionDispatchError, "no registered handler"):
            ActionDispatcher(raw, {})

    def test_posted_memory_write_is_host_intent_only(self):
        p = self.resolve(self.mem_spec)
        self.assertEqual([a["kind"] for a in p["actions"]],
                         ["pcie.link.train", "pcie.config.bar0", "pcie.memory.write"])
        self.assertIsNone(p["execution_evidence"])
        self.assertEqual(p["actions"][-1]["args"]["data_word"], 0xa5c36e91)
        for m in ("missing_dependency", "bad_offset", "outside", "bad_phase", "oversized"):
            doc = copy.deepcopy(self.mem_spec)
            req = doc["actions"][2]
            if m == "missing_dependency":
                req["depends_on"] = []
            elif m == "bad_offset":
                req["args"]["offset"] = 4094
            elif m == "outside":
                req["args"]["offset"] = 4096
            elif m == "bad_phase":
                req["phase"] = "init"
            else:
                req["args"]["data_word"] = 1 << 32
            with self.subTest(case=m), self.assertRaises(ScenarioError):
                self.resolve(doc)

    def test_ingress_is_backpressured_without_fake_memory(self):
        rtl = (ROOT/"dv/pcie_link/tb_pcie_cross_link.sv").read_text()
        rc = (ROOT/"dv/pcie_link/host_link_vproc.cpp").read_text()
        self.assertIn(".m_tlp_axis_tready(1'b0)", rtl)
        self.assertIn("PCIE_EP_MEM_TLP_BACKPRESSURE", rtl)
        self.assertIn("memWrite(address,bytes,4,", rc)
        self.assertIn("A posted MWr has no Cpl", rc)

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
