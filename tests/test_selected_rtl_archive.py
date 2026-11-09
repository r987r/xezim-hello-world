"""#163: exact selected compiler-input snapshot is not execution evidence."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from selected_rtl_provenance import (
    archive_selected_filelist, explain_target, verify_selected_archive
)


class SelectedRtlArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.out = self.root / ".tools/regression/example"
        self.out.mkdir(parents=True)
        self.soc = self.root / "gen/chip/soc_top.sv"
        self.soc.parent.mkdir(parents=True)
        self.soc.write_text("module soc_top; endmodule\n")
        self.tb = self.root / "dv/test_tb.sv"
        self.tb.parent.mkdir()
        self.tb.write_text("module full_chip_tb; endmodule\n")
        self.definition = {
            "sources": "noc", "engine": "cocotb-verilator",
            "top": "full_chip_tb", "logical_test": "memory-roundtrip",
        }
        self.filelist = self.out / "sources.f"
        self.filelist.write_text(str(self.soc) + "\n" + str(self.tb) + "\n")
        source_sha = hashlib.sha256(self.filelist.read_bytes()).hexdigest()
        self.plan = {
            **self.definition, "target": "example", "source_target": "noc",
            "sources": [str(self.soc), str(self.tb)],
            "includes": [], "defines": [], "firmware_mode": None,
            "identity": {"legacy_target": "example", "identity_sha256": "test",
                         "selection": {"filelist_sha256": source_sha}},
        }

    def make_archive(self):
        (self.out / "plan.json").write_text(json.dumps(self.plan) + "\n")
        (self.out / "identity.json").write_text(json.dumps(
            self.plan["identity"]) + "\n")
        return archive_selected_filelist(
            self.root, "example", self.definition, self.plan, self.filelist)

    def test_archive_preserves_exact_generated_top_and_source_hashes(self):
        value = self.make_archive()
        self.assertEqual(value["source_count"], 2)
        self.assertEqual(value["selected_soc_top"], "gen/chip/soc_top.sv")
        self.assertEqual(len(value["compiler_input_sha256"]), 64)
        archived_top = self.root / value["archive"] / "gen/chip/soc_top.sv"
        self.assertEqual(archived_top.read_bytes(), self.soc.read_bytes())
        self.assertNotIn("dv/test_tb.sv", value["generated_sha256"])
        self.assertEqual(verify_selected_archive(
            self.root, "example", self.definition), value)
        self.assertIn("not_elaborated", value["evidence"])

    def test_variant_top_overrides_default_and_copies_firmware(self):
        variant = self.out / "variant"
        variant.mkdir()
        alternate = variant / "soc_top.sv"
        alternate.write_text("module soc_top; wire real_ddr; endmodule\n")
        (variant / "flash.hex").write_text("12345678\n")
        self.plan["sources"][0] = str(alternate)
        self.plan["firmware_mode"] = "ethernet_ddr_pcie"
        self.filelist.write_text(str(alternate) + "\n" + str(self.tb) + "\n")
        self.plan["identity"]["selection"]["filelist_sha256"] = hashlib.sha256(
            self.filelist.read_bytes()).hexdigest()
        value = self.make_archive()
        self.assertIn("variant/soc_top.sv", value["selected_soc_top"])
        self.assertIn(".tools/regression/example/variant/flash.hex", value["generated_sha256"])
        self.assertNotIn("gen/chip/soc_top.sv", value["source_sha256"])
        self.assertTrue((self.root / value["archive"] /
                         ".tools/regression/example/variant/flash.hex").is_file())

    def test_network_compilation_can_omit_single_top_and_records_all_networks(self):
        self.definition.pop("top")
        self.plan.pop("top")
        self.plan["engine"] = self.definition["engine"] = "xezim-compile"
        network = self.root / "gen/noc/floonoc/noc_top.sv"
        network.parent.mkdir(parents=True)
        network.write_text("module noc_top; endmodule\n")
        package = network.parent / "noc_pkg.sv"
        package.write_text("package noc_pkg; endpackage\n")
        compiled = self.out / "local_data.f"
        compiled.write_text(self.filelist.read_text()
                            + str(package) + "\n" + str(network) + "\n")
        self.plan["selected_networks"] = {
            "local_data": {"top": "noc_top", "filelist": str(compiled)}
        }
        value = self.make_archive()
        self.assertIsNone(value["compiled_top"])
        self.assertIsNone(value["selected_soc_top"])
        self.assertEqual(value["source_count"], 4)
        self.assertIn("local_data", value["network_filelists"])
        self.assertTrue((self.root / value["archive"] / "local_data.f").is_file())
        compiled.write_text("tampered\n")
        with self.assertRaisesRegex(ValueError, "NoC filelist"):
            verify_selected_archive(self.root, "example", self.definition)

    def test_include_headers_are_attested_and_fail_on_change(self):
        headers = self.root / "rtl/headers"
        headers.mkdir(parents=True)
        header = headers / "defs.svh"
        header.write_text("`define WIDTH 32\n")
        self.plan["includes"] = [str(headers)]
        self.filelist.write_text(
            "+incdir+" + str(headers) + "\n"
            + str(self.soc) + "\n" + str(self.tb) + "\n")
        self.plan["identity"]["selection"]["filelist_sha256"] = hashlib.sha256(
            self.filelist.read_bytes()).hexdigest()
        value = self.make_archive()
        self.assertEqual(len(value["include_headers_sha256"]), 1)
        header.write_text("`define WIDTH 64\n")
        with self.assertRaisesRegex(ValueError, "include modified"):
            verify_selected_archive(self.root, "example", self.definition)

    def test_rejects_filelist_identity_and_profile_mismatch(self):
        for mutation in ("filelist", "identity", "top", "duplicate"):
            with self.subTest(mutation=mutation):
                plan = copy.deepcopy(self.plan)
                if mutation == "filelist":
                    self.filelist.write_text(str(self.tb) + "\n" + str(self.soc) + "\n")
                if mutation == "identity":
                    plan["identity"]["selection"]["filelist_sha256"] = "0" * 64
                if mutation == "top":
                    plan["top"] = "bad_top"
                if mutation == "duplicate":
                    plan["sources"].append(str(self.soc))
                with self.assertRaises(ValueError):
                    archive_selected_filelist(self.root, "example", self.definition,
                                              plan, self.filelist)
                self.filelist.write_text(str(self.soc) + "\n" + str(self.tb) + "\n")

    def test_rejects_selected_source_and_archived_copy_mutations(self):
        value = self.make_archive()
        self.soc.write_text("module soc_top; wire changed; endmodule\n")
        with self.assertRaisesRegex(ValueError, "modified"):
            verify_selected_archive(self.root, "example", self.definition)
        self.soc.write_text("module soc_top; endmodule\n")
        archived = self.root / value["archive"] / "gen/chip/soc_top.sv"
        archived.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            verify_selected_archive(self.root, "example", self.definition)

    def test_tampered_plan_or_identity_fail_after_original_archive(self):
        self.make_archive()
        plan_file = self.out / "plan.json"
        plan = json.loads(plan_file.read_text())
        plan["defines"].append("FORGED=1")
        plan_file.write_text(json.dumps(plan) + "\n")
        with self.assertRaisesRegex(ValueError, "plan/identity"):
            verify_selected_archive(self.root, "example", self.definition)
        plan_file.write_text(json.dumps(self.plan) + "\n")
        identity_file = self.out / "identity.json"
        bogus = json.loads(identity_file.read_text())
        bogus["identity_sha256"] = "0" * 64
        identity_file.write_text(json.dumps(bogus) + "\n")
        with self.assertRaisesRegex(ValueError, "plan/identity"):
            verify_selected_archive(self.root, "example", self.definition)

    def test_rejects_foreign_definition_even_when_bytes_match(self):
        self.make_archive()
        wrong = {**self.definition, "logical_test": "foreign-test"}
        with self.assertRaisesRegex(ValueError, "foreign/stale"):
            verify_selected_archive(self.root, "example", wrong)

    def test_declared_explain_does_not_invent_compiled_sources(self):
        # Use the real checked-in test registry; no Bender or runtime required.
        from regress import load_config
        config = load_config(ROOT / "config/regression.yaml")
        detail = explain_target(ROOT, "chip-ethernet-ddr-pcie",
                                config["tests"]["chip-ethernet-ddr-pcie"], config)
        self.assertEqual(detail["selected_source_status"],
                         "declared_only_no_resolved_filelist")
        self.assertIn("variant/soc_top.sv",
                      detail["expected_soc_top_path_hint_not_verified"])
        self.assertNotIn("selected_inputs", detail)


if __name__ == "__main__":
    unittest.main()
