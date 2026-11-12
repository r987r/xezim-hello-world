"""Pin the original OpenPCIe ConfigWr0 decoder's real payload contract.

This is a drift/structural check. The cross-provider BAR0 matrix supplies
the actual over-link data/ready/response/host-readback qualification.
"""
import unittest

from tools.pcie_cfg_overlay import overlay_decode


# Exact source-pattern fixtures from the pinned original decoder. Do not
# add a second host model, a direct BAR register write, or a synthetic Cpl.
ORIGINAL = """module pcie_config_decode;
  always_comb begin
        if (skid_axis_tvalid && !skid_axis_tlast) begin
          D.tlp_is_3dw             = '0;
          D.tlp_data               = '0;
          D.tlp_is_sop             = '1;
          tlp_dw0                  = skid_axis_tdata;
          if (tlp_dw0.byte0.Fmt inside {TLP_4DW_ND, TLP_4DW_WD}) begin
            D.tlp_is_pd = '1;
          end
        end
      ST_TLP_STREAM: begin
        skid_axis_tready = '1;
        if (s_axis_tvalid) begin
          D.tlp_data[(3-Q.word_count)*32+:32] = tlp_byte_swapped;
          D.word_count = Q.word_count + 1'b1;
          if (s_axis_tlast) begin
            D.tlp_is_eop = '1;
            D.state = ST_TLP_SEND;
          end
        end
      end
      ST_TLP_SEND: begin
        tlp_valid = '1;
        if (tlp_ready) begin
          tlp_tdata    = '0;
          tlp_strb     = '0;
          D.tlp_is_sop = '0;
          D.tlp_is_eop = '0;
          tlp_eop      = Q.tlp_is_eop;
          tlp_sop      = Q.tlp_is_sop;
          D.state      = ST_TLP_STREAM;
        end
      end
  end
endmodule
"""


class OpenPcieCfgDecodeTests(unittest.TestCase):
    def test_written_dword_is_forwarded_not_zeroed(self):
        patched = overlay_decode(ORIGINAL)
        self.assertIn("TLP_3DW_WD, TLP_4DW_WD", patched)
        self.assertIn("D.tlp_is_pd              = '0;", patched)
        self.assertIn("D.word_count             = '0;", patched)
        self.assertIn("if (skid_axis_tvalid) begin", patched)
        self.assertIn("if (skid_axis_tlast) begin", patched)
        self.assertIn("D.tlp_data[Q.word_count*32+:32] = tlp_byte_swapped;", patched)
        self.assertIn("tlp_tdata = Q.tlp_data[DATA_WIDTH-1:0];", patched)
        self.assertIn("tlp_strb  = Q.tlp_is_pd ? '1 : '0;", patched)
        self.assertLess(
            patched.index("tlp_tdata = Q.tlp_data"),
            patched.index("if (tlp_ready) begin", patched.index("ST_TLP_SEND: begin")),
        )
        self.assertNotIn("tlp_tdata    = '0;", patched)

    def test_decoder_patch_refuses_unpinned_source_shape(self):
        invalid = [
            ORIGINAL.replace("TLP_4DW_ND, TLP_4DW_WD", "TLP_3DW_WD, TLP_4DW_WD"),
            ORIGINAL.replace("if (s_axis_tvalid) begin", "if (skid_axis_tvalid) begin"),
            ORIGINAL.replace("tlp_tdata    = '0;", "tlp_tdata = '0;"),
            ORIGINAL.replace("D.tlp_data[(3-Q.word_count)*32+:32]", "D.tlp_data[0+:32]"),
        ]
        for source in invalid:
            with self.subTest(change=source[:35]), self.assertRaisesRegex(
                ValueError, "drift"
            ):
                overlay_decode(source)

    def test_no_double_patch(self):
        with self.assertRaisesRegex(ValueError, "drift"):
            overlay_decode(overlay_decode(ORIGINAL))


if __name__ == "__main__":
    unittest.main()
