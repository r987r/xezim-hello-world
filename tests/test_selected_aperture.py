"""Physical address windows are source-selected, never local Ethernet constants."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from dv.common.selected_aperture import selected_aperture


class SelectedApertureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def test_live_default_windows_derive_from_authoritative_config(self):
        expected = [
            ("data", "ethernet0.sram"),
            ("config", "ethernet0.ctrl"),
            ("data", "memory0.ddr0"),
        ]
        for plane, name in expected:
            regions = [r for r in self.cfg["address_map"][plane] if r["name"] == name]
            self.assertEqual(len(regions), 1)
            self.assertEqual(selected_aperture(name, plane, plan_path=""),
                             (int(regions[0]["base"], 0), int(regions[0]["size"], 0)))

    def test_plan_picks_exact_source_variant_and_rejects_wrong_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "plan.json"
            p.write_text(json.dumps({
                "report": {"address_map": {
                    "config": "config/soc.yaml", "variant": "architecture"}},
            }))
            self.assertEqual(selected_aperture("ethernet0.sram", "data", plan_path=p),
                             selected_aperture("ethernet0.sram", "data", plan_path=""))
            p.write_text(json.dumps({"report": {"address_map": {
                "config": "../../etc/passwd", "variant": "architecture"}}}))
            with self.assertRaisesRegex(ValueError, "escapes repository"):
                selected_aperture("ethernet0.sram", "data", plan_path=p)
            p.write_text(json.dumps({"report": {}}))
            with self.assertRaisesRegex(ValueError, "no selected SoC"):
                selected_aperture("ethernet0.sram", "data", plan_path=p)

    def test_rejects_unknown_window_or_wrong_plane(self):
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            selected_aperture("ethernet0.ctrl", "data", plan_path="")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            selected_aperture("ethernet0.nonexistent", "config", plan_path="")
        with self.assertRaisesRegex(ValueError, "invalid physical aperture"):
            selected_aperture("ethernet0.sram", "wishbone", plan_path="")


if __name__ == "__main__":
    unittest.main()
