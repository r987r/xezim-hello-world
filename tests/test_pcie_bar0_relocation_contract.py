"""Keep the new relocation mode real and separate from digital PIPE claims."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PcieBarRelocationSourceTests(unittest.TestCase):
    def test_real_bridge_floonoc_and_full_span_authorization(self):
        rtl = (ROOT/"dv/pcie0/pcie_noc_tb.sv").read_text()
        for token in ("pcie_axi_master #(", "floo_xezim_pcie0_local_data_noc u_noc",
                      "axi_sram_target #(", "pcie_bar0_noc_translate u_aw_relocate",
                      "pcie_bar0_noc_translate u_ar_relocate",
                      "aw_transfer_bytes", "ar_transfer_bytes",
                      "authorized_write_bursts", "w_authorized",
                      "pcie_req.w_valid = m_axi_wvalid && (!BAR0_RELOCATE || w_authorized)",
                      "m_axi_wready = pcie_rsp.w_ready && (!BAR0_RELOCATE || w_authorized)",
                      "m_axi_awaddr[63:32]", "m_axi_araddr[63:32]",
                      "&& (!BAR0_RELOCATE || aw_authorized)",
                      "&& (!BAR0_RELOCATE || ar_authorized)",
                      "$fatal(1, \"PCIe BAR0 invalid"):
            self.assertIn(token,rtl)

    def test_real_byte_regression_runs_both_modes(self):
        runner = (ROOT/"dv/pcie0/run_noc_smoke.py").read_text()
        noc = (ROOT/"dv/pcie0/noc_smoke.py").read_text()
        self.assertIn("dv/pcie_link/bar0_noc_translate.sv",runner)
        self.assertIn('parameters={"BAR0_RELOCATE": int(bar_relocate)}',runner)
        self.assertIn("run(bar_relocate=False)",runner)
        self.assertIn("run(bar_relocate=True)",runner)
        self.assertIn("0x80001000",noc)
        self.assertIn("(0xff0,",noc)
        self.assertIn("assert bytes(got) == payload",noc)


if __name__=="__main__":
    unittest.main()
