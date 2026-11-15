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



    def test_direct_floogen_profiles_use_real_bidirectional_nis(self):
        import floonoc_gen
        cfg = copy.deepcopy(self.project)
        knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())
        profiles = floonoc_gen.profiles(cfg, knobs)
        self.assertNotIn("global_data", profiles)
        self.assertIn("global_config", profiles)
        self.assertEqual(len(profiles), 15)  # 4 subsystem pairs + config + six directions
        for link in cfg["networks"]["direct_data"]["links"]:
            a, b = link["endpoints"]
            for src, dst in ((a, b), (b, a)):
                name = "direct_" + link["name"] + "_" + src + "_to_" + dst
                selected = profiles[name]["config"]
                self.assertEqual(
                    [e["name"] for e in selected["endpoints"]],
                    ["ingress", "egress"])
                self.assertEqual(selected["protocols"][0]["id_width"], 5)
                self.assertEqual(selected["protocols"][1]["id_width"], 5)
                own = profiles[src + "_local_data"]["config"]
                peer = profiles[dst + "_local_data"]["config"]
                self.assertIn("to_" + dst,
                              [ep["name"] for ep in own["endpoints"]])
                self.assertIn("from_" + src,
                              [ep["name"] for ep in peer["endpoints"]])
        legacy = floonoc_gen.profiles(copy.deepcopy(self.legacy), knobs)
        self.assertIn("global_data", legacy)
        self.assertEqual(len(legacy), 12)

    def test_phased_single_cpu_firmware_reuses_bootstrap(self):
        import chip_bootgen
        fw = chip_bootgen.build(copy.deepcopy(self.project))
        self.assertEqual(len(fw["cores"]), 1)
        self.assertEqual(list(fw["images"]), ["compute0"])
        self.assertNotIn("reset_ctrl", fw["addresses"])
        self.assertFalse(any("reset" in asm.lower() for _, asm in fw["rom"]))

if __name__ == "__main__":
    unittest.main()
