"""Merged PR publication evidence must be exact and auditable."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from publish_site import merged_main_pr_heads, verified_merged_pr, verified_pr_test_commit, verified_pr_tree_equivalent, dump, evidence_index
import tempfile
import json

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

    def test_real_github_pr_merge_sha_requires_exact_second_parent(self):
        head='a'*40
        merged='c'*40
        run={'event':'pull_request','head_sha':head,'head_branch':'feature/example','verified_merged_pr':9}
        client=Mock(repository='r987r/xezim-hello-world')
        client.request.return_value={'parents':[{'sha':'b'*40},{'sha':head}]}
        self.assertTrue(verified_pr_test_commit(client,run,merged))
        self.assertFalse(verified_pr_test_commit(client,{**run,'head_sha':'d'*40},merged))
        self.assertFalse(verified_pr_test_commit(client,{**run,'verified_merged_pr':None},merged))
        client.request.return_value={'parents':[{'sha':'b'*40},{'sha':'d'*40}]}
        self.assertFalse(verified_pr_test_commit(client,run,merged))
        self.assertTrue(verified_pr_test_commit(client,run,head))
        self.assertFalse(verified_pr_test_commit(client,run,'not-a-sha'))

    def test_equivalent_source_requires_real_merged_pr_and_identical_git_trees(self):
        head='a'*40; tested='b'*40; main='c'*40; tree='d'*40
        run={'event':'pull_request','head_sha':head,'head_branch':'feature/example',
             'verified_merged_pr':17}
        client=Mock(repository='r987r/xezim-hello-world')
        def request(path):
            if path.endswith(tested):
                return {'parents':[{'sha':'e'*40},{'sha':head}], 'tree':{'sha':tree}}
            if path.endswith(main):
                return {'parents':[{'sha':'f'*40},{'sha':tested}], 'tree':{'sha':tree}}
            raise ValueError('unexpected mocked GitHub commit')
        client.request.side_effect=request
        self.assertTrue(verified_pr_tree_equivalent(client,run,tested,main))
        self.assertFalse(verified_pr_tree_equivalent(client,{**run,'verified_merged_pr':None},tested,main))
        self.assertFalse(verified_pr_tree_equivalent(client,run,tested,'invalid-sha'))
        def mismatch(path):
            data=request(path)
            if path.endswith(main):
                data={**data,'tree':{'sha':'f'*40}}
            return data
        client.request.side_effect=mismatch
        self.assertFalse(verified_pr_tree_equivalent(client,run,tested,main))
        def fake_parent(path):
            data=request(path)
            if path.endswith(tested):
                data={**data,'parents':[{'sha':'e'*40},{'sha':'f'*40}]}
            return data
        client.request.side_effect=fake_parent
        self.assertFalse(verified_pr_tree_equivalent(client,run,tested,main))

    def test_evidence_index_uses_verified_tested_merge_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'123-1';folder.mkdir()
            head='a'*40;actual='c'*40
            dump(folder/'run.json',{'id':123,'name':'NoC', 'run_attempt':1,
                'head_branch':'feature/example', 'head_sha':head,
                'verified_tested_shas':[actual],'verified_merged_pr':9,
                'verified_equivalent_site_shas':{actual:'e'*40},
                'event':'pull_request','status':'completed','conclusion':'success',
                'path':'.github/workflows/floonoc-elab.yml',
                'created_at':'2026-11-04T10:00:00Z','updated_at':'2026-11-04T10:01:00Z',
                'html_url':'https://github.com/r987r/xezim-hello-world/actions/runs/123'})
            dump(folder/'workflow.json',{'label':'NoC checks'})
            target=folder/'artifact-5'/'chip-boot';target.mkdir(parents=True)
            dump(target/'result.json',{'target':'chip-boot','passed':True,'stage':'all'})
            dump(target/'plan.json',{'engine':'verilator'})
            dump(target/'axi-transactions.json',{'schema_version':1,'run':{
                'commit':actual,'dirty':False,'workflow_run_id':'123','workflow_attempt':'1',
                'target':'chip-boot'},'sections':{'axi':{'monitors':[],'transactions':[],'issues':[]}}})
            output=root/'out';output.mkdir()
            runs,entries,notes=evidence_index(root,output,'r987r/xezim-hello-world')
            self.assertEqual(entries[0]['source_sha'],actual)
            self.assertEqual(entries[0]['pr_head_sha'],head)
            self.assertEqual(entries[0]['merged_pr'],9)
            self.assertEqual(entries[0]['verified_site_source_sha'],'e'*40)
            self.assertEqual(runs[0]['tested_sha'],actual)
            # A different merge SHA is never inferred or accepted.
            data=json.loads((target/'axi-transactions.json').read_text())
            data['run']['commit']='d'*40
            dump(target/'axi-transactions.json',data)
            with self.assertRaisesRegex(ValueError,'provenance'):
                evidence_index(root,root/'out2','r987r/xezim-hello-world')

if __name__=='__main__':
    unittest.main()
