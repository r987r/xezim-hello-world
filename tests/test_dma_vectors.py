import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dv.common.dma_vectors import (
    build_dma_vector, DESC, DESC_END, DESC_OFFSET, FLAGS_COPY, FLAGS_IRQ,
)
from tools.memory_service import Pattern


class DmaVectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())

    def test_100_linked_descriptors_and_golden_payloads(self):
        case = build_dma_vector(self.cfg, count=100)
        meta = case.manifest
        self.assertEqual(len(case.source_sram), 16384)
        self.assertEqual(meta["descriptor_head"], 0x10001000)
        self.assertEqual(meta["destination_base"], 0x140000100)
        for i, entry in enumerate(meta["copies"]):
            desc = DESC.unpack_from(case.source_sram, DESC_OFFSET + i*32)
            self.assertEqual(desc, (entry["length"], entry["flags"],
                                    entry["next"], entry["src"], entry["dst"]))
            self.assertEqual(entry["flags"], FLAGS_COPY | (FLAGS_IRQ if i == 99 else 0))
            self.assertEqual(entry["next"], DESC_END if i == 99
                             else meta["descriptor_head"]+(i+1)*32)
            offset = entry["src"]-meta["source_sram_base"]
            self.assertEqual(case.source_sram[offset:offset+entry["length"]],
                             bytes.fromhex(entry["expected_hex"]))
            self.assertEqual(bytes.fromhex(entry["expected_hex"]),
                             Pattern("address_xor", 0x35+29*i).chunk(
                                 entry["src"], entry["length"]))

    def test_dma_only_profile_reuses_boot_space(self):
        case = build_dma_vector(self.cfg, profile="dma_only", count=100)
        meta = case.manifest
        self.assertEqual(meta["descriptor_head"], 0x10000000)
        self.assertEqual(meta["source_pool_start"], 0x10001000)
        self.assertEqual(meta["source_pool_bytes"], 12288)
        self.assertEqual(meta["allocation_profile"], "dma_only")
        self.assertIsNone(meta["sram_layout"]["regions"]["firmware"])
        self.assertEqual(DESC.unpack_from(case.source_sram, 0)[0], 64)
        self.assertEqual(meta["copies"][-1]["next"], DESC_END)
        self.assertEqual(meta["copies"][-1]["flags"], FLAGS_COPY | FLAGS_IRQ)

    def test_supported_local_and_remote_targets(self):
        for destination in ("compute0.sram", "compute1.sram", "memory0.hbm0",
                            "memory0.ddr0"):
            with self.subTest(destination=destination):
                case = build_dma_vector(self.cfg, destination=destination, count=1,
                                        length=65)
                self.assertEqual(case.manifest["copies"][0]["next"], DESC_END)

    def test_readmemh_word_order_and_manifest(self):
        case = build_dma_vector(self.cfg, count=3)
        with tempfile.TemporaryDirectory() as tmp:
            case.write(Path(tmp))
            words = (Path(tmp)/"source_sram.hex").read_text().splitlines()
            self.assertEqual(len(words), 2048)
            restore = b"".join(int(w,16).to_bytes(8,"little") for w in words)
            self.assertEqual(restore, case.source_sram)
            self.assertEqual(json.loads((Path(tmp)/"case.json").read_text())["kind"],
                             "dma_only_not_cold_boot")

    def test_rejects_invalid_inputs(self):
        invalid = ({"count": 129}, {"count": 0}, {"length": 0},
                   {"count": 100, "length": 128}, {"destination": "unknown"},
                   {"subsystem": "unknown"},
                   {"count": 65, "destination": "compute0.sram", "length": 64})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_dma_vector(self.cfg, **kwargs)

    def test_relocation_from_config(self):
        cfg = copy.deepcopy(self.cfg)
        for region in cfg["address_map"]["data"]:
            if region["name"] == "compute0.sram":
                region["base"] = "0x12000000"
        case = build_dma_vector(cfg, destination="memory0.hbm0", count=4)
        self.assertEqual(case.manifest["descriptor_head"], 0x12001000)
        self.assertEqual(case.manifest["copies"][0]["src"], 0x12002000)

    def test_descriptor_layout(self):
        self.assertEqual(DESC.size, 32)
        raw = DESC.pack(0x44332211, 0x88776655, 0x0102030405060708,
                        0x1112131415161718, 0x2122232425262728)
        self.assertEqual(raw[:8].hex(), "1122334455667788")
        self.assertEqual(raw[8:16].hex(), "0807060504030201")
