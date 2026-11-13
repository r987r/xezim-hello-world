"""Canonical run workspace is exclusive, source-bound and not legacy alias."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tools.run_workspace import reserve_run, verify_run, canonical_artifact, require_completed_xezim_run, require_completed_cocotb_run, verify_artifact_inventory
from tools.test_identity import IdentityError, selected, relative_path

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = yaml.safe_load((ROOT / "config/regression.yaml").read_text())["tests"]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "runs"
        self.plan = self.catalog["chip-cpu-scenario"]
        self.identity = selected("chip-cpu-scenario", self.plan,
                                 run_id="local-012345abcdef")

    def test_selected_four_part_identity_is_only_canonical_workspace(self):
        folder = reserve_run(self.root, self.identity, plan=self.plan)
        self.assertEqual(folder.relative_to(self.root), relative_path(self.identity))
        self.assertEqual(folder.parts[-4:], (
            "verilator", "soc-cpu-dma-scenario",
            "dma-sram-ddr-roundtrip", "local-012345abcdef"))
        self.assertEqual(verify_run(folder, self.identity, plan=self.plan), folder)
        destination = canonical_artifact(folder, "artifacts/axi-transactions.json")
        self.assertEqual(destination.parent.name, "artifacts")
        destination.write_text('{"kind":"unmeasured"}')
        with self.assertRaisesRegex(IdentityError, "overwrite"):
            canonical_artifact(folder, "artifacts/axi-transactions.json")
        self.assertFalse((self.root / "chip-cpu-scenario").exists())

    def test_duplicate_writer_and_tampered_identity_fail_closed(self):
        folder = reserve_run(self.root, self.identity)
        with self.assertRaisesRegex(IdentityError, "duplicate"):
            reserve_run(self.root, self.identity)
        original = json.loads((folder / "identity.json").read_text())
        original["run_id"] = "local-000000000001"
        (folder / "identity.json").write_text(json.dumps(original))
        with self.assertRaises(IdentityError):
            verify_run(folder, self.identity)

    def test_foreign_identity_wrong_plan_or_wrong_path_rejected(self):
        folder = reserve_run(self.root, self.identity)
        other = selected("chip-cpu-scenario", self.plan,
                         run_id="local-111111111111")
        with self.assertRaises(IdentityError):
            verify_run(folder, other)
        with self.assertRaises(IdentityError):
            verify_run(folder, self.identity,
                       plan=self.catalog["chip-dma-scenario"])
        altered = copy.deepcopy(self.identity)
        altered["identity_sha256"] = "0" * 64
        with self.assertRaises(IdentityError):
            reserve_run(self.root, altered)

    def test_existing_run_artifact_integrity_is_recorded_not_claimed_pass(self):
        directory = reserve_run(self.root, self.identity, plan=self.plan)
        artifact = canonical_artifact(directory, "logs/simulation.log")
        artifact.write_bytes(b"real simulator transcript")
        proof = verify_artifact_inventory(
            directory, self.identity, ["logs/simulation.log"], plan=self.plan)
        self.assertEqual(proof["status"],
                         "artifact_bytes_verified_not_execution_proof")
        self.assertEqual(proof["artifacts"][0]["bytes"], 25)
        self.assertEqual(len(proof["artifacts"][0]["sha256"]), 64)
        for names in ([], ["logs/simulation.log", "logs/simulation.log"],
                      ["missing.json"], ["../outside"], ["a\\\\b"]):
            with self.subTest(names=names), self.assertRaises(IdentityError):
                verify_artifact_inventory(directory, self.identity, names)
        artifact.unlink()
        with self.assertRaisesRegex(IdentityError, "missing canonical"):
            verify_artifact_inventory(
                directory, self.identity, ["logs/simulation.log"])

    def test_real_producer_gate_refuses_unexecuted_or_missing_result(self):
        plan = self.catalog["smoke"]
        identity = selected("smoke", plan, run_id="local-aaaaaaaaaaaa")
        root = Path(self.temp.name) / ".tools/runs"
        directory = reserve_run(root, identity, plan=plan)
        with self.assertRaisesRegex(IdentityError, "missing canonical"):
            require_completed_xezim_run(root, "smoke", plan)
        # Even a fabricated bare result without original source/runner logs
        # is not a qualified real simulator regression.
        (directory / "result.json").write_text(
            json.dumps({"target": "smoke", "passed": True}) + "\n")
        with self.assertRaisesRegex(IdentityError, "missing canonical"):
            require_completed_xezim_run(root, "smoke", plan)

    def test_canonical_serv_cpu_requires_selected_real_execution(self):
        plan = self.catalog["serv"]
        root = Path(self.temp.name) / ".tools/runs"
        identity = selected("serv", plan, run_id="local-aaaaaaaaaaaa")
        directory = reserve_run(root, identity, plan=plan)
        self.assertEqual(directory.relative_to(root), relative_path(identity))
        self.assertFalse((root.parent / "regression/serv").exists())
        with self.assertRaisesRegex(IdentityError, "missing canonical"):
            require_completed_xezim_run(root, "serv", plan)
        (directory / "result.json").write_text(json.dumps({
            "target": "serv", "passed": True, "stage": "all",
            "identity_sha256": identity["identity_sha256"],
            "canonical_id": relative_path(identity).as_posix(),
            "results": [{"name": "serv", "passed": True, "exit_code": 0}]
        }) + "\n")
        # A bare claimed PASS cannot replace actual source archive, log,
        # runner evidence or source selected artifact hashes.
        with self.assertRaisesRegex(IdentityError, "missing canonical"):
            require_completed_xezim_run(root, "serv", plan)
        invalid = dict(plan, top="wrong_cpu_tb")
        with self.assertRaisesRegex(IdentityError, "unexpected canonical"):
            require_completed_xezim_run(root, "serv", invalid)
        invalid = dict(plan, mode="compile")
        with self.assertRaisesRegex(IdentityError, "unexpected canonical"):
            require_completed_xezim_run(root, "serv", invalid)
        other = selected("serv", plan, run_id="local-bbbbbbbbbbbb")
        reserve_run(root, other, plan=plan)
        with self.assertRaisesRegex(IdentityError, "missing canonical"):
            require_completed_xezim_run(root, "serv", plan)

    def test_real_verilator_cocotb_producer_refuses_fabricated_completion(self):
        """A canonical name alone cannot make XML/runner/source evidence PASS."""
        plan = self.catalog["dma-rtl"]
        identity = selected("dma-rtl", plan, run_id="local-555555555555")
        root = Path(self.temp.name) / ".tools/runs"
        folder = reserve_run(root, identity, plan=plan)
        with self.assertRaisesRegex(IdentityError, "missing canonical"):
            require_completed_cocotb_run(root, "dma-rtl", plan)
        for name, data in {
            "plan.json": json.dumps({
                "target": "dma-rtl", "top": "dma_tb",
                "identity": identity}),
            "sources.f": "real DMA sources selected\\n",
            "selected-rtl-manifest.json": "{}\\n",
            "result.json": json.dumps({
                "target": "dma-rtl", "passed": True, "stage": "all",
                "identity_sha256": identity["identity_sha256"],
                "canonical_id": relative_path(identity).as_posix(),
                "results": [{"name": "dma-rtl", "passed": True, "exit_code": 0}]}),
            "runner-events.json": json.dumps({
                "events": [{"status": "completed", "passed": True}]}),
            "dma-rtl.log": "real Cocotb runner transcript\\n",
            "simulation.log": "PASS dma-rtl: descriptor real IRQ\\n",
            "results.xml": '<testsuite><testcase name="pulp_idma"/></testsuite>',
        }.items():
            (folder / name).write_text(data.replace("\\n", "\n"))
        # Only the source-archive *unit fixture* is mocked. Production
        # verification uses the original selected RTL manifest/hash checker.
        with patch("tools.selected_rtl_provenance.verify_selected_archive"):
            proof = require_completed_cocotb_run(root, "dma-rtl", plan)
            self.assertEqual(proof["canonical_id"],
                             relative_path(identity).as_posix())
            self.assertNotIn("protocol_qualified", proof["status"])
            for broken in ('<testsuite><testcase><failure/></testcase></testsuite>',
                           '<testsuite><testcase><error/></testcase></testsuite>',
                           '<testsuite><testcase><skipped/></testcase></testsuite>',
                           '<testsuite/>', '<not-xml'):
                (folder / "results.xml").write_text(broken)
                with self.subTest(xml=broken), self.assertRaises(IdentityError):
                    require_completed_cocotb_run(root, "dma-rtl", plan)
            (folder / "results.xml").write_text(
                '<testsuite><testcase name="pulp_idma"/></testsuite>')
            (folder / "simulation.log").write_text("fake simulator transcript")
            with self.assertRaisesRegex(IdentityError, "original simulator"):
                require_completed_cocotb_run(root, "dma-rtl", plan)
            (folder / "simulation.log").write_text("PASS dma-rtl: restored")
            bad = json.loads((folder / "result.json").read_text())
            bad["identity_sha256"] = "0" * 64
            (folder / "result.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(IdentityError, "original completed PASS"):
                require_completed_cocotb_run(root, "dma-rtl", plan)
            with self.assertRaisesRegex(IdentityError, "unreviewed"):
                require_completed_cocotb_run(root, "chip-cpu-dma", plan)
            # A second writer with the same logical target cannot silently
            # replace the first run; matching target across 2 run IDs is
            # treated as ambiguous at the CI ingestion boundary.
            other = selected("dma-rtl", plan, run_id="local-666666666666")
            reserve_run(root, other, plan=plan)
            with self.assertRaisesRegex(IdentityError, "exactly one"):
                require_completed_cocotb_run(root, "dma-rtl", plan)

    def test_symlink_and_escape_rejected(self):
        outer = Path(self.temp.name)
        fake = outer / "alias"
        fake.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(IdentityError, "symlink"):
            reserve_run(fake, self.identity)
        folder = reserve_run(self.root, self.identity)
        for path in ("../escape.json", "/tmp/foreign", "sub/../escape",
                     "a\\b"):
            with self.subTest(path=path), self.assertRaises(IdentityError):
                canonical_artifact(folder, path)
        shortcut = folder / "shortcut"
        shortcut.symlink_to(outer, target_is_directory=True)
        with self.assertRaisesRegex(IdentityError, "symlink"):
            canonical_artifact(folder, "shortcut/outside.json")


if __name__ == "__main__":
    unittest.main()
