"""DDR-B adapter contract tests; these are not full-chip RTL traffic tests."""
from __future__ import annotations

from dataclasses import replace
import copy
from pathlib import Path
import sys
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from soc_bridge_contract import contract, from_repo, translate_access


class DDRBContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[3]
        cls.soc = yaml.safe_load((root / "config/soc.yaml").read_text())
        cls.profile = yaml.safe_load(
            (root / "rtl/memory/ddr4/litedram_sim.yml").read_text())
        cls.geometry = yaml.safe_load(
            (root / "rtl/memory/ddr4/sim_geometry.yml").read_text())

    def validate(self, soc=None, profile=None):
        return contract(soc or self.soc, profile or self.profile, self.geometry)

    def test_matches_real_soc_and_standalone_profile(self):
        result = from_repo()
        self.assertEqual(result.physical_base, 0x140000000)
        self.assertEqual(result.architectural_size, 1 << 30)
        self.assertEqual(result.modeled_size, 32 << 20)
        self.assertEqual(result.fabric_addr_bits, 64)
        self.assertEqual(result.fabric_id_bits, result.controller_id_bits)
        self.assertTrue(result.requires_explicit_init)
        self.assertEqual(result.backend, "litedram_sim")

    def test_no_physical_address_truncation_or_32mib_alias(self):
        w = self.validate()
        for offset in (0, 8, 0x1000, (32 << 20) - 128):
            decoded = translate_access(w, physical=w.physical_base + offset,
                                       length=1, axi_id=15)
            self.assertEqual(decoded["local"], offset)
            self.assertEqual(decoded["id"], 15)
        for offset in (-8, (32 << 20), (1 << 30) - 8, 1 << 30):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                translate_access(w, physical=w.physical_base + offset,
                                 length=1, axi_id=0)

    def test_burst_boundaries_and_ids_fail_closed(self):
        w = self.validate()
        good = translate_access(w, physical=w.physical_base + 0x1000,
                                length=16, axi_id=3)
        self.assertEqual(good["length"], 16)
        for params in (
            {"physical":w.physical_base + 0xff8, "length":2, "axi_id":0},
            {"physical":w.physical_base + (32 << 20)-8, "length":2, "axi_id":0},
            {"physical":w.physical_base + 0x1000, "length":257, "axi_id":0},
            {"physical":w.physical_base + 0x1000, "length":1, "axi_id":16},
            {"physical":w.physical_base + 0x1000, "length":1, "axi_id":0,
             "atop": 1},
            {"physical":w.physical_base + 0x1000, "length":1, "axi_id":0,
             "burst":"WRAP"},
            {"physical":w.physical_base + 0x1000, "length":1, "axi_id":0,
             "beat_bytes":16},
        ):
            with self.subTest(params=params), self.assertRaises(ValueError):
                translate_access(w, **params)

    def test_axi_id_and_data_must_match_without_silent_adaptation(self):
        soc = copy.deepcopy(self.soc)
        soc["buses"]["data"]["id_bits"] = 5
        with self.assertRaisesRegex(ValueError, "SoC AXI"):
            self.validate(soc=soc)
        p = copy.deepcopy(self.profile)
        p["user_ports"]["axi_0"]["data_width"] = 128
        with self.assertRaisesRegex(ValueError, "contract mismatch"):
            self.validate(profile=p)
        p = copy.deepcopy(self.profile)
        p["user_ports"]["axi_0"]["id_width"] = 3
        with self.assertRaisesRegex(ValueError, "contract mismatch"):
            self.validate(profile=p)

    def test_init_is_required_and_config_fabric_not_assumed_ready(self):
        p = copy.deepcopy(self.profile)
        p["user_ports"]["axi_0"]["block_until_ready"] = False
        with self.assertRaisesRegex(ValueError, "blocked until"):
            self.validate(profile=p)
        p = copy.deepcopy(self.profile)
        p["with_refresh"] = False
        with self.assertRaisesRegex(ValueError, "refresh"):
            self.validate(profile=p)

    def test_global_data_route_and_window_are_unique(self):
        soc = copy.deepcopy(self.soc)
        soc["networks"]["global_data"]["outputs"].append(
            {"name":"duplicate_ddr", "target":"memory0.ddr0"})
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.validate(soc=soc)
        soc = copy.deepcopy(self.soc)
        region = next(x for x in soc["address_map"]["data"]
                      if x["name"] == "memory0.ddr0")
        region["base"] = "0x140000001"
        with self.assertRaisesRegex(ValueError, "aligned"):
            self.validate(soc=soc)

    def test_model_size_must_not_exceed_local_bus(self):
        w = self.validate()
        altered = replace(w, controller_addr_bits=20)
        with self.assertRaisesRegex(ValueError, "would truncate"):
            translate_access(altered, physical=w.physical_base + 0x1ff000,
                             length=1, axi_id=0)


if __name__ == "__main__":
    unittest.main()
