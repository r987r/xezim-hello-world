"""Generic peripheral routing tests: no custom PCIe-only fabric logic."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import floonoc_gen
import socgen
import supernoc_gen

class PeripheralFabricTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        cls.knobs = yaml.safe_load((ROOT / "config/interface_contracts.yaml").read_text())

    def test_peripheral_generates_both_local_nocs_and_global_links(self):
        c = copy.deepcopy(self.cfg)
        socgen.validate(c)
        nets = floonoc_gen.profiles(c, self.knobs)
        self.assertEqual(len(nets), 12)
        self.assertIn("pcie0_local_data", nets)
        self.assertIn("ethernet0_local_data", nets)
        self.assertIn("ethernet0_local_config", nets)
        self.assertIn("pcie0_local_config", nets)
        def endpoints(name):
            return {x["name"]:x for x in nets[name]["config"]["endpoints"]}
        data = endpoints("pcie0_local_data")
        cfg = endpoints("pcie0_local_config")
        self.assertEqual(set(data), {"host", "global_in", "sram", "global_out"})
        self.assertEqual(set(cfg), {"management", "global_in", "controller_regs", "global_out"})
        self.assertEqual(data["sram"]["addr_range"]["base"], 0x12000000)
        self.assertEqual(cfg["controller_regs"]["addr_range"]["base"], 0x40040000)
        self.assertIn("pcie0", endpoints("global_data"))
        self.assertIn("pcie0_sram", endpoints("global_data"))
        self.assertIn("pcie0", endpoints("global_config"))
        self.assertIn("pcie0_regs", endpoints("global_config"))
        eth_d, eth_c = endpoints("ethernet0_local_data"), endpoints("ethernet0_local_config")
        self.assertEqual(set(eth_d), {"packet_dma", "global_in", "sram", "global_out"})
        self.assertEqual(set(eth_c), {"management", "global_in", "controller_regs", "global_out"})
        self.assertEqual(eth_d["sram"]["addr_range"]["base"], 0x13000000)
        self.assertEqual(eth_c["controller_regs"]["addr_range"]["base"], 0x40050000)
        self.assertIn("ethernet0", endpoints("global_data"))
        self.assertIn("ethernet0_sram", endpoints("global_data"))
        self.assertIn("ethernet0", endpoints("global_config"))
        self.assertIn("ethernet0_regs", endpoints("global_config"))

    def test_peripheral_instance_name_independent_of_ip_and_global_path(self):
        c = copy.deepcopy(self.cfg)
        sub = next(s for s in c["subsystems"] if s["type"] == "peripheral")
        sub["name"] = "ethernet2"
        sub["ip"] = "liteeth"
        for plane, old, new in (("data", "pcie0.sram", "ethernet2.sram"),
                                 ("config", "pcie0.ctrl", "ethernet2.ctrl")):
            row = next(x for x in c["address_map"][plane] if x["name"] == old)
            row["name"] = new
        reachable = c["networks"]["global_config"]["reachable_subsystems"]
        reachable[reachable.index("pcie0")] = "ethernet2"
        socgen.validate(c)
        nets = floonoc_gen.profiles(c, self.knobs)
        self.assertIn("ethernet2_local_data", nets)
        self.assertIn("ethernet2_local_config", nets)

    def test_missing_cdc_or_sram_mapping_fails(self):
        for mode in ("cdc", "sram", "double", "bad_ip"):
            c = copy.deepcopy(self.cfg)
            sub = next(s for s in c["subsystems"] if s["type"] == "peripheral")
            if mode == "cdc":
                sub["clock_domain"] = "pcie_phy"
            elif mode == "sram":
                c["address_map"]["data"] = [r for r in c["address_map"]["data"]
                                           if r["name"] != "pcie0.sram"]
            elif mode == "double":
                sub["data_initiator"] = "global_in"
            else:
                sub["ip"] = "bad-ip"
            with self.subTest(mode=mode), self.assertRaises(socgen.ConfigError):
                socgen.validate(c)

    def test_shared_wrapper_links_both_global_planes(self):
        nets = floonoc_gen.profiles(self.cfg, self.knobs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {}
            for name, entry in nets.items():
                loc = root / entry["path"] / "floogen.yaml"
                loc.parent.mkdir(parents=True, exist_ok=True)
                loc.write_text(yaml.safe_dump(entry["config"]))
                manifest[name] = {"config":loc.relative_to(root).as_posix(),
                                  "top_module":f"floo_xezim_{name}_noc",
                                  "plane":entry["plane"]}
            (root / "manifest.json").write_text(json.dumps({"networks":manifest}))
            out = root / "supernoc" / "supernoc_tb.sv"
            out.parent.mkdir(exist_ok=True)
            meta = supernoc_gen.emit(self.cfg, root, out)
            edges = {(x["from"],x["to"]) for x in meta["connections"]}
            self.assertIn(("pcie0_local_data.global_out", "global_data.pcie0"), edges)
            self.assertIn(("global_data.pcie0_sram", "pcie0_local_data.global_in"), edges)
            self.assertIn(("pcie0_local_config.global_out", "global_config.pcie0"), edges)
            self.assertIn(("global_config.pcie0_regs", "pcie0_local_config.global_in"), edges)
            self.assertIn(("ethernet0_local_data.global_out", "global_data.ethernet0"), edges)
            self.assertIn(("global_data.ethernet0_sram", "ethernet0_local_data.global_in"), edges)
            self.assertIn(("ethernet0_local_config.global_out", "global_config.ethernet0"), edges)
            self.assertIn(("global_config.ethernet0_regs", "ethernet0_local_config.global_in"), edges)

if __name__=="__main__":
    unittest.main()
