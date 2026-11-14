"""Provider replacement must be source-owned, pinned and fail-closed."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml

from tools import pcie_link

ROOT = Path(__file__).resolve().parents[1]


class PcieLinkSelectionTests(unittest.TestCase):
    def setUp(self):
        self.doc = yaml.safe_load((ROOT / "config/pcie_link.yaml").read_text())
        self.lock = yaml.safe_load((ROOT / "config/ip.lock.yaml").read_text())

    def choose(self, change):
        data = copy.deepcopy(self.doc)
        change(data["profiles"][data["selected_profile"]])
        originals = [data, self.lock]
        with patch.object(pcie_link, "_load", side_effect=originals):
            return pcie_link.selection(ROOT)

    def test_default_is_separate_pinned_host_endpoint_and_explicitly_unqualified(self):
        result = pcie_link.selection(ROOT)
        self.assertEqual(result["link"]["generation"], 1)
        self.assertEqual(result["link"]["lanes"], 1)
        self.assertEqual(result["link"]["data_width_bits"], 16)
        self.assertEqual(result["link"]["datak_width_bits"], 2)
        self.assertEqual(result["link"]["pipe_parallel_clock_mhz"], 125)
        self.assertNotEqual(result["providers"]["host"]["commit"],
                            result["providers"]["endpoint"]["commit"])
        self.assertEqual(result["providers"]["host"]["license"], "GPL-3.0")
        self.assertIn("needs-review", result["providers"]["endpoint"]["license"])
        self.assertFalse(result["capability"]["l0_trained"])
        self.assertFalse(result["capability"]["digital_phy_sideband_ready"])
        self.assertFalse(result["capability"]["bar0_decode_in_real_controller"])
        self.assertIn("not_executed", result["capability"]["status"])

    def test_generated_files_are_exact_and_source_qualified(self):
        rendered = pcie_link.generated_files(ROOT)
        contract = json.loads(rendered["selection.json"])
        self.assertEqual(contract, pcie_link.selection(ROOT))
        self.assertIn("GPL-3.0", rendered["README.md"])
        self.assertIn("NOT QUALIFIED", rendered["README.md"])
        output = ROOT / "gen/pcie_link"
        for name, content in rendered.items():
            with self.subTest(name=name):
                self.assertEqual((output / name).read_text(), content)

    def test_exact_reviewed_overlay_is_visible_and_fails_unsafe_swaps(self):
        row = pcie_link.selection(ROOT)
        overlays = row["local_source_overlays"]
        self.assertEqual(len(overlays), 1)
        source = ROOT / overlays[0]["path"]
        self.assertEqual(overlays[0]["sha256"],
                         pcie_link.digest(source.read_bytes()))
        self.assertIn("reviewed_source_overlay", overlays[0]["status"])
        for path in ("../../tmp/forged.patch", "/tmp/unreviewed.patch",
                     "config/ip.lock.yaml"):
            with self.subTest(path=path), self.assertRaisesRegex(
                    pcie_link.PcieProviderError, "unsafe source-qualified"):
                self.choose(lambda p: p["endpoint"].update({"patch": path}))

    def test_unqualified_replay_activation_stays_disabled(self):
        # The original pinned replay engine needs cumulative ACK handling,
        # a real AXI ready path, and per-slot accepted-frame checks before
        # activating its occupancy gate. The prior experimental patch
        # regressed a 1024-byte read from offset 7 to offset 1; do not
        # re-enable replay without independent protocol-level tests.
        source=(ROOT/"dv/pcie_link/patches/openpcie_ltssm_comb_assignment.patch").read_text()
        self.assertIn("diff --git a/src/dllp/tlp2dllp.sv",source)
        self.assertNotIn("+        dllp_valid_o = 1'b1;",source)
        self.assertNotIn("+        if (tlp_axis_tready && skid_axis_tvalid && retry_available_i) begin",source)
        self.assertEqual(source.count(
            "+        data_credits_required = (data_length == '0) ? 16'd256 : ((data_length + 16'd3) >> 2);"),2)
        for dw, credits in ((1,1),(4,1),(5,2),(6,2),(7,2),(8,2),(9,3),(31,8),(32,8),(127,32),(0,256)):
            effective=1024 if dw==0 else dw
            self.assertEqual((effective+3)//4,credits)

    def test_endpoint_fc_overlay_is_explicit_and_does_not_fake_credits(self):
        # Source-pinned repair moves one-shot init to the provider's
        # existing dynamic UpdateFC producer; host FC validation remains on.
        source=(ROOT/"dv/pcie_link/patches/openpcie_ltssm_comb_assignment.patch").read_text()
        self.assertIn("diff --git a/src/dllp/pcie_flow_ctrl_init.sv",source)
        self.assertIn("-            next_state        = ST_UPDATE_P;",source)
        self.assertIn("+            next_state        = ST_FC_COMPLETE;",source)
        self.assertNotIn("+            fc2_values_sent_o = '1;",source)
        self.assertNotIn("+            fc1_values_stored_i = '1;",source)
        # PCIe posted-data FC is in 16-byte units: 5..8 DW must use
        # TWO credits, and 0 in the TLP length field means 1024 DW.
        self.assertIn("diff --git a/src/dllp/dllp2tlp.sv",source)
        self.assertEqual(source.count("+          (word_count_r == '0 ? 12'd256 : ((word_count_r + 16'd3) >> 2));"),3)
        self.assertNotIn("+          (word_count_r >> 2 == '0 ? 1'b1 : word_count_r >> 2);",source)
        for dw, credits in ((1,1),(4,1),(5,2),(6,2),(8,2),(9,3),(1023,256),(0,256)):
            effective = 1024 if dw == 0 else dw
            self.assertEqual((effective+3)//4,credits)


    def test_l0_and_bar_may_not_be_asserted_by_declaration(self):
        for key in pcie_link.CAPABILITY_FLAGS:
            with self.subTest(field=key), self.assertRaisesRegex(
                    pcie_link.PcieProviderError, "false qualification"):
                self.choose(lambda p: p["link"].update({key: True}))

    def test_provider_swaps_must_declared_and_have_same_pins(self):
        for key, value in (("lanes", 2), ("data_width_bits", 32),
                           ("datak_width_bits", 4), ("pipe_parallel_clock_mhz", 62.5)):
            with self.subTest(key=key), self.assertRaisesRegex(
                    pcie_link.PcieProviderError, "clock/width"):
                self.choose(lambda p: p["link"].update({key: value}))
        with self.assertRaisesRegex(pcie_link.PcieProviderError, "provider boundary"):
            self.choose(lambda p: p.pop("phy"))
        with self.assertRaisesRegex(pcie_link.PcieProviderError, "pinned"):
            self.choose(lambda p: p["host"].update({"ip_lock": "not_declared"}))
        with self.assertRaisesRegex(pcie_link.PcieProviderError, "root-complex"):
            self.choose(lambda p: p["host"].update({"endpoint_parameter_value": 1}))
        with self.assertRaisesRegex(pcie_link.PcieProviderError, "training"):
            self.choose(lambda p: p["phy"].update({"status_driver": "timer_link_up"}))


if __name__ == "__main__":
    unittest.main()
