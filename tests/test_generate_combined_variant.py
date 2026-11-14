"""Real combined source publisher: no snapshot-only acceptance or fake RTL PASS."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_combined_variant as publisher


class Completed:
    returncode = 0
    stderr = ""


class CombinedGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "config").mkdir()
        (self.root / "config/soc.yaml").write_text("name: xezim_soc_dv\n")
        (self.root / "config/regression.yaml").write_text(
            "tests:\n  chip-ethernet-ddr-pcie:\n"
            "    top: full_chip_tb\n    firmware_mode: ethernet_ddr_pcie\n")
        self.files = {
            publisher.SOURCE_ROOT + "variant/soc_top.sv": (
                b'module soc_top;\n  .InitFile("' +
                publisher.SOURCE_ROOT.encode() + b'variant/flash.hex")\n' +
                b'  .InitFile("' + publisher.SOURCE_ROOT.encode() +
                b'variant/bootrom.hex")\nendmodule\n'),
            publisher.SOURCE_ROOT + "variant/full_chip_tb.sv": (
                b'module full_chip_tb;\n  $readmemh("' +
                publisher.SOURCE_ROOT.encode() + b'variant/compute0.hex", expected);\n'
                b'  $readmemh("' + publisher.SOURCE_ROOT.encode() +
                b'variant/compute1.hex", expected);\nendmodule\n'),
            publisher.SOURCE_ROOT + "variant/manifest.json": (
                json.dumps({"file": publisher.SOURCE_ROOT + "variant/flash.hex"}) +
                "\n").encode(),
            publisher.SOURCE_ROOT + "variant/flash.hex": b"deadbeef\n",
            publisher.SOURCE_ROOT + "variant/bootrom.hex": b"12345678\n",
            publisher.SOURCE_ROOT + "variant/compute0.hex": b"abc\n",
            publisher.SOURCE_ROOT + "variant/compute1.hex": b"def\n",
            publisher.SOURCE_ROOT + "ddr_noc/noc/floonoc/global_data/floo_xezim_global_data_noc.sv":
                b"module floo_xezim_global_data_noc; endmodule\n",
            publisher.DDR_ROOT + "soc_ddr4_sim.v": b"module soc_ddr4_sim; endmodule\n",
        }
        for name, data in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        hashes = {k: hashlib.sha256(v).hexdigest() for k, v in self.files.items()}
        generated = {k: v for k, v in hashes.items()
                     if k.startswith(publisher.SOURCE_ROOT)}
        other = {f"rtl/third_party_{i:03d}.sv": "f"*64
                 for i in range(312 - len(hashes))}
        self.manifest = {
            "source_count": 312, "source_sha256": {**hashes, **other},
            "generated_sha256": generated,
            "compiler_input_sha256": "1"*64, "filelist_sha256": "2"*64,
        }
        self.calls = []

    def runner(self, args, cwd):
        self.calls.append((args, cwd))
        return Completed()

    def generate(self):
        with patch.object(publisher, "verify_selected_archive",
                          return_value=self.manifest):
            return publisher.emit(self.root, self.root / "published",
                                  runner=self.runner)

    def test_real_selected_bytes_publish_with_portable_images(self):
        manifest = self.generate()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0][-4:],
                         ["chip-ethernet-ddr-pcie", "--stage", "files", "--fail-fast"])
        folder = self.root / "published"
        self.assertEqual(manifest["source_count"], 312)
        self.assertTrue((folder / ".generated-combined").is_file())
        self.assertEqual(manifest["evidence"],
                         "generator_owned_selected_source_review_not_elaborated_or_simulated")
        for item in ("rtl/soc_top.sv", "rtl/full_chip_tb.sv", "rtl/manifest.json"):
            raw = (folder / item).read_bytes()
            self.assertNotIn(b".tools/regression/", raw)
            self.assertIn(b"gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/rtl/", raw)
        for item in ("rtl/flash.hex", "rtl/bootrom.hex",
                     "controller/gateware/soc_ddr4_sim.v"):
            self.assertTrue((folder / item).is_file())

    def test_modified_original_real_rtl_fails_before_publication(self):
        path = self.root / publisher.SOURCE_ROOT / "variant/soc_top.sv"
        path.write_bytes(b"module false_top; endmodule")
        with patch.object(publisher, "verify_selected_archive",
                          return_value=self.manifest):
            with self.assertRaisesRegex(publisher.CombinedGenerationError, "differs"):
                publisher.emit(self.root, self.root / "published", runner=self.runner)

    def test_unknown_or_duplicate_temporary_paths_fail_closed(self):
        source = self.files[publisher.SOURCE_ROOT + "variant/soc_top.sv"]
        with self.assertRaisesRegex(publisher.CombinedGenerationError, "still references"):
            publisher.portable_image_paths(
                source + b'// .tools/regression/other/stale\n',
                "xezim_soc_dv", "rtl/soc_top.sv")
        with self.assertRaisesRegex(publisher.CombinedGenerationError, "unique"):
            publisher.portable_image_paths(
                source + b'// ' + publisher.SOURCE_ROOT.encode() +
                b'variant/flash.hex\n', "xezim_soc_dv", "rtl/soc_top.sv")

    def test_wrong_selected_compiler_count_fails_closed(self):
        self.manifest["source_count"] = 311
        with patch.object(publisher, "verify_selected_archive",
                          return_value=self.manifest):
            with self.assertRaisesRegex(publisher.CombinedGenerationError, "count"):
                publisher.emit(self.root, self.root / "published", runner=self.runner)


if __name__ == "__main__":
    unittest.main()
