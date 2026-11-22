"""No simulator fixtures can be published as DDR execution evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml

from tools import ddr_split_workspace as ddr
from tools.run_workspace import reserve_run, uses_canonical_workspace
from tools.test_identity import IdentityError, SOURCE_LOCKS, selected, sha, validate

ROOT = Path(__file__).resolve().parents[1]


class DDRSplitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.catalog = yaml.safe_load((ROOT / 'config/regression.yaml').read_text())['tests']
        self.test = self.catalog[ddr.TARGET]
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('GITHUB_RUN_ID', None)
        os.environ.pop('GITHUB_RUN_ATTEMPT', None)
        for name in {'config/soc.yaml', *SOURCE_LOCKS, *ddr.PINNED_INPUTS}:
            self.write(self.root / name, name.encode())
        self.archives = Mock()
        self.fingerprint = Mock(return_value='a' * 64)

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    @staticmethod
    def command(path):
        return [[ddr.TARGET, ['python', 'sim_cocotb.py', str(path)]]]

    def prepare(self, run_id='local-012345abcdef', *, finalize=True):
        raw_filelist = b'/actual/selected/ddr.v\n'
        identity = selected(ddr.TARGET, self.test, root=self.root,
                            run_id=run_id, filelist_bytes=raw_filelist)
        out = reserve_run(self.root / '.tools/runs', identity)
        plan = {**self.test, 'target': ddr.TARGET, 'identity': identity, 'stage': 'run',
                'build': str(Path(self.test['build']) / run_id),
                'commands': self.command(out / 'plan.json'),
                'report': ddr.plan_report(self.root, out, self.test['report']),
                'results_xml': str(out / 'results.xml')}
        for name in (*ddr.DDR_INPUTS, *ddr.BUILD_RECORDS, 'selected-rtl-manifest.json'):
            self.write(out / name, name.encode())
        self.write(out / 'sources.f', raw_filelist)
        self.write(out / 'plan.json', json.dumps(plan).encode())
        build = self.root / plan['build']
        binary = build / plan['top']
        self.write(binary, ('EXE:' + run_id).encode())
        binary.chmod(0o700)
        self.write(build / 'regression-build.json', json.dumps({
            'binary_sha256': sha(binary.read_bytes()),
            'signature': 'a' * 64,
        }).encode())
        prepared = ddr.input_snapshot(self.root, out, plan)
        if finalize:
            ddr.seal(self.root, out, plan, prepared)
        return out, identity, plan, prepared

    def continuation(self, run_id):
        return ddr.prepare_continuation(
            self.root, self.test, run_id, verify_archive=self.archives,
            command=self.command, fingerprint=self.fingerprint)

    def test_only_standalone_source_target_migrates(self):
        self.assertTrue(uses_canonical_workspace(ddr.TARGET, self.test))
        self.assertFalse(uses_canonical_workspace('chip-ethernet-ddr-pcie',
                         self.catalog['chip-ethernet-ddr-pcie']))
        self.assertFalse(uses_canonical_workspace(ddr.TARGET, {**self.test, 'reuse_build': True}))

    def test_exact_invocation_with_two_builds_and_no_compile_only_pass(self):
        selected_out, ident, plan, _ = self.prepare()
        other_out, _, _, _ = self.prepare('local-012345abcd00')
        self.assertTrue((selected_out / ddr.SEAL).is_file())
        self.assertFalse((selected_out / 'result.json').exists())
        self.assertFalse((selected_out / 'simulation.log').exists())
        loc, found, read_plan = self.continuation(ident['run_id'])
        self.assertEqual((loc, found, read_plan), (selected_out, ident, plan))
        self.assertEqual((selected_out / ddr.CLAIM).read_bytes(), b'ddr-build-continuation-v1\n')
        self.assertFalse((other_out / ddr.CLAIM).exists())
        self.assertFalse((selected_out / 'result.json').exists())
        self.archives.assert_called_once_with(self.root, ddr.TARGET, self.test, directory=selected_out)
        self.fingerprint.assert_called_once_with(plan)
        with self.assertRaisesRegex(IdentityError,'already started'):
            self.continuation(ident['run_id'])

    def test_absent_seal_or_invalid_reader_never_dispatches(self):
        for value in ['', '..', 'local-0f2345abcdef', '../local-012345abcdef']:
            with self.subTest(run_id=value), self.assertRaises(IdentityError):
                self.continuation(value)
        out, ident, _, _ = self.prepare(finalize=False)
        with self.assertRaisesRegex(IdentityError,'missing or unsafe.*ddr-split-build'):
            self.continuation(ident['run_id'])
        self.assertFalse((out / ddr.CLAIM).exists())
        self.assertFalse((out / 'result.json').exists())
        self.archives.assert_not_called()

    def test_unsafe_inputs_and_preexisting_run_evidence_rejected(self):
        out, ident, _, _ = self.prepare()
        report = out / 'simulation.log'
        report.symlink_to(out / 'sources.f')
        with self.assertRaisesRegex(IdentityError,'contains run evidence'):
            self.continuation(ident['run_id'])
        report.unlink()
        f = out / ddr.DDR_INPUTS[0]
        replacement = f.with_suffix('.other')
        f.rename(replacement)
        f.symlink_to(replacement)
        with self.assertRaisesRegex(IdentityError,'missing or unsafe'):
            self.continuation(ident['run_id'])
        self.assertFalse((out / ddr.CLAIM).exists())

    def test_mutation_of_each_bound_input_blocks_before_claim(self):
        out, ident, plan, _ = self.prepare()
        build = self.root / plan['build']
        paths = [out/'sources.f', out/'selected-rtl-manifest.json', out/'plan.json',
                 *(out/p for p in (*ddr.DDR_INPUTS, *ddr.BUILD_RECORDS)),
                 *(self.root/p for p in ddr.PINNED_INPUTS),
                 build/'regression-build.json', build/plan['top'],
                 self.root/'config/soc.yaml', self.root / SOURCE_LOCKS[0]]
        for path in paths:
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                path.write_bytes(raw + b'\n')
                try:
                    with self.assertRaises(ValueError):
                        self.continuation(ident['run_id'])
                finally:
                    path.write_bytes(raw)
                self.assertFalse((out/ddr.CLAIM).exists())
        self.archives.assert_not_called()
        self.fingerprint.assert_not_called()

    def test_disallows_changed_input_during_build(self):
        out, _, plan, prepared = self.prepare(finalize=False)
        (out / 'ddr4-result.json').write_text('irrelevant runtime output must not become input')
        (out / ddr.DDR_INPUTS[1]).write_text('changed after selecting actual firmware')
        with self.assertRaisesRegex(IdentityError,'changed during build'):
            ddr.seal(self.root, out, plan, prepared)
        self.assertFalse((out / ddr.SEAL).exists())

    def test_missing_archive_or_tool_change_prevents_claim(self):
        out, ident, _, _ = self.prepare()
        self.archives.side_effect = ValueError('exact selected HDL header changed')
        with self.assertRaisesRegex(ValueError,'header changed'):
            self.continuation(ident['run_id'])
        self.archives.side_effect = None
        self.fingerprint.return_value = 'b' * 64
        with self.assertRaisesRegex(IdentityError,'simulator changed'):
            self.continuation(ident['run_id'])
        self.assertFalse((out / ddr.CLAIM).exists())

    def test_rejects_foreign_ci_attempt_and_swapped_build_record(self):
        first, ident, _, _ = self.prepare('ci-12345-a1-012345abcdef')
        second, _, _, _ = self.prepare('ci-12345-a1-012345abcd00')
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '12345', 'GITHUB_RUN_ATTEMPT': '2'}):
            with self.assertRaisesRegex(IdentityError,'different CI attempt'):
                self.continuation(ident['run_id'])
        (first / ddr.SEAL).write_bytes((second/ddr.SEAL).read_bytes())
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '12345', 'GITHUB_RUN_ATTEMPT': '1'}):
            with self.assertRaisesRegex(IdentityError,'changed before continuation'):
                self.continuation(ident['run_id'])
        self.assertFalse((first / ddr.CLAIM).exists())

    def test_full_runner_wiring_never_counts_a_build_log_as_runtime_pass(self):
        # Only the native simulator and report producers are fixtures here.
        # The real runner, input archive, planner, selector, and result writer
        # execute together, including the negative result identity.
        with patch.object(sys, 'path', [str(ROOT/'tools'), *sys.path]):
            import axi_report
            import protocol_report
            import regress
            import sim_cocotb
            import test_flow_report
            import variant_connectivity

            self.write(self.root/'config/regression.yaml',
                       (ROOT/'config/regression.yaml').read_bytes())
            options = SimpleNamespace(stage='build', arg=[], network=[], memory_config=None)
            resolver = Mock()
            resolver.config = {'defaults': {'timeout_s': 30}}
            resolver.sources.return_value = ([], [], [])

            def materialize(out, sources):
                for path in ddr.DDR_INPUTS:
                    self.write(out/path, path.encode())
                top = out/'variant/soc_top.sv'
                self.write(top, b'module soc_top; endmodule')
                return [str(top)]

            def fixture_process(command, log, timeout, env):
                plan = json.loads(Path(command[-1]).read_text())
                self.write(log, b'fixture native adapter')
                out = log.parent
                if plan['stage'] == 'build':
                    binary = self.root/plan['build']/plan['top']
                    self.write(binary, b'fixture executable, not hardware evidence')
                    binary.chmod(0o700)
                    self.write(binary.parent/'regression-build.json', json.dumps({
                        'binary_sha256': sha(binary.read_bytes()), 'signature': 'a' * 64,
                    }).encode())
                    self.write(out/'build.log', self.test['pass'].encode())
                else:
                    self.assertEqual(env['SOC_RUN_PLAN'], str(out/'plan.json'))
                    self.write(out/'simulation.log', b'no original PASS from the fixture')
                return 0, False

            def fixture_report(out, plan, result):
                self.write(out/'protocol-transactions.json', b'{"capture_complete":false,"records":[]}')
                return {'capture_bound': False, 'overflow': False, 'issues': 0, 'transactions': 0}

            with (patch.object(regress, 'ROOT', self.root),
                  patch.object(regress, 'noc_contracts', return_value={}),
                  patch.object(regress, 'append_pinned_dma_and_bender_sources'),
                  patch.object(regress, 'select_ddr_variant', side_effect=materialize) as producer,
                  patch.object(regress, 'run_process', side_effect=fixture_process),
                  patch.object(sim_cocotb, 'build_fingerprint', return_value='a' * 64),
                  patch.object(variant_connectivity, 'publish', return_value={'summary': {
                      'monitors': 0, 'declared_live_peripherals': 0}}),
                  patch.object(axi_report, 'write_report', side_effect=fixture_report),
                  patch.object(test_flow_report, 'write_report', return_value={
                      'passed': False, 'rows': [], 'issues': ['fixture']}),
                  patch.object(protocol_report, 'finalize_run', return_value=[])):
                self.assertTrue(regress.run_target(ddr.TARGET, self.test, resolver, options))
                identity_file, = self.root.glob('.tools/runs/*/*/*/*/identity.json')
                out = identity_file.parent
                frozen = (out/'plan.json').read_bytes()
                self.assertFalse((out/'result.json').exists())
                options.stage = 'run'
                options.continue_run_id = out.name
                self.assertFalse(regress.run_target(ddr.TARGET, self.test, resolver, options))
                self.assertEqual((out/'plan.json').read_bytes(), frozen)
                result = json.loads((out/'result.json').read_text())
                self.assertFalse(result['passed'])
                self.assertEqual(result['stage'], 'run')
                self.assertEqual(result['canonical_id'], out.relative_to(self.root/'.tools/runs').as_posix())
                self.assertFalse(result['results'][0]['passed'])
                producer.assert_called_once()
                resolver.sources.assert_called_once()

    def test_new_plan_requires_exact_own_address_map_and_preserves_old_identity(self):
        _, ident, plan, _ = self.prepare()
        self.assertEqual(validate(ident, plan=plan), ident)
        neutral = self.test['report']['address_map']
        old_config = {**self.test, 'report': {**self.test['report'], 'address_map': {
            **neutral, 'config': f'.tools/regression/{ddr.TARGET}/ddr_noc/soc.yaml',
            'csr_map': f'.tools/regression/{ddr.TARGET}/ddr-native-csr-map.json'}}}
        old_identity = selected(ddr.TARGET, old_config, root=self.root, run_id='local-aaaaaaaaaaaa')
        self.assertEqual(validate(old_identity, plan={**old_config, 'target': ddr.TARGET,
                                                     'identity': old_identity}), old_identity)
        self.assertNotEqual(old_identity['selection']['report_address_map'], neutral)
        plan['report']['address_map']['config'] = (
            plan['report']['address_map']['config']
            .replace(ident['run_id'], 'local-aaaaaaaaaaaa'))
        with self.assertRaisesRegex(IdentityError,'differs from plan'):
            validate(ident, plan=plan)


if __name__ == '__main__':
    unittest.main()
