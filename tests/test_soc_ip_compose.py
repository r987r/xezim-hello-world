"""Typed type/port/clock/IP mapping; manifest never claims live RTL."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from soc_ir import compile_ir
from soc_ip_compose import compose, registry, CompositionError


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.graph = json.loads((ROOT / "gen/diagrams/noc-topology.json").read_text())
        cls.ir = compile_ir(cls.soc, cls.graph)

    def test_current_subsystems_use_one_contract_per_type(self):
        value = compose(self.soc, self.ir)
        subs = {row["name"]: row for row in value["instances"]}
        self.assertEqual(set(subs),
                         {"compute0", "compute1", "memory0", "pcie0", "ethernet0"})
        self.assertEqual(subs["compute0"]["implementation"]["cpu"], "picorv32")
        self.assertEqual(subs["compute1"]["implementation"]["cpu"], "serv")
        self.assertEqual(subs["pcie0"]["implementation"]["ip"], "verilog_pcie")
        self.assertEqual(subs["ethernet0"]["implementation"]["ip"],
                         "ethernet_queue_mac")
        self.assertEqual(
            {target["name"] for target in subs["memory0"]["implementation"]["targets"]},
            {"memory0.hbm0", "memory0.ddr0"})
        self.assertEqual(value, compose(self.soc, self.ir))
        self.assertIn("not_compiled_pin_binding", value["evidence"])

    def test_registered_port_roles_and_incompatible_widths(self):
        contracts = registry(64, 32)
        good = contracts.check_link("compute", "data_master",
                                    "memory", "data_target")
        self.assertEqual(good["bits"], 64)
        self.assertEqual(good["evidence"], "declarative_only")
        with self.assertRaisesRegex(ValueError, "protocol or direction"):
            contracts.check_link("memory", "data_target",
                                 "compute", "data_master")
        with self.assertRaisesRegex(ValueError, "protocol or direction"):
            contracts.check_link("compute", "config_master",
                                 "memory", "data_target")
        with self.assertRaises(CompositionError):
            registry(0, 32)

    def test_bad_instance_ip_and_unsupported_clock_fail_closed(self):
        for mutation in ("missing", "clock", "type", "cpu"):
            with self.subTest(mutation=mutation):
                soc = copy.deepcopy(self.soc)
                ir = copy.deepcopy(self.ir)
                if mutation == "missing":
                    ir["instances"] = [x for x in ir["instances"]
                                       if not x["id"].startswith("pcie0")]
                if mutation == "clock":
                    soc["subsystems"][3]["clock_domain"] = "pcie_ref"
                if mutation == "type":
                    soc["subsystems"][3]["type"] = "undocumented"
                    ir["subsystems"] = sorted(soc["subsystems"], key=lambda x: x["name"])
                if mutation == "cpu":
                    soc["subsystems"][0]["cpu"].pop("ip")
                with self.assertRaises((CompositionError, ValueError)):
                    compose(soc, ir)

    def test_reject_foreign_ir_and_stale_address_map(self):
        foreign = copy.deepcopy(self.ir)
        foreign["project"] = "other_soc"
        with self.assertRaisesRegex(CompositionError, "foreign"):
            compose(self.soc, foreign)
        stale = copy.deepcopy(self.ir)
        stale["subsystems"] = []
        with self.assertRaisesRegex(CompositionError, "inventory"):
            compose(self.soc, stale)


if __name__ == "__main__":
    unittest.main()
