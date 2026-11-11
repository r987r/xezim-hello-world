"""Preserve fast modeled PCIe traffic while adding opt-in digital link.

Regression policy is intentionally source-level, not a synthetic traffic PASS.
The legacy TLP-to-AXI hardware tests are independently executed by their
original GitHub workflows and the canonical regression runner.
"""
import unittest
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]


class PcieModeCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.regression=yaml.safe_load((ROOT/"config/regression.yaml").read_text())
        cls.provider=yaml.safe_load((ROOT/"config/pcie_link.yaml").read_text())

    def test_original_fast_modes_remain_selected_and_reported(self):
        tests=self.regression["tests"]
        for name in ("chip-pcie-host","chip-pcie-outbound"):
            with self.subTest(name=name):
                t=tests[name]
                self.assertEqual(t["engine"],"cocotb-verilator")
                self.assertEqual(t["top"],"full_chip_tb")
                self.assertIn("flow",t["report"])
                self.assertIn("axi",t["report"])
                self.assertIn("protocols",t["report"])
                self.assertEqual(t["report"]["protocols"]["sources"]["pcie0.rx_req"]["protocol"],"pcie")
        self.assertIn("chip-pcie-host",self.regression["suites"]["full"])
        self.assertEqual(self.regression["suites"]["pcie-next"],["chip-pcie-outbound"])

    def test_real_link_opt_in_has_separate_provider_and_no_fake_qualification(self):
        p=self.provider["profiles"][self.provider["selected_profile"]]
        self.assertEqual(p["link"]["data_width_bits"],16)
        self.assertEqual(p["link"]["datak_width_bits"],2)
        self.assertEqual(p["link"]["pipe_parallel_clock_mhz"],125)
        self.assertEqual(p["link"]["generation"],1)
        self.assertFalse(p["link"]["trained_l0"])
        self.assertFalse(p["link"]["hardware_config_enumeration"])
        self.assertNotIn("pcie-digital-link",self.regression["tests"])
        self.assertEqual(p["phy"]["implementation"],"behavioral_digital_pipe_only")

    def test_same_source_flow_and_report_tools_remain_owned_by_runner(self):
        # Neither the existing legacy target nor the dedicated digital PHY
        # workflow is silently promoted to another runtime or a fake PASS.
        legacy=self.regression["tests"]["chip-pcie-host"]
        self.assertEqual(legacy["module"],"dv.pcie0.test_full_chip_host")
        self.assertIn("init",legacy["report"]["flow"]["required_steps"])
        self.assertIn("run",legacy["report"]["flow"]["required_steps"])
        self.assertIn("check",legacy["report"]["flow"]["required_steps"])
        self.assertEqual(legacy["report"]["protocols"]["sources"]["pcie0.tx_cpl"]["protocol"],"pcie")


if __name__=="__main__":
    unittest.main()
