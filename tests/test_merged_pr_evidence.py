"""Merged PR publication evidence must be exact and auditable."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from publish_site import merged_main_pr_heads, verified_merged_pr

class MergedPrEvidenceTests(unittest.TestCase):
    def test_exact_sha_branch_without_pr_association(self):
        run={'event':'pull_request','head_sha':'a'*40,'head_branch':'feature/fabric-explorer-connectivity','pull_requests':[]}
        approved={('a'*40,'feature/fabric-explorer-connectivity'):15}
        self.assertEqual(verified_merged_pr(run,approved),15)
        self.assertIsNone(verified_merged_pr({**run,'head_sha':'b'*40},approved))
        self.assertIsNone(verified_merged_pr({**run,'head_branch':'different'},approved))
        self.assertIsNone(verified_merged_pr({**run,'event':'push'},approved))

    def test_only_merged_main_prs(self):
        def response(path):
            return [
                {'number':15,'merged_at':'2026-11-04T16:30:24Z','base':{'ref':'main'},'head':{'sha':'a'*40,'ref':'fabric'}},
                {'number':14,'merged_at':None,'base':{'ref':'main'},'head':{'sha':'b'*40,'ref':'dma'}},
                {'number':12,'merged_at':'2026-11-04T10:00:00Z','base':{'ref':'develop'},'head':{'sha':'c'*40,'ref':'test'}}
            ]
        self.assertEqual(merged_main_pr_heads(Mock(request=response)),{('a'*40,'fabric'):15})

if __name__=='__main__':
    unittest.main()
