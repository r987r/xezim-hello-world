"""Unit-level configuration validation for the planned linkable subsystem NoCs."""
import copy
from pathlib import Path
import sys
import unittest
import yaml
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from interface_contracts import InterfaceError, build
import floonoc_gen

class InterfaceSizingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.soc = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())
        cls.floo = floonoc_gen.profiles(cls.soc, cls.knobs)["global_data"]["config"]

    def validate(self, soc=None, knobs=None, floo=None):
        return build(soc or copy.deepcopy(self.soc),
                     knobs or copy.deepcopy(self.knobs),
                     floo or copy.deepcopy(self.floo))

    def test_all_local_and_global_fabrics_present(self):
        graph = self.validate()
        self.assertEqual(set(graph["fabrics"]), {
            "compute0.local_data", "compute0.local_config",
            "compute1.local_data", "compute1.local_config",
            "memory0.memory_data", "memory0.local_data", "memory0.local_config",
            "pcie0.local_data", "pcie0.local_config",
            "global_data", "global_config"})
        self.assertEqual(graph["ports"]["compute0.local_data.global_out"]["id_bits"], 5)
        self.assertEqual(graph["ports"]["global_data.compute0_in"]["id_bits"], 5)
        self.assertEqual(graph["ports"]["memory0.memory_data.memory_ingress0_in"]["id_bits"], 4)
        self.assertEqual(graph["ports"]["memory0.memory_data.hbm0_out"]["id_bits"], 5)
        self.assertEqual(graph["ports"]["compute1.local_data.dma_in"]["max_pending_reads"], 2)
        self.assertEqual(graph["ports"]["compute1.local_data.cpu_in"]["max_pending_reads"], 1)
        self.assertTrue(all(x["status"] == "planned" for x in graph["links"]))

    def test_every_noc_uses_floonoc(self):
        graph = self.validate()
        for key, fabric in graph["fabrics"].items():
            if key == "memory0.memory_data":
                self.assertEqual(fabric["backend"], "verilog_axi")
            else:
                self.assertEqual(fabric["backend"], "floonoc", key)

    def test_wrong_floogen_ids_fails(self):
        floo = copy.deepcopy(self.floo)
        floo["protocols"][0]["id_width"] = 4
        with self.assertRaisesRegex(InterfaceError, "FlooGen axi_in"):
            self.validate(floo=floo)

    def test_wrong_floogen_data_width_fails(self):
        floo = copy.deepcopy(self.floo)
        floo["protocols"][0]["data_width"] = 32
        with self.assertRaisesRegex(InterfaceError, "FlooGen axi_in"):
            self.validate(floo=floo)

    def test_wrong_floogen_memory_map_fails(self):
        floo = copy.deepcopy(self.floo)
        next(e for e in floo["endpoints"] if e["name"] == "memory_ingress0")["addr_range"]["base"] = 0xdead0000
        with self.assertRaisesRegex(InterfaceError, "address range"):
            self.validate(floo=floo)

    def test_unknown_instance_fails(self):
        knobs = copy.deepcopy(self.knobs)
        knobs["instance_overrides"]["compute42"] = {"local_data": {"max_pending_reads": 2}}
        with self.assertRaisesRegex(InterfaceError, "unknown instance_overrides"):
            self.validate(knobs=knobs)

    def test_unknown_port_fails(self):
        knobs = copy.deepcopy(self.knobs)
        knobs["port_overrides"]["compute0.invalid"] = {"max_pending_reads": 2}
        with self.assertRaisesRegex(InterfaceError, "unknown port_overrides"):
            self.validate(knobs=knobs)

    def test_width_override_requires_adapter(self):
        knobs = copy.deepcopy(self.knobs)
        knobs["port_overrides"]["compute0.local_data.global_out"] = {"data_bits": 32}
        with self.assertRaisesRegex(InterfaceError, "requires named upstream adapter"):
            self.validate(knobs=knobs)

    def test_max_pending_limits_floogen(self):
        knobs = copy.deepcopy(self.knobs)
        knobs["fabric_parameters"]["global_data"]["MaxTxns"] = 2
        with self.assertRaisesRegex(InterfaceError, "MaxTxns below"):
            self.validate(knobs=knobs)

    def test_axi_lite_never_bursts(self):
        knobs = copy.deepcopy(self.knobs)
        knobs["defaults"]["axi4_lite"]["max_burst_beats"] = 2
        with self.assertRaisesRegex(InterfaceError, "AXI4-Lite"):
            self.validate(knobs=knobs)

    def test_add_compute_subsystem_scales_ports(self):
        soc = copy.deepcopy(self.soc)
        soc["subsystems"].insert(2, {"name":"compute2", "type":"compute",
                                     "cpu":{"ip":"picorv32", "bus":"axi4_lite", "adapter":"picorv32_axi"}})
        soc["networks"]["global_config"]["reachable_subsystems"].insert(2,"compute2")
        # Adding a compute instance requires explicit non-overlapping
        # SRAM and DMA-CSR address windows. The RTL generator must not invent them.
        soc["address_map"]["data"].append(
            {"name": "compute2.sram", "base": "0x13000000", "size": "0x00100000"})
        soc["address_map"]["config"].append(
            {"name": "compute2.dma", "base": "0x40050000", "size": "0x10000"})
        floo = copy.deepcopy(self.floo)
        floo = floonoc_gen.profiles(soc, self.knobs)["global_data"]["config"]
        graph = self.validate(soc=soc, floo=floo)
        self.assertIn("compute2.local_data", graph["fabrics"])
        self.assertIn("global_data.compute2_in", graph["ports"])
        self.assertEqual(graph["fabrics"]["global_data"]["n_sources"], 4)

if __name__ == "__main__":
    unittest.main()
