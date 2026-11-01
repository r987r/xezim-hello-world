import copy
import sys
from pathlib import Path
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import socgen


class SocConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def test_baseline_routes_and_boundaries(self):
        m = socgen.validate(copy.deepcopy(self.base))
        self.assertEqual(m["ingress"], 2)
        self.assertEqual(len(m["targets"]), 2)
        self.assertEqual([x["name"] for x in m["targets"]], ["memory0.hbm0", "memory0.hbm1"])
        self.assertEqual([x["base"] for x in m["targets"]], [0x100000000, 0x140000000])
        self.assertEqual(len(m["subsystems"]), 3)

    def test_generation_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            cfg = ROOT / "config/soc.yaml"
            socgen.run(cfg,out)
            first = (out/"hbm_tb.sv").read_bytes()
            socgen.run(cfg,out)
            self.assertEqual((out/"hbm_tb.sv").read_bytes(), first)
            self.assertIn(b"axi_crossbar",first)
            self.assertIn(b"axi_route_monitor",first)
            self.assertIn(b"N_IN = 2",first)

    def test_overlapping_data_addresses_rejected(self):
        doc=copy.deepcopy(self.base)
        doc["address_map"]["data"][3]["base"] = '0x100000000'
        with self.assertRaisesRegex(socgen.ConfigError,"overlap"):
            socgen.validate(doc)

    def test_unknown_subsystem_rejected(self):
        doc=copy.deepcopy(self.base)
        doc["subsystems"][0]["type"]="unknown"
        with self.assertRaisesRegex(socgen.ConfigError,"unknown subsystem"):
            socgen.validate(doc)

    def test_changing_ingress_without_matching_vip_rejected(self):
        doc=copy.deepcopy(self.base)
        doc["subsystem_types"]["hbm"]["data_noc"]["ingress_ports"]=3
        with self.assertRaisesRegex(socgen.ConfigError,"master agents"):
            socgen.validate(doc)

    def test_extra_compute_instance_needs_no_new_sv(self):
        doc=copy.deepcopy(self.base)
        doc["subsystems"].append({"name":"compute2","type":"compute"})
        m=socgen.validate(doc)
        self.assertEqual(len(m["subsystems"]),4)
        self.assertEqual(len(m["targets"]),2)

    def test_invalid_global_output_rejected(self):
        doc=copy.deepcopy(self.base)
        doc["networks"]["global_data"]["hbm_outputs"][1]["target"]="missing.hbm"
        with self.assertRaisesRegex(socgen.ConfigError,"missing target"):
            socgen.validate(doc)


if __name__ == "__main__":
    unittest.main()
