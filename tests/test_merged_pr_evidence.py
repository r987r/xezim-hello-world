"""Merged PR publication evidence must be exact and auditable."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
import base64

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from publish_site import (merged_main_pr_heads, verified_merged_pr, verified_pr_test_commit,
                          verified_pr_tree_equivalent, fabric_execution_fingerprint,
                          verified_fabric_execution_equivalent, FABRIC_REQUIRED_INPUTS,
                          FABRIC_EXECUTION_WORKFLOWS, dump, evidence_index)
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

    def test_archived_runner_commit_is_authenticated_not_renamed(self):
        from publish_site import authenticated_runner_revisions
        from runtime_contract import digest
        from test_intent import plan as declared_intent
        head='a'*40
        merged='c'*40
        run={'event':'pull_request','head_sha':head,
             'head_branch':'feature/naming','verified_merged_pr':129}
        client=Mock(repository='r987r/xezim-hello-world')
        client.request.return_value={'parents':[{'sha':'b'*40},{'sha':head}]}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            payload={'engine':'cocotb-verilator','stage':'all'}
            snapshot={'schema_version':1,'target':'chip-boot',
                'source_revision':merged,'stage':'all','engine':'cocotb-verilator',
                'adapter':'legacy_entrypoint_adapter',
                'migration_owner_issue':119,
                'adapter_scope':'legacy_internal_stimulus_opaque',
                'selected_firmware_mode':None,'seed':None,
                'command_argv':[], 'scenario_plan_sha256':None,
                'intent':declared_intent('chip-boot',payload),
                'evidence_kind':'selected_definition_not_runtime_execution'}
            snapshot['plan_sha256']=digest(snapshot)
            dump(folder/'selected-test-plan.json',snapshot)
            self.assertEqual(authenticated_runner_revisions(client,run,folder),{merged})
            self.assertEqual(authenticated_runner_revisions(client,
                             {'head_branch':'main','head_sha':merged},folder),{merged})
            with self.assertRaisesRegex(ValueError,'not authenticated'):
                authenticated_runner_revisions(client,
                    {'head_branch':'main','head_sha':'d'*40},folder)
            client.request.return_value={'parents':[{'sha':'b'*40},{'sha':'e'*40}]}
            with self.assertRaisesRegex(ValueError,'not authenticated'):
                authenticated_runner_revisions(client,run,folder)
            snapshot['source_revision']='f'*40
            dump(folder/'selected-test-plan.json',snapshot)
            with self.assertRaisesRegex(ValueError,'invalid selected runner snapshot'):
                authenticated_runner_revisions(client,run,folder)

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

    def test_current_rtl_input_fingerprint_ignores_docs_not_real_source(self):
        previous='1'*40
        current='2'*40
        head='3'*40
        base='4'*40
        old_tree='5'*40
        new_tree='6'*40
        base_blobs={p:'a'*40 for p in FABRIC_REQUIRED_INPUTS}
        base_blobs.update({'rtl/new_module.sv':'b'*40,'README.md':'1'*40,
                           'docs/publication.md':'1'*40,
                           '.github/workflows/pages.yml':'1'*40,
                           'tools/templates/run_report.html':'1'*40,
                           # The *compiled* generated top is still an input.
                           'gen/chip/soc_top.sv':'1'*40,
                           # Review-only copies and metadata are not selected
                           # by Bender or executed by the latency benchmark.
                           'gen/projects/xezim_soc_dv/variants/default/rtl/soc_top.sv':'2'*40,
                           'gen/projects/xezim_soc_dv/variants/default/manifest.json':'3'*40,
                           'gen/manifest.json':'4'*40,
                           'tools/generate.py':'5'*40,
                           'tools/stage_selected_rtl.py':'6'*40})
        new_blobs={**base_blobs, 'docs/publication.md':'2'*40,
                   'README.md':'2'*40,'.github/workflows/pages.yml':'2'*40,
                   'tools/templates/run_report.html':'2'*40,
                   # Unintegrated staged memory work must not erase the
                   # current NoC latency measurements.
                   'rtl/memory/ddr4/bringup.py':'2'*40,
                   'rtl/memory/ddr4/sim_model.py':'3'*40,
                   'rtl/memory/ddr4/toolchain.lock.yml':'4'*40,
                   # The SoC diagram's new syntax-only parser runs only
                   # during Pages publication, not in the RTL regression.
                   'tools/rtl_instance_parser.py':'4'*40,
                   'tools/design_explorer.py':'5'*40,
                   'tools/signal_inventory.py':'6'*40,
                   'tools/noc_diagrams.py':'7'*40,
                   'gen/diagrams/noc-hierarchy.svg':'8'*40,
                   'gen/diagrams/noc-topology.json':'9'*40,
                   # Actual merge #185/#187 introduced these checked-in
                   # source-review artifacts but did not compile them.
                   'gen/projects/xezim_soc_dv/variants/default/rtl/soc_top.sv':'7'*40,
                   'gen/projects/xezim_soc_dv/variants/default/manifest.json':'8'*40,
                   'gen/manifest.json':'9'*40,
                   'tools/generate.py':'c'*40,
                   'tools/stage_selected_rtl.py':'d'*40}
        workflows={}
        blob_sources={}
        for name in FABRIC_EXECUTION_WORKFLOWS:
            path='.github/workflows/'+name
            wf_old=('name: NoC\non: push\njobs:\n  elaborate:\n'
                    '    runs-on: ubuntu-24.04\n    steps:\n'
                    '    - run: make dv-supernoc\n')
            wf_new=wf_old.replace('on: push','on: pull_request')
            old_blob=('c' if name=='floonoc-elab.yml' else 'd')*40
            new_blob=('e' if name=='floonoc-elab.yml' else 'f')*40
            workflows[path]=(old_blob,new_blob)
            blob_sources[old_blob]=wf_old
            blob_sources[new_blob]=wf_new
        def rows(blobs,which):
            all_files={**blobs,**{p:shas[which] for p,shas in workflows.items()}}
            return [{'path':p,'sha':sha,'type':'blob'} for p,sha in all_files.items()]
        old_rows=rows(base_blobs,0)
        new_rows=rows(new_blobs,1)
        def request(path):
            if path.endswith('/git/commits/'+previous):
                return {'tree':{'sha':old_tree},'parents':[{'sha':base},{'sha':head}]}
            if path.endswith('/git/commits/'+current):
                return {'tree':{'sha':new_tree},'parents':[{'sha':previous}]}
            if path.endswith('/git/trees/'+old_tree+'?recursive=1'):
                return {'truncated':False,'tree':old_rows}
            if path.endswith('/git/trees/'+new_tree+'?recursive=1'):
                return {'truncated':False,'tree':new_rows}
            blob=path.rsplit('/',1)[-1]
            if blob in blob_sources:
                return {'encoding':'base64','content':base64.b64encode(blob_sources[blob].encode()).decode()}
            raise AssertionError(path)
        client=Mock(repository='r987r/xezim-hello-world')
        client.request.side_effect=request
        old=fabric_execution_fingerprint(client,previous)
        new=fabric_execution_fingerprint(client,current)
        self.assertIsNotNone(old)
        self.assertEqual(old,new)
        self.assertEqual(old['file_count'],len(FABRIC_REQUIRED_INPUTS)+1)
        self.assertEqual(old['policy'],'fabric-execution-inputs-v2')
        # Only the *selected* RTL source is timing-relevant. Changing a
        # review-only copy must not cause another 20+ minute simulation.
        next(x for x in new_rows if x['path']=='gen/chip/soc_top.sv')['sha']='f'*40
        self.assertNotEqual(fabric_execution_fingerprint(client,previous),
                            fabric_execution_fingerprint(client,current))
        next(x for x in new_rows if x['path']=='gen/chip/soc_top.sv')['sha']='1'*40
        main_run={'head_branch':'main','head_sha':previous}
        self.assertTrue(verified_fabric_execution_equivalent(
            client,main_run,previous,current))
        self.assertFalse(verified_fabric_execution_equivalent(
            client,{**main_run,'head_sha':'7'*40},previous,current))
        pr_run={'head_branch':'feature/rtl','head_sha':head,'verified_merged_pr':17}
        self.assertTrue(verified_fabric_execution_equivalent(
            client,pr_run,previous,current))
        self.assertFalse(verified_fabric_execution_equivalent(
            client,{**pr_run,'verified_merged_pr':None},previous,current))
        # Changing any RTL or the executing verification job must invalidate.
        new_rows[0]['sha']='8'*40
        # Mutate a specifically checked-in DV source instead of assuming
        # Git tree enumeration order.
        next(x for x in new_rows if x['path']=='dv/supernoc/test_supernoc.py')['sha']='9'*40
        self.assertNotEqual(fabric_execution_fingerprint(client,previous),
                            fabric_execution_fingerprint(client,current))
        next(x for x in new_rows if x['path']=='dv/supernoc/test_supernoc.py')['sha']='a'*40
        new_rows[0]['sha']=base_blobs.get(new_rows[0]['path'],new_rows[0]['sha'])
        original=blob_sources[workflows['.github/workflows/floonoc-elab.yml'][1]]
        blob_sources[workflows['.github/workflows/floonoc-elab.yml'][1]] = original.replace(
            'make dv-supernoc','make dv-chip')
        self.assertNotEqual(fabric_execution_fingerprint(client,previous),
                            fabric_execution_fingerprint(client,current))
        blob_sources[workflows['.github/workflows/floonoc-elab.yml'][1]] = original
        def truncated(path):
            value=request(path)
            if path.endswith('/git/trees/'+new_tree+'?recursive=1'):
                return {**value,'truncated':True}
            return value
        client.request.side_effect=truncated
        self.assertIsNone(fabric_execution_fingerprint(client,current))

    def test_evidence_index_uses_verified_tested_merge_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'123-1';folder.mkdir()
            head='a'*40;actual='c'*40
            dump(folder/'run.json',{'id':123,'name':'NoC', 'run_attempt':1,
                'head_branch':'feature/example', 'head_sha':head,
                'verified_tested_shas':[actual],'verified_merged_pr':9,
                'verified_equivalent_site_shas':{actual:'e'*40},
                'verified_equivalent_fabric_shas':{actual:'f'*40},
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
            self.assertEqual(entries[0]['verified_fabric_source_sha'],'f'*40)
            self.assertEqual(runs[0]['tested_sha'],actual)
            # A different merge SHA is never inferred or accepted.
            data=json.loads((target/'axi-transactions.json').read_text())
            data['run']['commit']='d'*40
            dump(target/'axi-transactions.json',data)
            with self.assertRaisesRegex(ValueError,'provenance'):
                evidence_index(root,root/'out2','r987r/xezim-hello-world')

if __name__=='__main__':
    unittest.main()
