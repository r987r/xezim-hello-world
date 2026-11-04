"""Boot and DMA share the same SRAM region ownership contract."""
import copy
from pathlib import Path
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sram_layout import build_sram_layout, PAYLOAD_START


class SramLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())

    def test_primary_claims_and_lifetimes(self):
        s0 = build_sram_layout(self.cfg, "compute0")
        s1 = build_sram_layout(self.cfg, "compute1")
        self.assertEqual((s0.firmware.start, s0.firmware.size), (0x10000000, 256))
        self.assertEqual((s0.mailbox.start, s0.mailbox.size), (0x10000400, 96))
        self.assertIsNone(s1.mailbox)
        self.assertEqual(s0.descriptors.start, 0x10001000)
        self.assertEqual(s0.payload.start, 0x10000000 + PAYLOAD_START)
        self.assertEqual(s1.descriptors.start, 0x11001000)
        self.assertTrue(s0.boot_scratch.size > 0)
        self.assertEqual(s0.boot_scratch.lifetime, "after_quiescence")
        self.assertEqual(s0.firmware.lifetime, "live")
        self.assertTrue(s0.descriptors.contains(0x10001000, 3200))
        self.assertFalse(s0.descriptors.contains(0x10001000, 4200))

    def test_mailbox_overlap_fails_before_dma_or_boot_generation(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["verification"]["full_chip_boot"]["mailbox_offset"] = "0x0fe0"
        with self.assertRaises(ValueError):
            build_sram_layout(cfg, "compute0")

    def test_relocated_base_and_model_size(self):
        cfg = copy.deepcopy(self.cfg)
        for region in cfg["address_map"]["data"]:
            if region["name"] == "compute0.sram":
                region["base"] = "0x12000000"
        layout = build_sram_layout(cfg, "compute0")
        self.assertEqual(layout.mailbox.start, 0x12000400)
        self.assertEqual(layout.descriptors.start, 0x12001000)
        cfg["boot"]["simulation_sram_bytes"] = 4096
        with self.assertRaises(ValueError):
            build_sram_layout(cfg, "compute0")
