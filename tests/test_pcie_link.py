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

    def test_selected_endpoint_demux_backpressure_fix_is_real_and_auditable(self):
        # Production-selected provider patch, not just standalone self-test.
        selected = pcie_link.selection(ROOT)
        overlay = ROOT / selected["local_source_overlays"][0]["path"]
        source = overlay.read_text()
        self.assertIn("diff --git a/src/dllp/axis_user_demux.sv", source)
        self.assertEqual(source.count("+            s_axis_tready = dllp_ready;"), 1)
        self.assertEqual(source.count("+            s_axis_tready = tlp_ready;"), 1)
        self.assertEqual(source.count(
            "+            if (s_axis_tready && !s_axis_tlast) next_state = ST_DLLP;"), 1)
        self.assertEqual(source.count(
            "+            if (s_axis_tready && !s_axis_tlast) next_state = ST_TLP;"), 1)
        self.assertIn("axis_demux_backpressure_tb.sv",
                      (ROOT / ".github/workflows/pcie-digital-link.yml").read_text())
        self.assertIn("tools/pcie_demux_backpressure.py",
                      (ROOT / ".github/workflows/pcie-digital-link.yml").read_text())

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

    def test_selected_endpoint_overlay_repairs_demux_handshake(self):
        # Regress the selected-provider path, not just standalone self-test
        # instrumentation: losing this hunk silently revives #76 CplH stalls.
        patch_path = ROOT / "dv/pcie_link/patches/openpcie_ltssm_comb_assignment.patch"
        contents = patch_path.read_text()
        heading = "diff --git a/src/dllp/axis_user_demux.sv b/src/dllp/axis_user_demux.sv"
        self.assertEqual(contents.count(heading), 1)
        demux = contents.split(heading, 1)[1]
        for removed, added in (
            ("-            s_axis_tready = m_tlp_axis_tready;",
             "+            s_axis_tready = tlp_ready;"),
            ("-            s_axis_tready = m_dllp_axis_tready;",
             "+            s_axis_tready = dllp_ready;"),
            ("-            next_state = ST_TLP;",
             "+            if (s_axis_tready && !s_axis_tlast) next_state = ST_TLP;"),
            ("-            next_state = ST_DLLP;",
             "+            if (s_axis_tready && !s_axis_tlast) next_state = ST_DLLP;"),
        ):
            self.assertIn(removed, demux)
            self.assertIn(added, demux)
        selected = pcie_link.selection(ROOT)
        self.assertEqual(len(selected["local_source_overlays"]), 1)
        self.assertEqual(selected["local_source_overlays"][0]["path"],
                         "dv/pcie_link/patches/openpcie_ltssm_comb_assignment.patch")
        self.assertEqual(selected["local_source_overlays"][0]["sha256"],
                         pcie_link.digest(patch_path.read_bytes()))
        selection_json = json.loads((ROOT / "gen/pcie_link/selection.json").read_text())
        self.assertEqual(selection_json["local_source_overlays"],
                         selected["local_source_overlays"])

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
