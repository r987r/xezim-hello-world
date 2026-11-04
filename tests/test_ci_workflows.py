"""GitHub Actions must be PR-to-main or manually dispatched only."""
from pathlib import Path
import unittest

import yaml

ROOT=Path(__file__).resolve().parents[1]

class WorkflowPolicyTests(unittest.TestCase):
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
        # Site styling must not queue an expensive NoC traffic regression.
        noc=(ROOT/'.github/workflows/floonoc-elab.yml').read_text()
        self.assertNotIn("'tools/templates/**'",noc)
        self.assertIn("'tools/templates/run_report.html'",noc)

if __name__=='__main__':
    unittest.main()
