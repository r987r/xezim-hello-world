"""Native open-source AXI fabric configuration and connectivity tests."""
import copy
import json
from pathlib import Path
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import socgen
from fabric_config import FabricConfigError, memory_connectivity


class FabricConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def test_example_is_a_real_executable_fabric_profile(self):
        p = ROOT / "config/examples/memory-fabric-connectivity.yaml"
        doc = yaml.safe_load(p.read_text())
        meta = socgen.validate(doc)
        self.assertEqual(meta["memory_crossbar_parameters"]["M_ISSUE"], [4, 4])
        self.assertEqual(meta["memory_connectivity"]["native_read_mask"], 15)
        self.assertEqual(meta["memory_connectivity"]["agent_mask"], 15)
        meta["target_count"] = len(meta["targets"])
        rtl = socgen.generate_top(meta)
        self.assertIn(".M_CONNECT_READ(4'hf)", rtl)
        self.assertIn(".M_CONNECT_WRITE(4'hf)", rtl)
        self.assertIn(".M_ISSUE({32'd4, 32'd4})", rtl)
        self.assertIn(".ENABLED_TARGETS(TARGET_ALLOW[i*N_MEM +: N_MEM])", rtl)
        self.assertIn(".ENABLED_ROUTES(TARGET_ALLOW)", rtl)
        ir = socgen.fabric_ir(meta)
        self.assertEqual(ir["memory"]["connectivity"]["agent_mask"], 15)

    def test_sparse_example_is_executable(self):
        p = ROOT / "config/examples/memory-fabric-sparse.yaml"
        doc = yaml.safe_load(p.read_text())
        meta = socgen.validate(doc)
        self.assertEqual(meta["memory_connectivity"]["native_read_mask"], 9)
        self.assertEqual(meta["memory_connectivity"]["agent_mask"], 9)
        meta["target_count"] = len(meta["targets"])
        rtl = socgen.generate_top(meta)
        self.assertIn(".M_CONNECT_READ(4'h9)", rtl)
        self.assertIn("TARGET_ALLOW = 4'h9", rtl)

    def test_sparse_matrix_is_not_ignored(self):
        doc = copy.deepcopy(self.base)
        fabric = doc["fabrics"]["memory_data"]
        fabric["connectivity"] = {
            "read": {"memory_ingress0": ["memory0.hbm0"],
                     "memory_ingress1": ["memory0.ddr0"]},
            "write": {"memory_ingress0": ["memory0.hbm0"],
                      "memory_ingress1": ["memory0.ddr0"]}}
        meta = socgen.validate(doc)
        self.assertEqual(meta["memory_connectivity"]["native_read_mask"], 9)
        self.assertEqual(meta["memory_connectivity"]["agent_mask"], 9)
        meta["target_count"] = len(meta["targets"])
        rtl = socgen.generate_top(meta)
        self.assertIn(".M_CONNECT_READ(4'h9)", rtl)

    def test_unknown_parameters_fail(self):
        doc = copy.deepcopy(self.base)
        doc["fabrics"]["memory_data"]["parameters"] = {"FAKE_FABRIC_KNOB": 5}
        with self.assertRaisesRegex(socgen.ConfigError, "unsupported"):
            socgen.validate(doc)

    def test_unknown_ports_fail(self):
        doc = copy.deepcopy(self.base)
        doc["fabrics"]["memory_data"]["parameters"] = {"M_ISSUE": {"nonexistent": 1}}
        with self.assertRaisesRegex(socgen.ConfigError, "per-port keys"):
            socgen.validate(doc)

    def test_invalid_register_type_fails(self):
        doc = copy.deepcopy(self.base)
        doc["fabrics"]["memory_data"]["parameters"] = {"S_AW_REG_TYPE": 3}
        with self.assertRaisesRegex(socgen.ConfigError, "in \[0, 2\]"):
            socgen.validate(doc)

    def test_missing_route_fails(self):
        doc = copy.deepcopy(self.base)
        doc["fabrics"]["memory_data"]["connectivity"] = {
            "read": {"memory_ingress0": ["memory0.hbm0"],
                     "memory_ingress1": ["memory0.hbm0"]},
            "write": {"memory_ingress0": ["memory0.hbm0"],
                      "memory_ingress1": ["memory0.hbm0"]}}
        with self.assertRaisesRegex(socgen.ConfigError, "each memory target"):
            socgen.validate(doc)

    def test_asymmetric_routes_fail_until_dv_supports_them(self):
        doc = copy.deepcopy(self.base)
        doc["fabrics"]["memory_data"]["connectivity"] = {
            "read": {"memory_ingress0": ["memory0.hbm0"],
                     "memory_ingress1": ["memory0.ddr0"]},
            "write": {"memory_ingress0": ["memory0.hbm0", "memory0.ddr0"],
                      "memory_ingress1": ["memory0.ddr0"]}}
        with self.assertRaisesRegex(socgen.ConfigError, "asymmetric"):
            socgen.validate(doc)

    def test_planned_backend_knobs_fail(self):
        doc = copy.deepcopy(self.base)
        doc["fabrics"]["global_data"]["parameters"] = {"routing": "xy"}
        with self.assertRaisesRegex(socgen.ConfigError, "executable backend"):
            socgen.validate(doc)

    def test_backward_compatibility(self):
        meta = socgen.validate(copy.deepcopy(self.base))
        self.assertNotIn("memory_connectivity", meta)
        self.assertNotIn("memory_crossbar_parameters", meta)


if __name__ == "__main__":
    unittest.main()
