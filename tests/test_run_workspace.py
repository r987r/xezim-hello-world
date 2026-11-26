"""Canonical run workspace is exclusive, source-bound and not legacy alias."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tools.run_workspace import reserve_run, reserve_materialized_run, verify_run, canonical_artifact, require_completed_xezim_run, require_completed_cocotb_run, verify_artifact_inventory
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

    def test_ethernet_preflight_and_execution_are_distinct(self):
        from tools.run_workspace import selected_run_folder, uses_canonical_workspace

        self.assertTrue(uses_canonical_workspace('chip-ethernet', self.catalog['chip-ethernet']))
        self.assertFalse(uses_canonical_workspace(
            'chip-ethernet-ddr-pcie', self.catalog['chip-ethernet-ddr-pcie']))
        target = 'chip-ethernet-cpu'
        plan = self.catalog[target]
        checkout = Path(self.temp.name)

        def add_stage(stage, suffix):
            identity = selected(target, plan, run_id=f'local-{suffix:012x}')
            work = reserve_run(checkout / '.tools/runs', identity, plan=plan)
            (work / 'plan.json').write_text(json.dumps({'stage': stage, 'identity': identity}))
            return work

        preflight = add_stage('files', 1)
        self.assertIsNone(selected_run_folder(checkout, target, plan, stage='all'))
        executed = add_stage('all', 2)
        self.assertEqual(selected_run_folder(checkout, target, plan, stage='files'), preflight)
        self.assertEqual(selected_run_folder(checkout, target, plan, stage='all'), executed)
        with self.assertRaisesRegex(IdentityError, 'exactly one'):
            selected_run_folder(checkout, target, plan)
        add_stage('all', 3)
        with self.assertRaisesRegex(IdentityError, 'exactly one'):
            selected_run_folder(checkout, target, plan, stage='all')

    def test_combined_files_qualification_selects_only_new_attested_stage(self):
        from tools.run_workspace import selected_run_folder, snapshot_run_ids, uses_canonical_workspace

        target = 'chip-ethernet-ddr-pcie'
        plan = self.catalog[target]
        checkout = Path(self.temp.name)
        scope = {'stage': 'files', 'canonical_combined_files': True}
        legacy = checkout / '.tools/regression' / target
        self.assertFalse(uses_canonical_workspace(target, plan, stage='files'))
        self.assertEqual(selected_run_folder(checkout, target, plan, stage='files'), legacy)
        self.assertTrue(uses_canonical_workspace(target, plan, **scope))
        self.assertFalse(uses_canonical_workspace(target, {**plan, 'top': 'other'}, **scope))
        self.assertTrue(uses_canonical_workspace(target, plan, stage='run'))

        def allocate(stage, suffix):
            identity = selected(target, plan, run_id=f'local-{suffix:012x}')
            work = reserve_run(checkout / '.tools/runs', identity, plan=plan)
            (work / 'plan.json').write_text(json.dumps({'stage': stage, 'identity': identity}))
            return work

        old = allocate('files', 9)
        baseline = snapshot_run_ids(checkout, target, plan, **scope)
        self.assertEqual(baseline, {old.name})
        execution = allocate('run', 8)
        self.assertIsNone(selected_run_folder(checkout, target, plan,
                                               prior_run_ids=baseline, **scope))
        self.assertEqual(selected_run_folder(checkout, target, plan, stage='run'), execution)
        first = allocate('files', 1)
        self.assertEqual(selected_run_folder(checkout, target, plan,
                                             prior_run_ids=baseline, **scope), first)
        with self.assertRaisesRegex(IdentityError, 'exactly one'):
            selected_run_folder(checkout, target, plan, **scope)
        second_baseline = snapshot_run_ids(checkout, target, plan, **scope)
        second = allocate('files', 2)
        self.assertEqual(selected_run_folder(checkout, target, plan,
                                             prior_run_ids=second_baseline, **scope), second)
        with self.assertRaisesRegex(IdentityError, 'exactly one'):
            selected_run_folder(checkout, target, plan, prior_run_ids=baseline, **scope)
        legacy.mkdir(parents=True)
        with self.assertRaisesRegex(IdentityError, 'mirror forbidden'):
            snapshot_run_ids(checkout, target, plan, **scope)

    def test_combined_explicit_files_archive_does_not_select_another_run(self):
        from tools.combined_source_projection import SourceProjectionError, verified_files_archive

        checkout = Path(self.temp.name)
        profile = "chip-ethernet-ddr-pcie"
        definition = self.catalog[profile]
        def allocate(index, stage):
            identity = selected(profile, definition, run_id=f"local-{index:012x}")
            out = reserve_run(checkout / ".tools/runs", identity, plan=definition)
            (out / "plan.json").write_text(json.dumps({"stage": stage, "identity": identity}))
            return out

        first, second, runtime = allocate(1, "files"), allocate(2, "files"), allocate(3, "run")
        # The generic verifier already owns byte and manifest/staleness tests.
        # Here check only the additional explicit files-selection contract.
        with patch("tools.combined_source_projection.verify_selected_archive",
                   return_value={"source_count": 312}) as verify:
            self.assertEqual(verified_files_archive(checkout, first.relative_to(checkout), definition),
                             (first, {"source_count": 312}))
            verify.assert_called_once_with(checkout, profile, definition, directory=first)
            self.assertEqual(verified_files_archive(checkout, second, definition)[0], second)
            with self.assertRaisesRegex(SourceProjectionError, "files-only"):
                verified_files_archive(checkout, runtime, definition)
            with self.assertRaisesRegex(SourceProjectionError, "checkout-owned"):
                verified_files_archive(checkout, checkout.parent / "foreign", definition)
            (first / "ddr-split-build.json").write_text("{}")
            with self.assertRaisesRegex(SourceProjectionError, "files-only"):
                verified_files_archive(checkout, first, definition)
            (checkout / ".tools/regression").mkdir()
            (checkout / ".tools/regression" / profile).symlink_to(second, target_is_directory=True)
            with self.assertRaisesRegex(SourceProjectionError, "mirror forbidden"):
                verified_files_archive(checkout, second, definition)

    def test_replay_selects_only_one_new_invocation_never_latest(self):
        from tools.run_workspace import selected_run_folder, snapshot_run_ids

        checkout = Path(self.temp.name)
        target = "chip-cpu-scenario"
        def stage(run_id):
            identity = selected(target, self.plan, run_id=run_id)
            path = reserve_run(checkout / ".tools/runs", identity, plan=self.plan)
            (path / "plan.json").write_text(json.dumps({"identity": identity, "stage": "all"}))
            return path

        stage("local-999999999999")
        previous = snapshot_run_ids(checkout, target, self.plan)
        self.assertIsNone(selected_run_folder(checkout, target, self.plan, stage="all",
                                              prior_run_ids=previous))
        fresh = stage("local-000000000001")
        self.assertEqual(selected_run_folder(checkout, target, self.plan, stage="all",
                                             prior_run_ids=previous), fresh)
        stage("local-000000000002")
        with self.assertRaisesRegex(IdentityError, "exactly one"):
            selected_run_folder(checkout, target, self.plan, stage="all", prior_run_ids=previous)

    def test_dynamic_materialization_binds_final_compiler_filelist(self):
        import hashlib

        plan = self.catalog["boot-relocated"]
        initial = selected("boot-relocated", plan, run_id="local-012345abcdef")
        expected = self.root / relative_path(initial)

        def materialize(folder):
            self.assertEqual(folder, expected)
            self.assertFalse((folder / "identity.json").exists())
            (folder / "sources.f").write_bytes(b"selected/boot_config_pkg.sv\n")

        folder, final = reserve_materialized_run(self.root, initial, materialize, plan=plan)
        self.assertEqual(folder, expected)
        self.assertNotEqual(final["identity_sha256"], initial["identity_sha256"])
        self.assertEqual(final["selection"]["filelist_sha256"], hashlib.sha256(
            (folder / "sources.f").read_bytes()).hexdigest())
        self.assertEqual(verify_run(folder, final, plan=plan), folder)
        with self.assertRaisesRegex(IdentityError, "duplicate"):
            reserve_materialized_run(self.root, initial, materialize, plan=plan)
        with self.assertRaisesRegex(IdentityError, "unbound"):
            reserve_materialized_run(self.root, final, materialize, plan=plan)

    def test_failed_materialization_is_not_a_discoverable_run(self):
        from tools.run_workspace import selected_run_folder

        plan = self.catalog["boot-relocated"]
        initial = selected("boot-relocated", plan, run_id="local-012345abcdef")
        checkout = Path(self.temp.name)
        runs = checkout / ".tools/runs"

        def incomplete(folder):
            (folder / "prepare.log").write_text("preparation failed")

        with self.assertRaisesRegex(IdentityError, "filelist missing"):
            reserve_materialized_run(runs, initial, incomplete, plan=plan)
        self.assertTrue((runs / relative_path(initial) / "prepare.log").is_file())
        self.assertIsNone(selected_run_folder(checkout, "boot-relocated", plan))

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

    def test_negative_canonical_gate_requires_named_mismatch_without_pass(self):
        target = "memory-negative"
        plan = self.catalog[target]
        root = Path(self.temp.name) / ".tools/runs"
        identity = selected(target, plan, run_id="local-aaaaaaaaaaaa")
        directory = reserve_run(root, identity, plan=plan)
        (directory / "plan.json").write_text(json.dumps({"identity": identity}))
        for name in ("sources.f", "selected-rtl-manifest.json", "runner-events.json"):
            (directory / name).touch()
        result = {
            "target": target, "passed": True, "stage": "all",
            "identity_sha256": identity["identity_sha256"],
            "canonical_id": relative_path(identity).as_posix(),
            "results": [{"name": target, "passed": True, "exit_code": 1}],
        }
        (directory / "result.json").write_text(json.dumps(result))
        transcript = directory / f"{target}.log"
        transcript.write_text(plan["expect_failure"])
        with patch("tools.selected_rtl_provenance.verify_selected_archive"):
            self.assertEqual(require_completed_xezim_run(root, target, plan)["status"],
                             "runner_completed_xezim_expected_negative")
            transcript.write_text(plan["expect_failure"] + plan["pass"])
            with self.assertRaisesRegex(IdentityError, "named negative"):
                require_completed_xezim_run(root, target, plan)
            transcript.write_text(plan["expect_failure"])
            for bad in (0, -9, True):
                result["results"][0]["exit_code"] = bad
                (directory / "result.json").write_text(json.dumps(result))
                with self.assertRaisesRegex(IdentityError, "completed selected Xezim outcome"):
                    require_completed_xezim_run(root, target, plan)

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
        # Two otherwise valid identities remain ambiguous, even when
        # neither run has any completed simulator evidence.
        with self.assertRaisesRegex(IdentityError, "exactly one real canonical"):
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
