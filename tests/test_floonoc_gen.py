"""SoC-driven FlooGen profiles: all eight real network RTL generation scopes.

These tests validate intended topology and native parameter patching. They do
not claim router elaboration or AXI traffic simulation has passed.
"""
import copy
from pathlib import Path
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import floonoc_gen


class FlooNoCProfilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())

    def test_eight_independent_local_and_global_nocs(self):
        nocs = floonoc_gen.profiles(copy.deepcopy(self.soc), self.knobs)
        self.assertEqual(set(nocs), {
            "compute0_local_data", "compute0_local_config",
            "compute1_local_data", "compute1_local_config",
            "memory0_local_data", "memory0_local_config",
            "global_data", "global_config"})
        self.assertEqual(len({p["path"] for p in nocs.values()}), 8)
        for name, entry in nocs.items():
            cfg = entry["config"]
            self.assertEqual(cfg["network_type"], "axi")
            self.assertEqual(cfg["routing"]["route_algo"], "XY")
            self.assertTrue(any(ep.get("mgr_port_protocol") for ep in cfg["endpoints"]), name)
            self.assertTrue(any(ep.get("sbr_port_protocol") for ep in cfg["endpoints"]), name)
            self.assertEqual(len(cfg["connections"]), len(cfg["endpoints"]))
            grid = cfg["routers"][0]["array"]
            self.assertGreaterEqual(grid[0] * grid[1], len(cfg["endpoints"]))
            self.assertEqual(cfg["routers"][0]["degree"], 5)

    def test_compute0_can_boot_compute1_via_global_noc(self):
        cfg = floonoc_gen.profiles(self.soc, self.knobs)["global_data"]["config"]
        eps = {e["name"]: e for e in cfg["endpoints"]}
        self.assertIn("compute1_sram", eps)
        self.assertEqual(eps["compute1_sram"]["addr_range"]["base"], 0x11000000)
        self.assertEqual(eps["compute0_sram"]["addr_range"]["base"], 0x10000000)
        self.assertIn("memory_ingress0", eps)
        self.assertIn("memory_ingress1", eps)

    def test_local_data_routes_local_and_remote_sram(self):
        nocs = floonoc_gen.profiles(self.soc, self.knobs)
        for own, other in (("compute0", "compute1"), ("compute1", "compute0")):
            eps = {x["name"]: x for x in nocs[own + "_local_data"]["config"]["endpoints"]}
            self.assertEqual(eps["sram"]["addr_range"]["base"],
                             int(next(x["base"] for x in self.soc["address_map"]["data"]
                                      if x["name"] == own + ".sram"), 0))
            remote = eps["global_out"]["addr_range"]
            self.assertTrue(any(x["base"] in (0x10000000, 0x11000000)
                                for x in remote))
        eps = {x["name"]: x for x in nocs["compute0_local_data"]["config"]["endpoints"]}
        self.assertIn("boot_rom", eps)
        self.assertIn("boot_flash", eps)

    def test_all_config_fabrics_use_axi4_single_beat_transport(self):
        nocs = floonoc_gen.profiles(self.soc, self.knobs)
        for name, entry in nocs.items():
            cfg = entry["config"]
            if entry["plane"] == "config":
                self.assertEqual({p["data_width"] for p in cfg["protocols"]}, {32})
                self.assertEqual({p["addr_width"] for p in cfg["protocols"]}, {32})
                self.assertEqual({p["id_width"] for p in cfg["protocols"]}, {1})
                self.assertEqual({p["protocol"] for p in cfg["protocols"]}, {"AXI4"})
                self.assertEqual(entry["native_parameters"]["MaxUniqueIds"], 2)
                self.assertIs(entry["native_parameters"]["AtopSupport"], False)
                self.assertEqual(entry["native_parameters"]["MaxAtomicTxns"], 0)
            else:
                self.assertEqual({p["data_width"] for p in cfg["protocols"]}, {64})
                self.assertEqual({p["addr_width"] for p in cfg["protocols"]}, {64})

    def test_global_config_routes_to_every_subsystem(self):
        nocs = floonoc_gen.profiles(self.soc, self.knobs)
        targets = {x["name"]: x for x in nocs["global_config"]["config"]["endpoints"]}
        self.assertIn("compute0_regs", targets)
        self.assertIn("compute1_regs", targets)
        self.assertIn("memory0_regs", targets)
        self.assertTrue(any(w["base"] == 0x40020000 for w in targets["compute0_regs"]["addr_range"]))
        self.assertEqual(targets["memory0_regs"]["addr_range"]["base"], 0x40030000)

    def test_disable_atomic_reservation_without_reducing_id_capacity(self):
        nocs = floonoc_gen.profiles(self.soc, self.knobs)
        self.assertEqual(nocs["global_config"]["native_parameters"]["MaxUniqueIds"], 2)
        self.assertEqual(nocs["global_data"]["native_parameters"]["MaxUniqueIds"], 4)
        for name, design in nocs.items():
            self.assertFalse(design["native_parameters"]["AtopSupport"], name)
            self.assertEqual(design["native_parameters"]["MaxAtomicTxns"], 0, name)

    def test_reject_atomic_reservations_in_non_atomic_soc(self):
        knobs = copy.deepcopy(self.knobs)
        knobs["fabric_parameters"]["local_config"]["MaxAtomicTxns"] = 1
        with self.assertRaisesRegex(floonoc_gen.NoCGenerationError, "ATOPs unsupported"):
            floonoc_gen.profiles(self.soc, knobs)
        knobs = copy.deepcopy(self.knobs)
        knobs["fabric_parameters"]["global_data"]["AtopSupport"] = True
        with self.assertRaisesRegex(floonoc_gen.NoCGenerationError, "ATOPs unsupported"):
            floonoc_gen.profiles(self.soc, knobs)

    def test_native_upstream_chimney_knobs_are_applied(self):
        # Simulates the exact anchor emitted by pinned upstream FlooGen.
        minimal = ("module floo_example(input logic clk);\n"
                   "floo_axi_chimney #(\n"
                   "  .ChimneyCfg(set_ports(ChimneyDefaultCfg, 1'b0, 1'b1)),\n"
                   "  .RouteCfg(RouteCfg)\n) u_ni();\nendmodule\n")
        params = self.knobs["fabric_parameters"]["global_data"]
        modified, count = floonoc_gen.native_bindings(minimal, params)
        self.assertEqual(count, 1)
        self.assertIn("c.MaxTxns = 8;", modified)
        self.assertIn("c.MaxTxnsPerId = 9;", modified)
        self.assertIn("c.MaxUniqueIds = 4;", modified)
        self.assertIn(".AtopSupport(1'b0)", modified)
        self.assertIn(".MaxAtomicTxns(0)", modified)
        self.assertIn(".ChimneyCfg(set_ports(xezim_chimney_cfg(),", modified)
        with self.assertRaisesRegex(floonoc_gen.NoCGenerationError, "anchor"):
            floonoc_gen.native_bindings("module empty; endmodule", params)

    def test_target_only_ni_requires_no_rob_but_preserves_manager_rob(self):
        # This models both roles actually emitted by pinned FlooGen.
        # Upstream floo_axi_chimney NoMgrPortRobType asserts at time zero
        # if a target-only chimney is given NormalRoB.
        mini = (
            "module dual(input logic clk);\\n"
            "floo_axi_chimney #(\\n"
            " .ChimneyCfg(set_ports(ChimneyDefaultCfg, 1'b0, 1'b1))\\n"
            ") source_ni();\\n"
            "floo_axi_chimney #(\\n"
            " .ChimneyCfg(set_ports(ChimneyDefaultCfg, 1'b1, 1'b0))\\n"
            ") target_ni();\\n"
            "endmodule\\n"
        )
        source, count = floonoc_gen.native_bindings(
            mini, self.knobs["fabric_parameters"]["memory_local_data"])
        self.assertEqual(count, 2)
        self.assertIn("c.BRoBType = NormalRoB;", source)
        self.assertIn("c.RRoBType = NormalRoB;", source)
        self.assertIn("c.BRoBType = NoRoB;", source)
        self.assertIn("c.RRoBType = NoRoB;", source)
        self.assertIn(
            ".ChimneyCfg(set_ports(xezim_chimney_cfg_no_mgr(), 1'b1, 1'b0))",
            source)
        self.assertIn(
            ".ChimneyCfg(set_ports(xezim_chimney_cfg(), 1'b0, 1'b1))",
            source)
        self.assertEqual(source.count(".AtopSupport(1'b0)"), 2)

    def test_reject_upstream_power_of_two_rob_usage_counter_mismatch(self):
        knobs = copy.deepcopy(self.knobs)
        knobs["fabric_parameters"]["global_data"]["MaxTxnsPerId"] = 8
        with self.assertRaisesRegex(
                floonoc_gen.NoCGenerationError, "power-of-two MaxTxnsPerId"):
            floonoc_gen.profiles(self.soc, knobs)

    def test_new_compute_instance_produces_two_more_local_nocs(self):
        soc = copy.deepcopy(self.soc)
        soc["subsystems"].insert(2, {
            "name": "compute2", "type": "compute",
            "cpu": {"ip": "picorv32", "bus": "axi4_lite", "adapter": "picorv32_axi"}
        })
        soc["networks"]["global_config"]["reachable_subsystems"].insert(2, "compute2")
        soc["address_map"]["data"].append({
            "name": "compute2.sram", "base": "0x12000000", "size": "0x00100000"
        })
        soc["address_map"]["config"].append({
            "name": "compute2.dma", "base": "0x40040000", "size": "0x10000"
        })
        got = floonoc_gen.profiles(soc, self.knobs)
        self.assertIn("compute2_local_config", got)
        self.assertIn("compute2_local_data", got)
        self.assertEqual(len(got), 10)
        global_eps = {e["name"] for e in got["global_data"]["config"]["endpoints"]}
        self.assertIn("compute2_sram", global_eps)


if __name__ == "__main__":
    unittest.main()
