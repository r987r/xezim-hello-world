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
        self.assertEqual(result["link"]["data_width_bits"], 32)
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

    def test_l0_and_bar_may_not_be_asserted_by_declaration(self):
        for key in pcie_link.CAPABILITY_FLAGS:
            with self.subTest(field=key), self.assertRaisesRegex(
                    pcie_link.PcieProviderError, "false qualification"):
                self.choose(lambda p: p["link"].update({key: True}))

    def test_provider_swaps_must_declared_and_have_same_pins(self):
        for key, value in (("lanes", 2), ("data_width_bits", 16),
                           ("datak_width_bits", 1), ("pipe_parallel_clock_mhz", 250)):
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
