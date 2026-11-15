"""Source-only project-B checks: these are not routed-RTL evidence."""
import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import bootgen
import socgen

PROJECT = ROOT / "config/projects/ethernet-cpu-ddr-pcie/soc.yaml"


class ThreeRegionProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = yaml.safe_load(PROJECT.read_text())
        cls.legacy = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def test_second_project_is_different_and_valid(self):
        meta = socgen.validate(copy.deepcopy(self.project))
        self.assertEqual(meta["name"], "xezim_ethernet_cpu_ddr_pcie")
        self.assertEqual([c["ip"] for c in meta["cpu_instances"]], ["picorv32"])
        self.assertEqual([t["name"] for t in meta["targets"]], ["memory0.ddr0"])
        self.assertEqual(meta["ingress"], 1)
        self.assertNotIn("global_data", meta["fabrics"])
        self.assertEqual(len(meta["direct_data_links"]), 3)
        self.assertEqual(
            [x["name"] for x in self.project["layout"]["regions"]],
            ["ethernet", "cpu_memory", "pcie"])
        self.assertEqual(self.project["layout"]["control_noc"]["edge"], "bottom")
        self.assertEqual(
            set(self.project["networks"]["global_config"]["reachable_subsystems"]),
            {s["name"] for s in self.project["subsystems"]})
        legacy = socgen.validate(copy.deepcopy(self.legacy))
        self.assertEqual(len(legacy["cpu_instances"]), 2)
        self.assertEqual({t["kind"] for t in legacy["targets"]}, {"hbm", "ddr"})

    def test_single_cpu_rom_copy_does_not_release_nonexistent_cpu(self):
        fw = bootgen.build(copy.deepcopy(self.project))
        self.assertEqual(set(fw["images"]), {"compute0"})
        self.assertNotIn("sram1", fw["addresses"])
        self.assertNotIn("reset_ctrl", fw["addresses"])
        self.assertNotIn("signature1", fw["addresses"])
        self.assertFalse(any("release CPU1" in asm for _, asm in fw["bootrom"]))

    def test_direct_topology_rejects_unknown_peer(self):
        cfg = copy.deepcopy(self.project)
        cfg["networks"]["direct_data"]["links"][0]["endpoints"][1] = "unknown0"
        with self.assertRaisesRegex(socgen.ConfigError, "invalid direct data link"):
            socgen.validate(cfg)

    def test_direct_topology_rejects_duplicate_pair(self):
        cfg = copy.deepcopy(self.project)
        cfg["networks"]["direct_data"]["links"].append(
            {"name": "other_name", "endpoints": ["compute0", "ethernet0"],
             "duplex": True})
        with self.assertRaisesRegex(socgen.ConfigError, "duplicate direct data link"):
            socgen.validate(cfg)

    def test_direct_topology_rejects_one_way_alias(self):
        cfg = copy.deepcopy(self.project)
        cfg["networks"]["direct_data"]["links"][0]["duplex"] = False
        with self.assertRaisesRegex(socgen.ConfigError, "invalid direct data link"):
            socgen.validate(cfg)

    def test_direct_topology_rejects_disconnected_region(self):
        cfg = copy.deepcopy(self.project)
        cfg["networks"]["direct_data"]["links"].pop()
        with self.assertRaisesRegex(socgen.ConfigError, "disconnected"):
            socgen.validate(cfg)

    def test_direct_topology_rejects_legacy_global_data_fabric(self):
        cfg = copy.deepcopy(self.project)
        cfg["fabrics"]["global_data"] = {"topology": "mesh", "backend": "floonoc"}
        with self.assertRaisesRegex(socgen.ConfigError, "must not declare"):
            socgen.validate(cfg)

    def test_direct_topology_rejects_ambiguous_fabrics(self):
        cfg = copy.deepcopy(self.project)
        cfg["networks"]["global_data"] = {"protocol": "axi4", "outputs": []}
        with self.assertRaisesRegex(socgen.ConfigError, "exactly one"):
            socgen.validate(cfg)

    def test_direct_topology_rejects_hbm(self):
        cfg = copy.deepcopy(self.project)
        cfg["memory_targets"].append(copy.deepcopy(self.legacy["memory_targets"][0]))
        cfg["address_map"]["data"].append(copy.deepcopy(self.legacy["address_map"]["data"][-2]))
        with self.assertRaisesRegex(socgen.ConfigError, "DDR-only"):
            socgen.validate(cfg)

    def test_layout_cannot_omit_peer(self):
        cfg = copy.deepcopy(self.project)
        cfg["layout"]["regions"][1]["subsystems"] = ["compute0"]
        with self.assertRaisesRegex(socgen.ConfigError, "place each subsystem"):
            socgen.validate(cfg)

    def test_single_core_boot_rejects_secondary_release(self):
        cfg = copy.deepcopy(self.project)
        cfg["boot"]["secondary_release"] = "mmio"
        with self.assertRaisesRegex(socgen.ConfigError, "secondary_release"):
            socgen.validate(cfg)


if __name__ == "__main__":
    unittest.main()
