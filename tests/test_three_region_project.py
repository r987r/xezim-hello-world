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
        self.assertEqual(len(meta["direct_data_links"]), 4)
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
        self.assertEqual(len(profiles), 17)  # 8 local + global config + 8 directed links
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

    def test_ethernet_has_two_independent_addr_decoded_data_outputs(self):
        import floonoc_gen
        cfg = copy.deepcopy(self.project)
        knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())
        profiles = floonoc_gen.profiles(cfg, knobs)
        ethernet = profiles["ethernet0_local_data"]["config"]
        compute = profiles["compute0_local_data"]["config"]
        ports = {ep["name"]: ep for ep in ethernet["endpoints"]}
        self.assertIn("to_compute0", ports)
        self.assertIn("to_memory0", ports)
        ddr_base = int(next(x["base"] for x in cfg["address_map"]["data"]
                            if x["name"] == "memory0.ddr0"), 0)
        cpu_base = int(next(x["base"] for x in cfg["address_map"]["data"]
                            if x["name"] == "compute0.sram"), 0)

        def decodes(port, address):
            ranges = port.get("addr_range", [])
            if isinstance(ranges, dict):
                ranges = [ranges]
            return any(int(x["base"]) <= address < int(x["base"]) + int(x["size"])
                       for x in ranges)

        self.assertTrue(decodes(ports["to_memory0"], ddr_base))
        self.assertFalse(decodes(ports["to_compute0"], ddr_base))
        self.assertTrue(decodes(ports["to_compute0"], cpu_base))
        self.assertFalse(decodes(ports["to_memory0"], cpu_base))
        compute_ports = {ep["name"]: ep for ep in compute["endpoints"]}
        # CPU, DMA and PCIe can still reach DDR via central compute->memory.
        self.assertTrue(decodes(compute_ports["to_memory0"], ddr_base))
        self.assertFalse(decodes(compute_ports["to_ethernet0"], ddr_base))
        for direction in (("ethernet0", "memory0"), ("memory0", "ethernet0")):
            src, dest = direction
            self.assertIn(
                "direct_l0_ethernet_memory_" + src + "_to_" + dest,
                profiles)

    def test_local_router_decodes_no_duplicate_target_windows(self):
        import floonoc_gen
        cfg = copy.deepcopy(self.project)
        knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())
        profiles = floonoc_gen.profiles(cfg, knobs)
        for name, row in profiles.items():
            endpoints = row["config"]["endpoints"]
            ranges = []
            for ep in endpoints:
                if "sbr_port_protocol" not in ep:
                    continue
                windows = ep.get("addr_range", [])
                if isinstance(windows, dict):
                    windows = [windows]
                ranges.extend((int(w["base"]), int(w["base"]) + int(w["size"]), ep["name"])
                              for w in windows)
            for i, (a, b, left) in enumerate(ranges):
                for c, d, right in ranges[i+1:]:
                    self.assertTrue(b <= c or d <= a,
                                    f"{name}: {left} and {right} overlap")

    def test_phased_single_cpu_firmware_reuses_bootstrap(self):
        import chip_bootgen
        fw = chip_bootgen.build(copy.deepcopy(self.project))
        self.assertEqual(len(fw["cores"]), 1)
        self.assertEqual(list(fw["images"]), ["compute0"])
        self.assertNotIn("reset_ctrl", fw["addresses"])
        self.assertFalse(any("reset" in asm.lower() for _, asm in fw["rom"]))

if __name__ == "__main__":
    unittest.main()
