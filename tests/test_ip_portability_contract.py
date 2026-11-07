"""Mutation gates for IP backend replacement: verify unsupported swaps fail closed.

The *actual* implementation registry and config are the source of truth.
These tests intentionally do not invent a second topology, vendor allowlist,
hardware backend or BFM. A negative is NOT proof of pluggable replacement.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import floonoc_gen
import socgen


class IPPortabilityGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())

    def test_executed_noc_profiles_match_config_selected_roles(self):
        # The source-selected existing backend generates every configured
        # local/global scope. Do not maintain a parallel expected mesh list.
        soc = copy.deepcopy(self.soc)
        meta = socgen.validate(soc)
        profiles = floonoc_gen.profiles(soc, self.knobs)
        expected = {"global_data", "global_config"}
        for subsystem in soc["subsystems"]:
            expected.add(subsystem["name"] + "_local_data")
            expected.add(subsystem["name"] + "_local_config")
        self.assertEqual(set(profiles), expected)
        self.assertEqual(set(meta["fabrics"]), set(soc["fabrics"]))
        for name, obj in profiles.items():
            self.assertEqual(obj["plane"], "config" if name.endswith("_config") else "data")
            selected = soc["fabrics"][obj["family"]]["backend"]
            self.assertEqual(selected, "floonoc", name)

    def test_noc_backend_swap_does_not_silently_use_floogen(self):
        soc = copy.deepcopy(self.soc)
        # A vendor registry entry is not an implemented full-chip emitter.
        soc["fabrics"]["global_data"]["backend"] = "pulp_axi"
        with self.assertRaisesRegex(floonoc_gen.NoCGenerationError,
                                    "backend=floonoc"):
            floonoc_gen.profiles(soc, self.knobs)
        # The standalone memory crossbar has a distinct backend registry.
        soc = copy.deepcopy(self.soc)
        soc["fabrics"]["memory_data"]["backend"] = "pulp_axi"
        with self.assertRaisesRegex(socgen.ConfigError,
                                    "No RTL generator implemented yet"):
            socgen.validate(soc)

    def test_ddr_controller_swap_does_not_appear_qualified(self):
        soc = copy.deepcopy(self.soc)
        target = next(t for t in soc["memory_targets"] if t["kind"] == "ddr")
        target["controller"] = "alternate_ddr"
        with self.assertRaisesRegex(socgen.ConfigError,
                                    "unsupported ddr controller"):
            socgen.validate(soc)
        # A new simulation model must not silently inherit AXI RAM proof.
        soc = copy.deepcopy(self.soc)
        target = next(t for t in soc["memory_targets"] if t["kind"] == "ddr")
        target["simulation"]["backend"] = "other_dfi_model"
        with self.assertRaisesRegex(socgen.ConfigError,
                                    "only axi_ram behavioral model"):
            socgen.validate(soc)

    def test_cpu_and_dma_swaps_need_real_adapters(self):
        soc = copy.deepcopy(self.soc)
        soc["subsystem_types"]["compute"]["dma"] = "alternate_dma"
        with self.assertRaisesRegex(socgen.ConfigError,
                                    "requires common pulp_idma"):
            socgen.validate(soc)
        soc = copy.deepcopy(self.soc)
        core = next(sub for sub in soc["subsystems"] if sub["type"] == "compute")
        core["cpu"] = {"ip": "alternate_cpu", "bus": "axi4_lite",
                       "adapter": "alternate_adapter"}
        with self.assertRaisesRegex(socgen.ConfigError, "unknown CPU IP"):
            socgen.validate(soc)


if __name__ == "__main__":
    unittest.main()
