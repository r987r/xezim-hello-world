"""#76 source-selected PCIe endpoint DBI frontdoor contract.

This proves generated wiring selection, not actual CPU instruction execution,
trained PHY, or a completed full-chip PCIe memory transaction.
"""
from pathlib import Path
import json
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
import full_chip_gen


class PcieEndpointFrontdoorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())
        cls.manifest = json.loads((ROOT/"gen/supernoc/manifest.json").read_text())

    def test_opt_in_reuses_cpu_config_noc_and_cannot_fake_link(self):
        flash = next(int(x["base"], 0) for x in self.cfg["address_map"]["data"]
                     if x["name"] == "boot.flash")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            full_chip_gen.emit(
                self.cfg, self.manifest, ROOT/"gen/noc/floonoc", root,
                cpu0_run_hook=flash+0x1000, cpu_dma_mode=True,
                pcie_host_mode=True, pcie_outbound_mode=True)
            rtl = (root/"soc_top.sv").read_text()
            self.assertIn("pcie_requester_axi_regs", rtl)
            self.assertIn(".EndpointPrelink(1'b1)", rtl)
            self.assertIn(".EndpointSramBase(32'h12000000)", rtl)
            self.assertIn(".EndpointSramBytes(32'h00100000)", rtl)
            self.assertEqual(rtl.count("u_pcie_requester_csrs"), 1)
            for pin in ("ep_phy_ready_i", "ep_link_up_i",
                        "ep_host_mem_enable_i", "ep_ltssm_l0_i",
                        "ep_noc_ready_i"):
                self.assertIn(f".{pin}(1'b0)", rtl)
            self.assertIn("picorv32_cpu_adapter", rtl)
            self.assertIn("soc_noc u_noc", rtl)
            self.assertIn("m_pcie0_local_config", rtl)

    def test_unselected_host_variant_remains_reserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            full_chip_gen.emit(self.cfg, self.manifest, ROOT/"gen/noc/floonoc",
                               root, pcie_host_mode=True)
            rtl = (root/"soc_top.sv").read_text()
            self.assertNotIn("u_pcie_requester_csrs", rtl)
            self.assertIn("u_reserved_s_pcie0_local_config_controller_regs", rtl)

    def test_no_second_converter_and_window_rejections(self):
        source = (ROOT/"rtl/adapters/pcie_requester_axi_regs.sv").read_text()
        policy = (ROOT/"dv/pcie_link/endpoint_prelink_ctrl.sv").read_text()
        build = (ROOT/"tools/regress.py").read_text()
        self.assertEqual(source.count("axi_to_axi_lite #("), 1)
        for condition in ("wr_offset >= 32'h1000", "wr_offset <= 32'h1018",
                          "rd_offset >= 32'h1000", "wr_offset < 32'h40",
                          "ep_illegal_write", "ep_cfg_write = write_fire && ep_wr_window",
                          "illegal_write ? 2'b10 : 2'b00",
                          "u_endpoint_dbi ("):
            self.assertIn(condition, source)
        self.assertIn("if (!bar_config_committed_o)", policy)
        self.assertIn("if (cfg_wstrb_i != 4'hf)", policy)
        self.assertIn("endpoint_prelink_ctrl.sv", build)


if __name__ == "__main__":
    unittest.main()
