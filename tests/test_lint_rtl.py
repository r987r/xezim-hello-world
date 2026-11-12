"""slang lint inventory: no false green results, stable diagnostics and dynamic profiles."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import lint_rtl


class SlangLintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "config/regression.yaml").write_text(
            "schema_version: 1\ntests:\n"
            "  soc-e2e:\n    sources: noc\n    engine: cocotb-verilator\n    top: new_top\n"
            "  soc-e2e-negative:\n    sources: noc\n    engine: cocotb-verilator\n"
            "    top: new_top\n    reuse_build: true\n    expect_failure: bad\n"
            "  unknown-ip-test:\n    sources: noc\n    engine: cocotb-verilator\n    top: another_top\n"
            "  noc-elaborate:\n    sources: noc\n    engine: verilator-lint\n"
            "  optional-real-memory:\n    sources: noc\n    engine: cocotb-verilator\n"
            "    top: full_chip_tb\n    opt_in: true\n")
        self.folder = self.root / ".tools/regression/soc-e2e"
        self.folder.mkdir(parents=True)
        (self.folder / "sources.f").write_text("fake.sv\n")
        (self.folder / "plan.json").write_text(
            json.dumps({"target": "soc-e2e", "top": "new_top", "sources": ["fake.sv"]}))

    def test_discovers_new_unknown_subsystem_profiles(self):
        self.assertEqual(lint_rtl.select_profiles(self.root, []),
                         ["soc-e2e", "unknown-ip-test"])
        with self.assertRaisesRegex(ValueError, "unknown lint profiles"):
            lint_rtl.select_profiles(self.root, ["missing"])
        # Real DDR controller variant only exists after its pinned runtime
        # generation; ordinary source-filelist lint must stay source-true.
        self.assertNotIn("optional-real-memory", lint_rtl.select_profiles(self.root, []))
        self.assertEqual(lint_rtl.select_profiles(self.root, ["optional-real-memory"]),
                         ["optional-real-memory"])

    def test_project_owned_selected_sources_have_explicit_time_scale(self):
        # Source ownership only; pinned upstream warnings are a separate gate.
        owned = [
            "dv/dma/dma_tb.sv",
            "rtl/adapters/axi_sram_target.sv",
            "rtl/adapters/chip_types_pkg.sv",
            "rtl/adapters/cpu_noc_adapter.sv",
            "rtl/adapters/serv_axi_lite_adapter.sv",
            "rtl/adapters/soc_dma_regs.sv",
            "rtl/adapters/soc_idma_engine.sv",
            "rtl/io/ethernet0/ethernet0_axi_mvp.sv",
            "rtl/io/ethernet0/ethernet_queue_axi_regs.sv",
            "rtl/io/ethernet0/ethernet_queue_ctrl.sv",
            "gen/chip/soc_top.sv", "gen/chip/full_chip_dma_tb.sv",
            "gen/supernoc/soc_noc.sv", "gen/supernoc/supernoc_tb.sv",
        ]
        networks = json.loads((ROOT/"gen/noc/floonoc/manifest.json").read_text())["networks"]
        self.assertEqual(len(networks), 12)
        for record in networks.values():
            owned += ["gen/noc/floonoc/"+record[key] for key in ("top", "package")]
        self.assertEqual(len(owned), 38)
        for path in owned:
            with self.subTest(path=path):
                self.assertTrue((ROOT/path).read_text().startswith("`timescale 1ns/1ps\n"),
                                f"owned selected RTL time scale missing: {path}")

    def test_source_location_and_severity(self):
        raw = self.root / "diagnostics.json"
        raw.write_text(json.dumps([
            {"severity": "error", "code": "InvalidPort", "location": str(self.root / "rtl/net.sv") + ":16:7",
             "message": "bad width", "symbolPath": "soc_top.noc0"},
            {"severity": "warning", "code": "Unused", "message": "unused signal"},
        ]))
        found = lint_rtl.parse_diagnostics(raw, self.root, "soc-e2e", "lint")
        self.assertEqual(found[0]["file"], "rtl/net.sv")
        self.assertEqual(found[0]["line"], 16)
        self.assertEqual(found[0]["column"], 7)
        self.assertEqual(found[0]["symbol_path"], "soc_top.noc0")
        self.assertEqual(found[1]["severity"], "warning")

    def test_writes_full_report_even_with_design_errors(self):
        def fake(command, **kwargs):
            loc = Path(command[command.index("--diag-json") + 1])
            if "--lint-only" in command:
                loc.write_text(json.dumps([{"severity": "error", "code": "Example",
                                            "message": "test design error"}]))
                return subprocess.CompletedProcess(command, 1, "", "design error")
            loc.write_text("[]")
            return subprocess.CompletedProcess(command, 0, "", "")
        report = lint_rtl.analyze(self.root, "soc-e2e", "new_top", "/bin/slang",
                                  self.root / "results", execute=fake)
        self.assertEqual(report["summary"]["error"], 1)
        self.assertEqual(report["policy"], "report_only")
        self.assertEqual(len(report["modes"]), 2)
        self.assertTrue((self.root / "results/report.json").exists())

    def test_fails_closed_tool_crash_or_bad_json(self):
        def crash(command, **kwargs):
            return subprocess.CompletedProcess(command, 139, "", "segfault")
        with self.assertRaisesRegex(ValueError, "without design diagnostics"):
            lint_rtl.analyze(self.root, "soc-e2e", "new_top", "/bin/slang",
                             self.root / "crash", execute=crash)
        def bad(command, **kwargs):
            path = Path(command[command.index("--diag-json") + 1])
            path.write_text("bad-json")
            return subprocess.CompletedProcess(command, 0, "", "")
        with self.assertRaisesRegex(ValueError, "invalid diagnostics JSON"):
            lint_rtl.analyze(self.root, "soc-e2e", "new_top", "/bin/slang",
                             self.root / "bad", execute=bad)

    def test_deduplicates_cross_profile_and_mode_without_hiding_errors(self):
        row = {"severity": "warning", "code": "MissingTimeScale",
               "file": "rtl/top.sv", "line": 31, "column": 2,
               "symbol_path": "soc_top", "message": "timescale absent",
               "origin": "project", "mode": "lint"}
        second = dict(row, mode="elaborate", severity="error")
        vendor = dict(row, code="UnconnectedInputPort",
                      file=".tools/floonoc/src/fifo.sv", line=9,
                      origin="vendor", message="unconnected source input")
        reports = [
            {"profile":"chip-a","filelist_sha256":"a"*64,
             "findings":[row,second,vendor]},
            {"profile":"chip-b","filelist_sha256":"b"*64,
             "findings":[dict(row, profile="chip-b"),dict(vendor,mode="elaborate")]}
        ]
        original = json.dumps(reports, sort_keys=True)
        dedup = lint_rtl.deduplicate_reports(reports)
        self.assertEqual(json.dumps(reports, sort_keys=True), original)
        self.assertEqual(dedup["original_occurrences"], 5)
        self.assertEqual(dedup["unique_diagnostics"], 2)
        self.assertEqual(dedup["deduplicated_occurrences"], 3)
        self.assertEqual(dedup["unique_severity_counts"], {"error":1,"warning":1})
        self.assertEqual(dedup["unique_origin_counts"], {"project":1,"vendor":1})
        self.assertEqual(dedup["filelist_sha256_by_profile"],
                         {"chip-a":"a"*64,"chip-b":"b"*64})
        top = next(f for f in dedup["findings"] if f["code"]=="MissingTimeScale")
        self.assertEqual(top["occurrences"],3)
        self.assertEqual(top["severities"],["error","warning"])
        self.assertEqual(top["modes"],["elaborate","lint"])
        self.assertEqual(top["profiles"],["chip-a","chip-b"])
        self.assertEqual(top["messages"],["timescale absent"])
        self.assertEqual(dedup, lint_rtl.deduplicate_reports(reports))

    def test_missing_codes_and_paths_do_not_collapse_different_messages(self):
        base = {"severity":"error","code":"","file":"","line":None,
                "column":None,"symbol_path":"","origin":"project",
                "mode":"lint","message":"first failure"}
        report = {"profile":"chip-a","filelist_sha256":"c"*64,
                  "findings":[base,dict(base,message="second failure")]}
        dedup = lint_rtl.deduplicate_reports([report])
        self.assertEqual(dedup["unique_diagnostics"],2)
        self.assertEqual(dedup["unique_severity_counts"]["error"],2)

    def test_migrated_dma_lint_reads_only_exact_canonical_identity_and_source_archive(self):
        from test_identity import selected, save, relative_path
        definition = {
            "engine": "cocotb-verilator", "sources": "noc",
            "bender_targets": ["dma"], "top": "dma_tb",
            "module": "dv.dma.test_dma",
            "logical_test": "dma-descriptor-chain",
        }
        cfg = self.root / "config/regression.yaml"
        import yaml
        cfg.write_text(yaml.safe_dump({"schema_version": 1, "tests": {
            "dma-rtl": definition}}, sort_keys=True))
        filelist_bytes = b"+incdir+/pinned/noc\\n/pinned/dma_tb.sv\\n"
        identity = selected("dma-rtl", definition, filelist_bytes=filelist_bytes,
                            run_id="local-a1b2c3d4e5f6")
        directory = self.root / ".tools/runs" / relative_path(identity)
        directory.mkdir(parents=True)
        save(directory / "identity.json", identity)
        (directory / "sources.f").write_bytes(filelist_bytes)
        (directory / "plan.json").write_text(json.dumps({
            **definition, "target": "dma-rtl", "source_target": "noc",
            "sources": ["/pinned/dma_tb.sv"], "identity": identity}))
        with patch("selected_rtl_provenance.verify_selected_archive",
                   return_value={"status": "source_selected_only"}) as verifier:
            self.assertEqual(lint_rtl.verify_plan(self.root, "dma-rtl", "dma_tb"),
                             directory / "sources.f")
            verifier.assert_called_once_with(
                self.root.resolve(), "dma-rtl", definition, directory=directory)
            # Conflicting old target aliases cannot override the new writer.
            old = self.root / ".tools/regression/dma-rtl"
            old.mkdir(parents=True)
            (old / "sources.f").write_bytes(filelist_bytes)
            with self.assertRaisesRegex(ValueError, "legacy dma-rtl"):
                lint_rtl.verify_plan(self.root, "dma-rtl", "dma_tb")
            import shutil
            shutil.rmtree(old)
            (directory / "sources.f").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "filelist SHA mismatch"):
                lint_rtl.verify_plan(self.root, "dma-rtl", "dma_tb")
            (directory / "sources.f").write_bytes(filelist_bytes)
            second = directory.parent / "local-111111111111"
            second.mkdir()
            save(second / "identity.json", selected(
                "dma-rtl", definition, filelist_bytes=filelist_bytes,
                run_id="local-111111111111"))
            with self.assertRaisesRegex(ValueError, "exactly one"):
                lint_rtl.verify_plan(self.root, "dma-rtl", "dma_tb")

    def test_rejects_wrong_plan(self):
        (self.folder / "plan.json").write_text(
            json.dumps({"target": "other", "top": "new_top", "sources": ["fake.sv"]}))
        with self.assertRaisesRegex(ValueError, "does not match"):
            lint_rtl.verify_plan(self.root, "soc-e2e", "new_top")


if __name__ == "__main__":
    unittest.main()
