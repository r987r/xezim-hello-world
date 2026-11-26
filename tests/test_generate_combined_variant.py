"""Real combined source publisher: no snapshot-only acceptance or fake RTL PASS."""
import hashlib
import json
import shutil
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
        # Fixture models the actual source-list size and absolute Bender
        # checkout paths, without requiring any upstream IP checkout.
        for name in other:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("module stub; endmodule\n")
        filelist = ("+incdir+" + str(self.root / "config") + "\n"
                    "+define+TARGET_RTL\n" +
                    "".join(str(self.root / name) + "\n"
                            for name in [*hashes, *other]))
        (self.root / publisher.SOURCE_ROOT / "sources.f").write_text(filelist)
        self.manifest = {
            "source_count": 312, "source_sha256": {**hashes, **other},
            "generated_sha256": generated,
            "compiler_input_sha256": "1"*64,
            "filelist_sha256": hashlib.sha256(filelist.encode()).hexdigest(),
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
        portable = (folder / "compiler/sources.f").read_text()
        self.assertNotIn(str(self.root), portable)
        self.assertIn("+incdir+config", portable)
        self.assertIn("gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/rtl/soc_top.sv",
                      portable)
        self.assertIn("gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie/controller/gateware/soc_ddr4_sim.v",
                      portable)
        self.assertEqual(len([line for line in portable.splitlines()
                              if not line.startswith("+")]), 312)

    def test_files_only_projection_preserves_portable_bytes_without_legacy_writer(self):
        from combined_source_projection import (BRIDGE, LEGACY_BRIDGE, SourceProjectionError,
                                                project)
        from selected_rtl_provenance import _canonical_sha

        root = self.root
        legacy = root / publisher.SOURCE_ROOT
        directory = root / ".tools/runs/verilator/soc-ethernet-ddr-pcie/multiprotocol-closure/local-000000000001"
        prefix = directory.relative_to(root).as_posix() + "/"
        old_list = legacy / "sources.f"
        replaced_source = "rtl/third_party_000.sv"
        bridge_bytes = (root / replaced_source).read_bytes()
        bridge = root / LEGACY_BRIDGE
        bridge.parent.mkdir(parents=True)
        bridge.write_bytes(bridge_bytes)
        old_raw = old_list.read_bytes().replace(replaced_source.encode(), LEGACY_BRIDGE.encode())
        old_list.write_bytes(old_raw)
        self.manifest["filelist_sha256"] = hashlib.sha256(old_raw).hexdigest()
        sources = self.manifest["source_sha256"]
        sources.pop(replaced_source)
        sources[LEGACY_BRIDGE] = hashlib.sha256(bridge_bytes).hexdigest()
        self.manifest["config_sha256"] = _canonical_sha(
            {"filelist_sha256": self.manifest["filelist_sha256"]})
        self.manifest.update(include_headers_sha256={}, network_filelists={})
        legacy_output = self.generate()

        def relocate(name):
            if name == LEGACY_BRIDGE:
                return prefix + BRIDGE
            return name.replace(publisher.SOURCE_ROOT, prefix)

        def sha(raw):
            return hashlib.sha256(raw).hexdigest()

        generated = {}
        for name in self.manifest["generated_sha256"]:
            raw = (root / name).read_bytes().replace(publisher.SOURCE_ROOT.encode(), prefix.encode())
            actual = root / relocate(name)
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(raw)
            generated[relocate(name)] = sha(raw)
        actual_bridge = root / relocate(LEGACY_BRIDGE)
        actual_bridge.parent.mkdir(parents=True, exist_ok=True)
        actual_bridge.write_bytes(bridge_bytes)
        generated[relocate(LEGACY_BRIDGE)] = sha(bridge_bytes)
        raw = old_raw.replace(publisher.SOURCE_ROOT.encode(), prefix.encode()).replace(
            LEGACY_BRIDGE.encode(), (prefix + BRIDGE).encode())
        (directory / "sources.f").write_bytes(raw)
        identity = {"selection": {"filelist_sha256": sha(raw)}, "identity_sha256": "a" * 64}
        identity["config_sha256"] = _canonical_sha(identity["selection"])
        entries = raw.decode().splitlines()
        plan = {"identity": identity, "engine": "cocotb-verilator", "top": "full_chip_tb",
                "source_target": "noc", "firmware_mode": "ethernet_ddr_pcie", "args": [],
                "includes": [entries[0].removeprefix("+incdir+")],
                "defines": [entries[1].removeprefix("+define+")], "sources": entries[2:]}
        actual = {**self.manifest, "schema_version": 1, "profile": publisher.PROFILE,
                  "compiled_top": plan["top"], "network_filelists": {}, "include_headers_sha256": {},
                  "definition_sha256": None, "defines": None, "includes": None, "args": None,
                  "selected_soc_top": prefix + "variant/soc_top.sv",
                  "generated_sha256": generated, "filelist_sha256": sha(raw),
                  "identity_sha256": identity["identity_sha256"], "config_sha256": identity["config_sha256"],
                  "source_sha256": {relocate(key): generated.get(relocate(key), value)
                                    for key, value in sources.items()}}

        shutil.rmtree(legacy)
        bridge.unlink()
        projected = project(root, directory, actual, plan,
                            read=lambda name, digest: publisher.source_bytes(root, name, digest))
        self.assertEqual(projected.reference_filelist, old_raw)
        self.assertNotEqual(projected.reference["filelist_sha256"], actual["filelist_sha256"])
        with patch("combined_source_projection.prepared_workspace", return_value=directory), \
                patch("combined_source_projection.verified_inputs", return_value=projected):
            result = publisher.emit(root, root / "candidate", runner=self.runner,
                                    canonical_combined_files=True)
        self.assertEqual(legacy_output, result)
        self.assertEqual(publisher.tree(root / "published"), publisher.tree(root / "candidate"))
        self.assertFalse(legacy.exists())
        foreign = {**actual, "source_sha256": {**actual["source_sha256"],
                   ".tools/runs/another-run/foreign.sv": "f" * 64}}
        with self.assertRaisesRegex(SourceProjectionError, "foreign run"):
            project(root, directory, foreign, plan,
                    read=lambda name, digest: publisher.source_bytes(root, name, digest))

    def test_portable_compiler_identity_is_stable_across_checkout_paths(self):
        first = self.generate()
        with tempfile.TemporaryDirectory() as other:
            relocated = Path(other) / "different-checkout"
            shutil.copytree(self.root, relocated)
            source_list = relocated / publisher.SOURCE_ROOT / "sources.f"
            rewritten = source_list.read_text().replace(
                str(self.root), str(relocated))
            source_list.write_text(rewritten)
            other_manifest = {**self.manifest,
                              "filelist_sha256": hashlib.sha256(
                                  rewritten.encode()).hexdigest(),
                              "compiler_input_sha256": "9"*64}
            with patch.object(publisher, "verify_selected_archive",
                              return_value=other_manifest):
                second = publisher.emit(relocated, relocated / "portable",
                                        runner=self.runner)
            self.assertEqual(first, second)
            self.assertEqual((self.root/"published/manifest.json").read_bytes(),
                             (relocated/"portable/manifest.json").read_bytes())
            self.assertEqual((self.root/"published/compiler/sources.f").read_bytes(),
                             (relocated/"portable/compiler/sources.f").read_bytes())
            self.assertNotIn(str(self.root),
                             (self.root/"published/manifest.json").read_text())
            self.assertEqual(len(second["portable_compiler_input_sha256"]), 64)

    def test_default_atomic_generator_preserves_verified_named_variant(self):
        import generate
        selected = self.root / "gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie"
        self.generate()
        selected.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.root / "published", selected)
        actual_gen = self.root / "gen"
        (actual_gen / generate.STAMP).write_text("socgen-v2\n")
        (actual_gen / "default.sv").write_text("module default_top; endmodule\n")
        readme = self.root / "README.md"
        readme.write_text("existing README fixture\n")

        def original_default_build(cfg, out, readme_path):
            (out / generate.STAMP).write_text("socgen-v2\n")
            (out / "default.sv").write_text("module default_top; endmodule\n")
            return readme_path.read_text()

        with patch.object(generate, "build", side_effect=original_default_build):
            self.assertEqual(
                generate.execute(self.root / "config/soc.yaml", actual_gen,
                                 readme, check=True), 0)
            self.assertEqual(
                generate.execute(self.root / "config/soc.yaml", actual_gen,
                                 readme, check=False), 0)
            self.assertTrue((selected / "rtl/soc_top.sv").is_file())
            (selected / "rtl/soc_top.sv").write_bytes(b"tampered real RTL\n")
            with self.assertRaisesRegex(generate.GenerationError, "integrity"):
                generate.execute(self.root / "config/soc.yaml", actual_gen,
                                 readme, check=True)

    def test_owned_selected_tree_detects_missing_and_stale_sources(self):
        self.generate()
        selected = self.root / "published"
        publisher.verify_published_tree(selected, self.root / "config/soc.yaml")
        (selected / "rtl/flash.hex").unlink()
        with self.assertRaisesRegex(publisher.CombinedGenerationError, "missing"):
            publisher.verify_published_tree(selected, self.root / "config/soc.yaml")

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

    def test_missing_source_or_changed_original_filelist_is_rejected(self):
        list_path = self.root / publisher.SOURCE_ROOT / "sources.f"
        list_path.write_text(list_path.read_text() + "+define+SURPRISE\n")
        with patch.object(publisher, "verify_selected_archive",
                          return_value=self.manifest):
            with self.assertRaisesRegex(publisher.CombinedGenerationError, "filelist digest"):
                publisher.emit(self.root, self.root / "published", runner=self.runner)
        list_path.write_text(list_path.read_text().removesuffix("+define+SURPRISE\n"))
        missing = self.root / publisher.DDR_ROOT / "soc_ddr4_sim.v"
        missing.unlink()
        with patch.object(publisher, "verify_selected_archive",
                          return_value=self.manifest):
            with self.assertRaisesRegex(publisher.CombinedGenerationError, "missing"):
                publisher.emit(self.root, self.root / "published", runner=self.runner)

    def test_wrong_selected_compiler_count_fails_closed(self):
        self.manifest["source_count"] = 311
        with patch.object(publisher, "verify_selected_archive",
                          return_value=self.manifest):
            with self.assertRaisesRegex(publisher.CombinedGenerationError, "count"):
                publisher.emit(self.root, self.root / "published", runner=self.runner)


if __name__ == "__main__":
    unittest.main()
