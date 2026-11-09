"""Selected RTL staging is only a checked snapshot, never generated hardware."""
import copy
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
import stage_selected_rtl as stage_mod


class StagedSelectedRtlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        (self.root / "config/soc.yaml").write_text("name: sample_soc\n")
        self.folder = self.root / ".tools/regression/chip-combined"
        self.folder.mkdir(parents=True)
        self.variant = self.folder / "variant/soc_top.sv"
        self.variant.parent.mkdir()
        self.variant.write_text("module soc_top; wire combined; endmodule\n")
        (self.folder / "sources.f").write_text(str(self.variant)+"\n")
        self.archive = self.folder / "selected-rtl/deadbeef"
        copied = self.archive / ".tools/regression/chip-combined/variant/soc_top.sv"
        copied.parent.mkdir(parents=True)
        copied.write_bytes(self.variant.read_bytes())
        self.sha = hashlib.sha256(self.variant.read_bytes()).hexdigest()
        self.source = ".tools/regression/chip-combined/variant/soc_top.sv"
        self.manifest = {
            "archive": self.archive.relative_to(self.root).as_posix(),
            "selected_soc_top": self.source,
            "generated_sha256": {self.source: self.sha},
            "source_sha256": {self.source: self.sha},
            "include_headers_sha256": {},
            "compiler_input_sha256": "a"*64,
            "manifest_sha256": "b"*64,
            "filelist_sha256": hashlib.sha256((self.folder/"sources.f").read_bytes()).hexdigest(),
            "compiled_top": "full_chip_tb",
        }
        self.definition = {
            "top": "full_chip_tb", "sources": "noc",
            "firmware_mode": "ethernet_ddr_pcie",
        }
        self.out = self.root / ".tools/review-stages"

    def stage(self, **kwargs):
        with patch.object(stage_mod, "verify_selected_archive", return_value=self.manifest):
            return stage_mod.stage(self.root, "chip-combined",
                                   self.definition, self.out, **kwargs)

    def test_real_selected_variant_copy_has_exact_bytes_and_fail_closed_manifest(self):
        value = self.stage()
        self.assertIn("ethernet-ddr-pcie", value["hardware_variant"])
        self.assertEqual(value["selected_top_sha256"], self.sha)
        self.assertFalse(value["generator_reproducible"])
        self.assertFalse(value["bit_connectivity_proven"])
        self.assertFalse(value["protocol_traffic_observed"])
        location = self.out / "sample_soc" / value["hardware_variant"]
        self.assertEqual(stage_mod.verify_stage(location), value)
        self.assertEqual((location/"snapshot"/self.source).read_bytes(),
                         self.variant.read_bytes())

    def test_duplicate_fails_without_explicit_replace(self):
        value = self.stage()
        with self.assertRaisesRegex(stage_mod.PromotionError, "already exists"):
            self.stage()
        self.assertEqual(self.stage(replace=True), value)

    def test_reject_modified_archived_selected_top(self):
        self.archive.joinpath(self.source).write_text("modified")
        with self.assertRaisesRegex(stage_mod.PromotionError, "differs"):
            self.stage()
        self.archive.joinpath(self.source).write_bytes(self.variant.read_bytes())
        self.stage()
        folder = self.out/"sample_soc"/stage_mod.config_target(self.definition)
        (folder/"snapshot"/self.source).write_text("changed")
        with self.assertRaisesRegex(stage_mod.PromotionError, "changed"):
            stage_mod.verify_stage(folder)

    def test_reject_generator_owned_output_and_foreign_profile(self):
        with patch.object(stage_mod, "verify_selected_archive", return_value=self.manifest):
            with self.assertRaisesRegex(stage_mod.PromotionError, "generator-owned"):
                stage_mod.stage(self.root, "chip-combined", self.definition,
                                self.root / "gen/projects")
        with self.assertRaisesRegex(stage_mod.PromotionError, "full-chip"):
            self.stage_with_definition({"top":"not_chip"})

    def stage_with_definition(self, definition):
        with patch.object(stage_mod, "verify_selected_archive", return_value=self.manifest):
            return stage_mod.stage(self.root,"chip-combined",definition,self.out)


if __name__ == "__main__":
    unittest.main()
