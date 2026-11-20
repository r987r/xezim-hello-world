"""Ensure the source-qualified BAR wrapper patch cannot silently drift."""
from __future__ import annotations

import unittest

from tools.pcie_cfg_overlay import overlay


ORIGINAL_EXCERPT = """module pcie_cfg_wrapper
    output pcie_config_reg__out_t hwif_out
);
  //Ports
  pcie_config_handler #(
      .DATA_WIDTH(DATA_WIDTH)
  ) pcie_config_handler_inst (
      .s_axil_rdata         (s_axil_rdata),
      .s_axil_rvalid        (s_axil_rvalid)
  );
  pcie_config_reg pcie_config_reg_inst (
      .s_axil_rdata  (s_axil_rdata),
      .hwif_out      (hwif_out)
  );
endmodule
"""


class OverlayTests(unittest.TestCase):
    def test_overlay_reuses_original_configuration_components(self):
        patched = overlay(ORIGINAL_EXCERPT)
        self.assertIn("pcie_bar0_host_cfg bar0_host_cfg_inst", patched)
        self.assertIn(".s_axil_rdata         (bar0_host_read_data)", patched)
        self.assertIn(".s_axil_rdata  (bar0_rdl_read_data)", patched)
        self.assertIn("bar0_device_aperture_i", patched)
        self.assertEqual(patched.count("pcie_config_reg pcie_config_reg_inst"), 1)
        self.assertEqual(patched.count("pcie_config_handler_inst"), 1)

    def test_missing_original_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "drift"):
            overlay(ORIGINAL_EXCERPT.replace(
                ".s_axil_rdata  (s_axil_rdata),",
                ".s_axil_rdata  (renamed),"))
        with self.assertRaisesRegex(ValueError, "drift"):
            overlay(ORIGINAL_EXCERPT.replace(
                "    output pcie_config_reg__out_t hwif_out",
                "    output pcie_config_reg__out_t new_hwif_out"))


if __name__ == "__main__":
    unittest.main()
