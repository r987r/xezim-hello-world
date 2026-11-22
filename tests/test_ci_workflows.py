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
        self.assertIn('.tools/regression/chip-*/', upload(fullchip, 'full-chip-boot-results'))
        archive = upload(fullchip, 'full-chip-boot-results')
        reports = upload(fullchip, 'chip-axi-run-reports-')
        select_boot = next(step['run'] for step in fullchip if step.get('id') == 'static-chip-runs')
        self.assertIn('for name in ("chip-boot", "chip-boot-negative", "chip-boot-latency", "chip-dma")',
                      select_boot)
        self.assertIn('selected_run_folder(root, name, catalog[name])', select_boot)
        self.assertIn('steps.static-chip-runs.outputs.directories', archive)
        self.assertIn('.tools/runs/xezim/', archive)
        self.assertIn('steps.static-chip-runs.outputs.reports', reports)
        self.assertNotIn('.tools/regression/chip-dma/', reports)
        self.assertIn('.tools/regression/chip-cpu-dma/report.html', reports)
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
        self.assertTrue(any(name.startswith('fabric-latency-fullchip-')
                            for name in discovered['dv-fabric-latency.yml']['artifacts']))

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
