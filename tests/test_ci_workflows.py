"""GitHub Actions must be PR-to-main or manually dispatched only."""
from fnmatch import fnmatchcase
from pathlib import Path
import sys
import unittest

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

class WorkflowPolicyTests(unittest.TestCase):
    def test_project_compile_covers_both_project_sources_and_shared_contracts(self):
        workflow = ROOT / '.github/workflows/project-compile.yml'
        doc = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)
        paths = doc['on']['pull_request']['paths']
        catalog = yaml.safe_load((ROOT / 'config/projects/catalog.yaml').read_text())
        sources = {p['config'] for p in catalog['projects']
                   if p['qualification'] != 'source_contract_only'}
        sources.update({'config/interface_contracts.yaml', 'config/ip.lock.yaml',
                        'config/regression.yaml', 'Bender.yml', 'Bender.lock',
                        'requirements.txt', 'tools/ip_fetch.py', 'tools/regress.py',
                        '.github/actions/setup-bender/action.yml'})
        for source in sorted(sources):
            with self.subTest(source=source):
                self.assertTrue(any(fnmatchcase(source, path) for path in paths), source)

    def test_static_full_chip_workspaces_keep_current_ci_consumers(self):
        from publish_site import discover_test_workflows
        from run_workspace import uses_canonical_workspace
        from test_identity import relative_path, selected

        catalog = yaml.safe_load((ROOT / 'config/regression.yaml').read_text())['tests']
        names = ('chip-boot', 'chip-boot-negative', 'chip-boot-latency')
        selected_family = {name for name, plan in catalog.items()
                           if plan.get('engine') == 'cocotb-verilator'
                           and not plan.get('firmware_mode')
                           and name.startswith('chip-')
                           and uses_canonical_workspace(name, plan)}
        self.assertEqual(selected_family, set(names) | {'chip-dma'})
        plans = [catalog[name] for name in names]
        self.assertEqual({p['build'] for p in plans}, {'.tools/chip-obj'})
        self.assertFalse(plans[0].get('reuse_build', False))
        self.assertTrue(all(p['reuse_build'] for p in plans[1:]))
        paths = [relative_path(selected(name, plan, run_id='local-012345abcdef'))
                 for name, plan in zip(names, plans)]
        self.assertEqual(len(set(paths)), 3)

        def steps(workflow, job):
            path = ROOT / '.github/workflows' / workflow
            return yaml.load(path.read_text(), Loader=yaml.BaseLoader)['jobs'][job]['steps']

        def upload(steps, name):
            return next(step['with']['path'] for step in steps
                        if step.get('with', {}).get('name', '').startswith(name))

        fullchip = steps('full-chip.yml', 'boot')
        self.assertNotIn('.tools/regression/', upload(fullchip, 'full-chip-boot-results'))
        archive = upload(fullchip, 'full-chip-boot-results')
        reports = upload(fullchip, 'chip-axi-run-reports-')
        select_boot = next(step['run'] for step in fullchip if step.get('id') == 'chip-runs')
        self.assertIn('for name in ("chip-boot", "chip-boot-negative", "chip-boot-latency",',
                      select_boot)
        self.assertIn('"chip-dma", "chip-cpu-dma")', select_boot)
        self.assertIn('successful chip-cpu-dma regression lacks canonical result', select_boot)
        self.assertIn('selected_run_folder(root, name, catalog[name])', select_boot)
        self.assertIn('steps.chip-runs.outputs.directories', archive)
        self.assertIn('.tools/runs/xezim/', archive)
        self.assertIn('steps.chip-runs.outputs.reports', reports)
        self.assertNotIn('.tools/regression/chip-dma/', reports)
        self.assertNotIn('.tools/regression/chip-cpu-dma/', reports)
        self.assertNotIn('.tools/runs/verilator/', archive + reports)
        self.assertNotIn('.tools/regression/chip-boot', reports)

        latency = steps('dv-fabric-latency.yml', 'unloaded-full-chip')
        select_latency = next(step['run'] for step in latency
                              if step.get('id') == 'fullchip-latency-run')
        self.assertIn('selected_run_folder(root, name, plan)', select_latency)
        self.assertIn('name = "chip-boot-latency"', select_latency)
        self.assertIn('steps.fullchip-latency-run.outputs.canonical_id',
                      upload(latency, 'fabric-latency-fullchip-'))

        mux = steps('ethernet-mvp.yml', 'noc-axi-mux')
        select_mux = next(step['run'] for step in mux if step.get('id') == 'chip-boot-source')
        self.assertIn('chip-boot --stage files', select_mux)
        self.assertIn('selected_run_folder(root, name, plan)', select_mux)
        self.assertIn('-f "$filelist"', select_mux)
        self.assertNotIn('.tools/regression/', select_mux)
        self.assertIn('steps.chip-boot-source.outputs.filelist',
                      upload(mux, 'ethernet-axi-mux-sources-'))
        discovered = discover_test_workflows(ROOT)
        self.assertIn('full-chip-boot-results', discovered['full-chip.yml']['artifacts'])
        self.assertTrue(any(name.startswith('chip-axi-run-reports-')
                            for name in discovered['full-chip.yml']['artifacts']))
        self.assertTrue(any(name.startswith('fabric-latency-fullchip-')
                            for name in discovered['dv-fabric-latency.yml']['artifacts']))

    def test_ethernet_variant_archives_only_the_existing_execution(self):
        from publish_site import discover_test_workflows
        workflow = ROOT / '.github/workflows/ethernet-mvp.yml'
        jobs = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)['jobs']
        for job, selector, simulator, prefix in (
                ('chip-real-noc', 'ethernet-execution', 'run-ethernet',
                 'ethernet-chip-data-config-noc-'),
                ('chip-cpu-ethernet', 'ethernet-cpu-execution', 'run-ethernet-cpu',
                 'ethernet-cpu0-c-queue-cq-')):
            steps = jobs[job]['steps']
            select = next(step for step in steps if step.get('id') == selector)
            upload = next(step for step in steps
                          if step.get('with', {}).get('name', '').startswith(prefix))
            self.assertIn('stage="all"', select['run'])
            self.assertIn(f'steps.{simulator}.outcome', select['env']['SIMULATION_OUTCOME'])
            self.assertIn('successful Ethernet regression lacks canonical result', select['run'])
            self.assertIn("format('.tools/runs/{0}/'", upload['with']['path'])
            self.assertIn(f'steps.{selector}.outputs.canonical_id', upload['with']['path'])
            discovered = discover_test_workflows(ROOT)['ethernet-mvp.yml']['artifacts']
            self.assertTrue(any(name.startswith(prefix) for name in discovered))
        preflight = next(step['run'] for step in jobs['chip-cpu-ethernet']['steps']
                         if 'Verify RV32I' in step.get('name', ''))
        self.assertIn('stage="files"', preflight)
        for member in ('variant/cpu_dma.elf', 'variant/flash.hex', 'sources.f'):
            self.assertIn(member, preflight)

    def test_cpu_and_pcie_workflows_preserve_original_archive_names(self):
        from publish_site import discover_test_workflows
        cases = (
            ('pcie0-integrated.yml', 'pcie0-real-noc', 'pcie-host-execution',
             'run-pcie-host', 'pcie0-dedicated-noc-'),
            ('pcie0-integrated.yml', 'cpu-c-same-flow', 'cpu-dma-execution',
             'run-cpu-dma', 'cpu-c-init-run-check-flow-'),
            ('pcie-outbound.yml', 'full-chip-outbound-idma', 'pcie-outbound-execution',
             'run-pcie-outbound', 'pcie-outbound-fullchip-'),
        )
        discovered = discover_test_workflows(ROOT)
        for workflow, job, helper, producer, name in cases:
            path = ROOT / '.github/workflows' / workflow
            steps = yaml.load(path.read_text(), Loader=yaml.BaseLoader)['jobs'][job]['steps']
            sel = next(step for step in steps if step.get('id') == helper)
            self.assertIn('stage="all"', sel['run'])
            self.assertIn(f'steps.{producer}.outcome', sel['env']['SIMULATION_OUTCOME'])
            self.assertTrue(any(item.startswith(name)
                                for item in discovered[workflow]['artifacts']))

    def test_ddr_split_archive_still_feeds_pages_without_uploading_unbound_runs(self):
        from publish_site import discover_test_workflows
        from test_identity import RUN, relative_path, selected

        workflow = 'ddr4-fullchip.yml'
        path = ROOT / '.github/workflows' / workflow
        steps = yaml.load(path.read_text(), Loader=yaml.BaseLoader)['jobs']['cpu-idma-ddr']['steps']
        archive_name = 'ddr4-fullchip-cpu-dma-evidence'
        upload = next(step['with'] for step in steps
                      if step.get('with', {}).get('name') == archive_name)
        self.assertIn(archive_name, discover_test_workflows(ROOT)[workflow]['artifacts'])

        target = 'chip-ddr4-real'
        plan = yaml.safe_load((ROOT/'config/regression.yaml').read_text())['tests'][target]
        example = selected(target, plan, run_id='ci-123-a1-012345abcdef')
        prefix = f".tools/runs/{relative_path(example).parent.as_posix()}/"
        canonical = [line for line in upload['path'].splitlines() if line.startswith('.tools/runs/')]
        fallback = '_no-ddr-build_'
        self.assertEqual(canonical, [
            prefix + "${{ steps.ddr-build.outputs.run_id || '_no-ddr-build_' }}/"])
        self.assertIsNone(RUN.fullmatch(fallback))
        self.assertNotIn(".tools/chip-ddr4-real-obj/", upload['path'])
        self.assertNotIn(".tools/regression/", upload['path'])
        self.assertNotIn('steps.ddr-build.outputs.run_dir', upload['path'])

    def test_combined_archive_keeps_source_replay_and_exact_run_separate(self):
        from publish_site import discover_test_workflows
        from test_identity import RUN, relative_path, selected

        wf = 'dv-combined34.yml'
        steps = yaml.load((ROOT/'.github/workflows'/wf).read_text(),
                          Loader=yaml.BaseLoader)['jobs']['real-combined-rtl']['steps']
        build = next(step for step in steps if step.get('id') == 'combined-build')
        upload = next(step['with'] for step in steps
                      if step.get('with', {}).get('name', '').startswith('dv-combined34-single-chip-'))
        replay = next(step['run'] for step in steps if 'generate actual LiteDRAM' in step.get('name', ''))
        self.assertIn('"--stage", "files"', replay)
        self.assertIn('prepared_workspace(root, definition', replay)
        self.assertIn('["--files-workspace", str(folder)]', replay)
        self.assertIn('"--explain", *args', replay)
        self.assertIn('"tools/selected_source_reference.py", "--profile", PROFILE, *args', replay)
        self.assertIn('"tools/stage_selected_rtl.py", "--profile", PROFILE, *args', replay)
        self.assertIn('build_hardware_variant.py --profile chip-ethernet-ddr-pcie --check', replay)
        self.assertNotIn('--canonical-combined-files', replay)
        portable = next(step['run'] for step in steps
                        if 'replay checked-in portable' in step.get('name', ''))
        self.assertIn('make check-generated-combined', portable)
        self.assertIn('len(plans) == 3', portable)
        self.assertIn('assert_iverilog_clean()', portable)
        self.assertIn('verilator --lint-only', portable)
        self.assertIn('--stage build', build['run'])
        self.assertIn('combined-runtime-input-equivalence.json', build['run'])
        self.assertNotIn('.tools/regression/', upload['path'])
        self.assertNotIn('.tools/chip-ethernet-ddr-pcie-obj/', upload['path'])
        self.assertIn(upload['name'], discover_test_workflows(ROOT)[wf]['artifacts'])
        target = 'chip-ethernet-ddr-pcie'
        cfg = yaml.safe_load((ROOT/'config/regression.yaml').read_text())['tests'][target]
        example = selected(target, cfg, run_id='local-012345abcdef')
        prefix = f".tools/runs/{relative_path(example).parent.as_posix()}/"
        canonical = [p for p in upload['path'].splitlines() if p.startswith('.tools/runs/')]
        self.assertEqual(canonical, [
            prefix + "${{ steps.combined-build.outputs.run_id || '_no-combined-build_' }}/"])
        self.assertIsNone(RUN.fullmatch('_no-combined-build_'))

    def test_scenario_archives_exact_replay_pairs_under_the_original_name(self):
        from publish_site import discover_test_workflows
        path = ROOT / '.github/workflows/dv-scenario.yml'
        steps = yaml.load(path.read_text(), Loader=yaml.BaseLoader)['jobs']['scenario-real-rtl']['steps']
        replay = next(step for step in steps if step.get('id') == 'real-scenario-replay')
        archive = next(step['with'] for step in steps
                       if step.get('with', {}).get('name', '').startswith('dv-scenario-rtl-'))
        self.assertIn("prior_run_ids=before[name]", replay['run'])
        self.assertIn("ambiguous or missing invocation", replay['run'])
        self.assertIn("verify_replay_input", replay['run'])
        self.assertIn("shutil.make_archive", replay['run'])
        self.assertIn("steps.real-scenario-replay.outputs.paths", archive['path'])
        self.assertIn(".tools/scenarios/rtl-seed-matrix/", archive['path'])
        self.assertNotIn(".tools/regression/", archive['path'])
        self.assertIn(archive['name'],
                      discover_test_workflows(ROOT)['dv-scenario.yml']['artifacts'])

    def test_csr_boot_archive_keeps_existing_pages_consumer(self):
        from publish_site import discover_test_workflows

        path = ROOT / '.github/workflows/csr.yml'
        steps = yaml.load(path.read_text(), Loader=yaml.BaseLoader)['jobs']['csr-rtl-boot']['steps']
        preflight = next(i for i, step in enumerate(steps)
                         if step.get('run') == 'python3 tools/run_csr_axi.py')
        clean_gate = next(i for i, step in enumerate(steps)
                          if 'git status --porcelain --untracked-files=all' in step.get('run', ''))
        chip_boot = next(i for i, step in enumerate(steps) if step.get('id') == 'csr-boot')
        self.assertLess(preflight, clean_gate)
        self.assertLess(clean_gate, chip_boot)
        self.assertTrue(any("assert real['run']['dirty'] is False" in step.get('run', '')
                            for step in steps[chip_boot:]))
        selector = next(step for step in steps if step.get('id') == 'csr-run')
        self.assertIn("selected_run_folder(root, target, catalog[target], stage='all')",
                      selector['run'])
        self.assertIn('successful CSR boot lacks canonical result', selector['run'])
        archive_name = 'csr-peakrdl-real-chip-boot'
        upload = next(step['with'] for step in steps
                      if step.get('with', {}).get('name') == archive_name)
        self.assertIn('.tools/runs/${{ steps.csr-run.outputs.canonical_id }}/', upload['path'])
        self.assertNotIn('.tools/regression/', upload['path'])
        self.assertIn(archive_name, discover_test_workflows(ROOT)['csr.yml']['artifacts'])

    def test_only_pr_to_main_or_manual_dispatch(self):
        for path in sorted((ROOT/'.github/workflows').glob('*.yml')):
            with self.subTest(workflow=path.name):
                doc=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
                events=doc['on']
                self.assertIsInstance(events,dict)
                self.assertIn('workflow_dispatch',events)
                self.assertTrue(set(events).issubset({'workflow_dispatch','pull_request'}),events)
                if 'pull_request' in events:
                    self.assertEqual(events['pull_request'].get('branches'),['main'])
        pages=yaml.load((ROOT/'.github/workflows/pages.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertIn('closed',pages['on']['pull_request']['types'])
        self.assertNotIn('push',pages['on'])
        self.assertNotIn('workflow_run',pages['on'])
        # Separate a short merge event (which only dispatches main) from
        # the long Pages builder. Otherwise new merges replace a pending
        # closed-PR event before it can enqueue the measured publication.
        group = pages['concurrency']['group']
        self.assertIn("format('merge-{0}', github.event.pull_request.number)", group)
        self.assertIn("format('preview-{0}', github.event.pull_request.number)", group)
        self.assertIn("'publish-main'", group)
        self.assertNotIn("|| 'publish' }}", group)
        self.assertIn('github.event.action != \'closed\'',
                      pages['concurrency']['cancel-in-progress'])
        # Pull-request runs must only preview or dispatch; they cannot deploy
        # directly because GitHub Pages restricts deployments by run ref.
        dispatch=pages['jobs']['dispatch-after-merge']
        self.assertIn("github.event.pull_request.merged == true",dispatch['if'])
        self.assertEqual(dispatch['permissions']['actions'],'write')
        deploy=pages['jobs']['deploy']
        self.assertIn("github.event_name == 'workflow_dispatch'",deploy['if'])
        self.assertIn("github.ref == 'refs/heads/main'",deploy['if'])
        self.assertNotIn('pull_request',deploy['if'])
        # Site styling must not queue an expensive NoC traffic regression.
        noc=(ROOT/'.github/workflows/floonoc-elab.yml').read_text()
        self.assertNotIn("'tools/templates/**'",noc)
        self.assertIn("'tools/templates/run_report.html'",noc)
        self.assertIn("'tools/fabric_report.py'",noc)
        self.assertNotIn("'tools/templates/site_fabric.html'",noc)

if __name__=='__main__':
    unittest.main()
