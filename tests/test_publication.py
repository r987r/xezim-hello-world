"""Evidence provenance, safe extraction and project-subpath publication."""
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import zipfile

import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import publish_site as site

SHA='a'*40
CONFIG=yaml.safe_load((ROOT/'config/publication.yaml').read_text())


def fixture(root,axi=False,passed=True,flattened=False):
    folder=root/'123-1';folder.mkdir(parents=True)
    site.dump(folder/'run.json',{'id':123,'run_attempt':1,'name':'Test workflow','path':'.github/workflows/full-chip.yml',
        'status':'completed','conclusion':'success' if passed else 'failure','head_sha':SHA,'head_branch':'main',
        'html_url':'https://github.com/r987r/xezim-hello-world/actions/runs/123',
        'created_at':'2026-11-04T00:00:00Z','updated_at':'2026-11-04T00:01:00Z'})
    site.dump(folder/'workflow.json',{'label':'Chip boot'})
    target=folder/'artifact-100'
    if not flattened:target=target/'chip-boot'
    target.mkdir(parents=True)
    site.dump(target/'result.json',{'target':'chip-boot','passed':passed,'stage':'all'})
    site.dump(target/'plan.json',{'engine':'cocotb-verilator','expect_failure':'required mismatch'})
    (target/'simulation.log').write_text('actual simulator transcript')
    (target/'sources.f').write_text('/source/original.sv\n')
    (target/'results.xml').write_text('<testsuites/>')
    if axi:
        site.dump(target/'axi-transactions.json',{'schema_version':1,
            'run':{'commit':SHA,'dirty':False,'workflow_run_id':'123','workflow_attempt':'1','target':'chip-boot'},
            'sections':{'axi':{'monitors':[],'transactions':[],'issues':[]}}})
    return target


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        self.links.extend(value for key,value in attrs if key in ('href','src'))


class PublicationTests(unittest.TestCase):
    def test_ci_producer_discovery_includes_new_protocol_workflows(self):
        workflows=site.discover_test_workflows(ROOT)
        self.assertIn("ethernet-mvp.yml",workflows)
        self.assertIn("ethernet-standalone.yml",workflows)
        self.assertIn("pcie0-integrated.yml",workflows)
        self.assertIn("full-chip.yml",workflows)
        self.assertNotIn("pages.yml",workflows)
        self.assertNotIn("publish-xezim.yml",workflows)
        self.assertTrue(any("ethernet-chip-data-config" in a for a in workflows["ethernet-mvp.yml"]["artifacts"]))
        self.assertTrue(any("pcie0-dedicated-noc" in a for a in workflows["pcie0-integrated.yml"]["artifacts"]))

    def test_future_workflow_is_discovered_without_yaml_registration(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/".github/workflows"
            directory.mkdir(parents=True)
            (directory/"new-ip.yml").write_text(
                "name: New protocol\njobs:\n  test:\n    steps:\n"
                "      - uses: actions/upload-artifact@v4\n"
                "        with:\n          name: custom-${{ github.run_id }}\n"
                "          path: .tools/regression/chip-new-ip/\n")
            result=site.discover_test_workflows(Path(temp))
            self.assertIn("new-ip.yml",result)
            self.assertEqual(result["new-ip.yml"]["label"],"New protocol")

    def test_standalone_test_without_artifact_is_visible_as_workflow_only(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/".github/workflows"
            directory.mkdir(parents=True)
            (directory/"standalone.yml").write_text(
                "name: Standalone Ethernet sanity\njobs:\n  test:\n    steps:\n"
                "      - run: python3 -m unittest tests.test_ethernet_queue_api -v\n")
            workflows=site.discover_test_workflows(Path(temp))
            self.assertIn("standalone.yml",workflows)
            self.assertEqual(workflows["standalone.yml"]["artifacts"],[])
    def test_workflow_scoped_history_cannot_be_starved_by_other_ci(self):
        from unittest.mock import Mock
        from datetime import datetime
        names={"ethernet-mvp.yml": {}, "pcie0-integrated.yml": {}}
        calls=[]
        def request(path):
            calls.append(path)
            workflow=next(name for name in names if name in path)
            return {"workflow_runs": [
                {"id": 123 if workflow.startswith("ethernet") else 456,
                 "path": ".github/workflows/"+workflow,
                 "head_branch": "main", "head_sha": SHA,
                 "event": "workflow_dispatch", "status": "completed",
                 "conclusion": "success"}]}
        client=Mock(repository="r987r/xezim-hello-world",request=Mock(side_effect=request))
        selected,notes=site.select_workflow_runs(client,names,{},4)
        self.assertFalse(notes)
        self.assertEqual(selected["ethernet-mvp.yml"][0]["id"],123)
        self.assertEqual(selected["pcie0-integrated.yml"][0]["id"],456)
        self.assertEqual(len(calls),2)
        self.assertTrue(all("/actions/workflows/" in u for u in calls))
        self.assertTrue(all("/actions/runs?" not in u for u in calls))

    def test_unmerged_pr_excluded_and_main_accepted_in_workflow_history(self):
        from unittest.mock import Mock
        fixture_runs=[{"id": 10, "path": ".github/workflows/ethernet-mvp.yml",
                       "head_branch": "unmerged-feature", "head_sha": "b"*40,
                       "event": "pull_request"},
                      {"id": 11, "path": ".github/workflows/ethernet-mvp.yml",
                       "head_branch": "main", "head_sha": SHA,
                       "event": "workflow_dispatch"}]
        client=Mock(repository="r987r/xezim-hello-world",
                    request=Mock(return_value={"workflow_runs":fixture_runs}))
        selected,notes=site.select_workflow_runs(
            client,{"ethernet-mvp.yml":{}},{},4)
        self.assertEqual([run["id"] for run in selected["ethernet-mvp.yml"]],[11])
        self.assertFalse(notes)

    def test_truncated_workflow_history_is_explicitly_reported(self):
        from unittest.mock import Mock
        rows=[{"id":n,"path":".github/workflows/new-protocol.yml",
               "head_branch":"unmerged", "head_sha":"b"*40,
               "event":"pull_request"} for n in range(100)]
        client=Mock(repository="r987r/xezim-hello-world",
                    request=Mock(return_value={"workflow_runs":rows}))
        selected,notes=site.select_workflow_runs(
            client,{"new-protocol.yml":{}},{},4,max_pages=2)
        self.assertEqual(selected["new-protocol.yml"],[])
        self.assertEqual(client.request.call_count,2)
        self.assertIn("truncated",notes[0])
    def test_protocol_link_index_tracks_arbitrary_vip_source_fields(self):
        report={'capture_complete':True,
                'sources':[
                    {'id':'pcie0.rx_req','protocol':'pcie','role':'target',
                     'clock_domain':'soc_single_clock',
                     'implementation':'upstream_pcieifframe'},
                    {'id':'ethernet0.mac.rx','protocol':'ethernet','role':'target',
                     'clock_domain':'rx_clk','implementation':'cocotbext_eth'},
                    {'id':'peripheral0.apb','protocol':'apb','role':'target',
                     'clock_domain':'pclk','implementation':'apb_vip'}],
                'records':[
                    {'source':'pcie0.rx_req','protocol':'pcie','kind':'transaction',
                     'operation':'mem_read','id':'02:3','start_ps':1000,
                     'end_ps':3000,'status':'complete',
                     'fields':{'tag':'0x3','header_hex':'0x123',
                               'address':'0x4000','length_dw':1}},
                    {'source':'ethernet0.mac.rx','protocol':'ethernet',
                     'kind':'transaction','operation':'frame_rx','id':5,
                     'start_ps':4000,'end_ps':9000,'status':'complete',
                     'fields':{'ether_type':'0x0800','frame_length':64}},
                    {'source':'peripheral0.apb','protocol':'apb',
                     'kind':'transaction','operation':'write','id':6,
                     'start_ps':10000,'end_ps':12000,'status':'complete',
                     'fields':{'register':'0x40','pslverr':False}}]}
        actual=site.protocol_link_catalog(report)
        self.assertEqual({s['protocol'] for s in actual['sources']},
                         {'pcie','ethernet','apb'})
        self.assertTrue(actual['capture_complete'])
        self.assertEqual(actual['sources'][0]['preview'][0]['fields']['header_hex'],
                         '0x123')
        self.assertEqual(actual['sources'][1]['preview'][0]['fields']['ether_type'],
                         '0x0800')
        self.assertEqual(actual['sources'][2]['preview'][0]['fields']['pslverr'],
                         False)

    def test_protocol_link_index_caps_previews_but_counts_every_record(self):
        report={'capture_complete':False,
                'sources':[{'id':'new0.axi5','protocol':'axi5',
                            'role':'initiator','clock_domain':'clk',
                            'implementation':'future_vip'}],
                'records':[{'source':'new0.axi5','protocol':'axi5',
                            'kind':'transaction','operation':'read',
                            'start_ps':n*1000,'end_ps':(n+1)*1000,
                            'status':'complete','fields':{'new_axi5_attr':n}}
                           for n in range(100)]}
        data=site.protocol_link_catalog(report,preview_per_source=4)
        self.assertEqual(data['sources'][0]['count'],100)
        self.assertEqual(data['sources'][0]['operations'],{'read':100})
        self.assertEqual(len(data['sources'][0]['preview']),4)
        self.assertFalse(data['capture_complete'])

    def test_complete_offline_site_links_are_relative_and_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'site';dataset=site.build(output,Path(tmp)/'empty','r987r/xezim-hello-world',SHA,CONFIG)
            self.assertEqual(set(dataset['tests']), set(
                yaml.safe_load((ROOT/'config/regression.yaml').read_text())['tests']))
            self.assertIn('dma-rtl',dataset['tests'])
            self.assertIn('chip-dma',dataset['tests'])
            self.assertTrue((output/'fabric.html').is_file())
            self.assertTrue((output/'address-map.html').is_file())
            addr=json.loads((output/'data/soc-address-map.json').read_text())
            self.assertEqual(addr['schema_version'],1)
            self.assertEqual(len(addr['regions']),14)
            self.assertEqual(sum(r['plane']=='data' for r in addr['regions']),8)
            self.assertEqual(sum(r['plane']=='config' for r in addr['regions']),6)
            region={r['name']:r for r in addr['regions']}
            self.assertEqual(len(region['compute0.dma']['source_registers']),4)
            self.assertEqual(len(region['compute1.dma']['source_registers']),4)
            self.assertGreaterEqual(len(region['ethernet0.ctrl']['source_registers']),25)
            self.assertEqual(region['ethernet0.ctrl']['registers'],[])
            self.assertEqual(region['pcie0.ctrl']['source_registers'],[])
            coverage=json.loads((output/'data/csr-source-coverage.json').read_text())
            self.assertFalse(coverage['unacknowledged'])
            self.assertIn('pcie0.ctrl',{g['instance'] for g in coverage['gaps']})
            self.assertEqual(addr['config_sha256'],
                hashlib.sha256((ROOT/'config/soc.yaml').read_bytes()).hexdigest())
            self.assertEqual(next(r for r in addr['regions']
                if r['name']=='memory0.ddr0')['modeled_capacity_bytes'],65536)
            self.assertIn('external mem',(output/'data/soc-data-memories.rdl').read_text())
            map_html=(output/'address-map.html').read_text()
            self.assertIn('id="address-map-data"',map_html)
            self.assertIn('id="ddr-csr-variants-data"',map_html)
            self.assertIn('id="am-variant"',map_html)
            self.assertEqual(json.loads((output/'data/ddr-csr-verified-runs.json').read_text()),[])
            self.assertNotIn('__DDR_CSR_VARIANTS__',map_html)
            self.assertIn('register definitions are not RTL test coverage',map_html)
            self.assertNotIn('__ADDRESS_MAP_DATA__',map_html)
            overview=(output/'index.html').read_text()
            self.assertIn('Targets with recorded evidence',overview)
            self.assertIn('Latest archived PASS targets',overview)
            self.assertIn('Latest target results at exact site SHA',overview)
            self.assertNotIn('Passing recorded test reports',overview)
            test_runs=(output/'runs.html').read_text()
            self.assertIn('Exact tested/site SHA',test_runs)
            self.assertIn('Verified same Git tree',test_runs)
            self.assertIn('Fabric inputs equivalent only',test_runs)
            self.assertIn('Historical tested SHA',test_runs)
            self.assertIn('recorded flow steps',test_runs)
            self.assertNotIn('through eight connected FlooNoC meshes',(output/'index.html').read_text())
            self.assertIn('peripheral-attachment-status',(output/'topology.html').read_text())
            self.assertIn('Unmeasured',(output/'fabric.html').read_text())
            self.assertIn('href="address-map.html"',(output/'index.html').read_text())
            self.assertIn('href="address-map.html"',(output/'reference.html').read_text())
            self.assertTrue((output/'data/fabric.json').is_file())
            expected_networks=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())['networks']
            self.assertEqual(json.loads((output/'data/fabric.json').read_text())['summary']['meshes'],len(expected_networks))
            self.assertNotIn('__FABRIC_DATA__',(output/'fabric.html').read_text())
            self.assertNotIn('__PROTOCOL_LINK_DATA__',(output/'explorer.html').read_text())
            self.assertIn('id="arch-embedded-protocol-links"',(output/'explorer.html').read_text())
            self.assertIn('id="ex-embedded-rtl-bindings"',(output/'explorer.html').read_text())
            self.assertNotIn('__RTL_INSTANCE_BINDINGS__',(output/'explorer.html').read_text())
            bindings=json.loads((output/'data/rtl-instance-bindings.json').read_text())
            self.assertIn('compute0.cpu', bindings)
            self.assertIn(bindings['compute0.cpu']['status'],
                          {'compiler_parse_unavailable','unique_root_instance'})
            self.assertIn('ethernet0.ip',bindings)
            self.assertNotIn('const preferred={',(output/'explorer.html').read_text())
            fabric=json.loads((output/'data/fabric.json').read_text())
            self.assertEqual(fabric['latency_table']['units'],
                             'simulation_reference_clock_cycles')
            self.assertEqual(fabric['latency_table']['stat_order'],['min','avg','max'])
            self.assertEqual(fabric['latency_table']['reference_clock']['signal'],'clk_i')
            self.assertEqual(fabric['latency_table']['reference_clock']['domain'],'soc_single_clock')
            self.assertIsNone(fabric['latency_table']['reference_clock']['measured_period_ps'])
            self.assertIsNone(fabric['latency_table']['reference_clock']['hardware_frequency_hz'])
            self.assertEqual(len(fabric['latency_table']['rows']),len(fabric['matrix']))
            html=(output/'fabric.html').read_text()
            self.assertIn('id="fabric-latency-table"',html)
            self.assertIn('id="fabric-reference-clock"',html)
            self.assertIn('function renderLatencyTable()',html)
            self.assertIn('function renderMobileRoutes()',html)
            self.assertIn('function mobileMetric(',html)
            self.assertIn('function renderRoute()',html)
            self.assertIn('id="fabric-mobile-view"',html)
            self.assertIn('id="fabric-mobile-routes"',html)
            self.assertIn('id="fabric-show-unreachable"',html)
            self.assertIn('id="fabric-mobile-count"',html)
            self.assertIn('@media(max-width:820px)',html)
            self.assertIn('#fabric-wide-view,.fabric-desktop-explainer{display:none}',html)
            self.assertIn('expandedMobileRoutes',html)
            self.assertIn("r.access==='RW'",html)
            self.assertIn('Open router path and CI evidence',html)
            self.assertIn('fabric-detail-table',html)
            self.assertIn("dataset.label='Request cycles'",html)
            self.assertIn('Target read',html)
            self.assertIn('Target write',html)
            self.assertNotIn('id="fabric-matrix"',html)
            self.assertNotIn('renderMatrix()',html)
            self.assertFalse(dataset['entries'])
            real_monitors=json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())['monitors']
            self.assertEqual(len(dataset['monitors']),len(real_monitors))
            for path in output.rglob('*.html'):
                parser=Links();parser.feed(path.read_text())
                for href in parser.links:
                    url=urlsplit(href)
                    if url.scheme or url.netloc or not url.path:continue
                    self.assertFalse(url.path.startswith('/'),(path,href))
                    target=(path.parent/unquote(url.path)).resolve()
                    self.assertTrue(target.is_relative_to(output),(path,href))
                    self.assertTrue(target.exists(),(path,href))
            self.assertNotIn('__HOME__',(output/'index.html').read_text())
            self.assertIn('href="../index.html"',(output/'docs/full-chip-boot.html').read_text())

    def test_failed_and_negative_results_preserve_provenance_and_raw_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fixture(root/'evidence',passed=False,flattened=True)
            output=root/'site';output.mkdir()
            runs,entries,_=site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            self.assertEqual(entries[0]['source_sha'],SHA)
            self.assertFalse(entries[0]['passed'])
            self.assertEqual(entries[0]['expected_failure'],'required mismatch')
            self.assertEqual(runs[0]['conclusion'],'failure')
            report=output/entries[0]['path']
            self.assertIn('Regression FAIL',report.read_text())
            self.assertIn('href="../../../index.html"',report.read_text())
            self.assertIn('results.xml',entries[0]['assets'])
            self.assertEqual((report.parent/'simulation.log').read_text(),'actual simulator transcript')

    def test_archived_canonical_identity_uses_primary_current_run_path(self):
        from test_identity import selected, relative_path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence')
            # A *selected original run*, not reconstructed from newer catalog.
            plan={'engine':'cocotb-verilator','sources':'noc',
                  'top':'full_chip_tb','logical_test':'multicore-cold-boot',
                  'stage':'all'}
            identity=selected('chip-boot',plan, filelist=target/'sources.f',
                run_id='ci-123-a1-012345abcdef')
            plan['identity']=identity
            site.dump(target/'plan.json',plan)
            site.dump(target/'identity.json',identity)
            site.dump(target/'result.json',{
                'target':'chip-boot','passed':True,'stage':'all',
                'identity_sha256':identity['identity_sha256'],
                'canonical_id':relative_path(identity).as_posix()})
            output=root/'site';output.mkdir()
            _,entries,_=site.evidence_index(root/'evidence',output,
                                               'r987r/xezim-hello-world')
            e=entries[0]
            self.assertEqual(e['identity_status'],'source_verified')
            self.assertEqual(e['testname'],'multicore-cold-boot')
            self.assertEqual(e['config_target'],'soc-default')
            canonical_root=output/'runs'/relative_path(identity)
            self.assertEqual(e['path'],(Path('runs')/relative_path(identity)/'report.html').as_posix())
            self.assertEqual(e['canonical_url'],e['path'])
            self.assertTrue((canonical_root/'report.html').is_file())
            self.assertIn('Immutable identity',(canonical_root/'report.html').read_text())
            self.assertTrue((canonical_root/'identity.json').is_file())
            self.assertFalse((output/'runs/123-1/chip-boot').exists())
            self.assertFalse((output/'by-test').exists())
            original=(target/'sources.f').read_bytes()
            (target/'sources.f').write_bytes(b'foreign selected RTL filelist')
            with self.assertRaisesRegex(ValueError,'original archived source filelist'):
                site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            (target/'sources.f').write_bytes(original)
            identity['testname']='corrupt-name'
            site.dump(target/'identity.json',identity)
            with self.assertRaisesRegex(ValueError,'digest mismatch'):
                site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')

    def test_ci_attempt_identity_cannot_be_published_under_other_run(self):
        from test_identity import selected,relative_path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence')
            plan={'engine':'cocotb-verilator','sources':'noc',
                  'top':'full_chip_tb','logical_test':'multicore-cold-boot'}
            identity=selected('chip-boot',plan,run_id='ci-98765-a2-012345abcdef')
            plan['identity']=identity
            site.dump(target/'plan.json',plan)
            site.dump(target/'identity.json',identity)
            site.dump(target/'result.json',{'target':'chip-boot','passed':True,
                'identity_sha256':identity['identity_sha256'],
                'canonical_id':relative_path(identity).as_posix()})
            output=root/'site';output.mkdir()
            with self.assertRaisesRegex(ValueError,'different CI attempt'):
                site.evidence_index(root/'evidence',output,
                                    'r987r/xezim-hello-world')

    def test_archived_plan_survives_history_without_current_scenario(self):
        from tools.test_intent import snapshot as capture_plan
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence',axi=True)
            archived={'engine':'cocotb-verilator','top':'full_chip_tb',
                      'args':['+RUN_SEED=31'],'firmware_mode':'legacy'}
            site.dump(target/'plan.json',archived)
            original=capture_plan('chip-boot',archived)
            site.dump(target/'planned-flow.json',original)
            output=root/'site';output.mkdir()
            _,entries,_=site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            self.assertEqual(entries[0]['planned_flow_sha256'],original['plan_sha256'])
            self.assertEqual(entries[0]['planned_flow_intent'],original['intent'])
            self.assertEqual(entries[0]['planned_flow_status'],'captured_before_simulation')
            path=output/'runs/123-1/chip-boot'
            self.assertEqual(json.loads((path/'test-intent.json').read_text())['selected_args'],
                             ['+RUN_SEED=31'])
            self.assertIn('Archived pre-run plan',(path/'report.html').read_text())

    def test_tampered_archived_plan_rejected_on_publish(self):
        from tools.test_intent import snapshot as capture_plan
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence')
            old=capture_plan('chip-boot',{'engine':'xezim','args':['--max-time','10us']})
            old['intent']['selected_args'].append('--dangerous')
            site.dump(target/'planned-flow.json',old)
            output=root/'site';output.mkdir()
            with self.assertRaisesRegex(ValueError,'digest mismatch'):
                site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')

    def test_historical_axi_is_rendered_without_rewriting_original_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence',axi=True)
            before=(target/'axi-transactions.json').read_bytes()
            output=root/'site';output.mkdir()
            _,entries,_=site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            self.assertFalse(entries[0]['annotations'])
            report=output/entries[0]['path']
            self.assertEqual((report.parent/'axi-transactions.json').read_bytes(),before)
            self.assertIn('All runs',report.read_text())

    def test_archived_selected_plan_and_actual_runner_dispatch_provenance(self):
        from runtime_contract import digest, dispatch_event
        from test_intent import plan as intended
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence',axi=True)
            test=json.loads((target/'plan.json').read_text())
            test['stage']='all'
            site.dump(target/'plan.json',test)
            snapshot={'schema_version':1,'target':'chip-boot','source_revision':SHA,
                      'stage':'all','engine':'cocotb-verilator',
                      'adapter':'legacy_entrypoint_adapter',
                      'migration_owner_issue':119,
                      'adapter_scope':'legacy_internal_stimulus_opaque',
                      'selected_firmware_mode':None,'seed':None,
                      'command_argv':[{'label':'chip-boot','argv':['sim','-f','source.f']}],
                      'scenario_plan_sha256':None,'intent':intended('chip-boot',test),
                      'evidence_kind':'selected_definition_not_runtime_execution'}
            snapshot['plan_sha256']=digest(snapshot)
            site.dump(target/'selected-test-plan.json',snapshot)
            events=[
                dispatch_event(snapshot,'chip-boot',status='started'),
                dispatch_event(snapshot,'chip-boot',status='completed',
                               duration_s=1.0,passed=True,reason='PASS marker observed')]
            site.dump(target/'runner-events.json',
                      {'schema_version':1,'target':'chip-boot',
                       'plan_sha256':snapshot['plan_sha256'],'events':events})
            output=root/'site';output.mkdir()
            _,entries,_=site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            self.assertEqual(entries[0]['selected_plan_sha256'],snapshot['plan_sha256'])
            self.assertEqual(entries[0]['runtime_adapter'],'legacy_entrypoint_adapter')
            html=(output/entries[0]['path']).read_text()
            self.assertIn('Selected per-run snapshot',html)
            self.assertIn('internal steps independently instrumented only where available',html)
            self.assertTrue((output/'runs/123-1/chip-boot/selected-test-plan.json').is_file())
            # A second publication into an already populated destination
            # must fail closed instead of silently overwriting one run.
            with self.assertRaisesRegex(ValueError,'duplicate published canonical run or historical evidence path'):
                site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            corrupt=dict(snapshot);corrupt['source_revision']='b'*40
            site.dump(target/'selected-test-plan.json',corrupt)
            # Re-run the provenance-negative against a FRESH publication
            # destination: an existing report must not mask the real
            # selected-plan digest mismatch.
            fresh=root/'site-corrupt';fresh.mkdir()
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                site.evidence_index(root/'evidence',fresh,'r987r/xezim-hello-world')

    def test_protocol_report_is_provenance_verified_and_html_re_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence',axi=True)
            report={
                'schema_version':1,
                'run':{'commit':SHA,'dirty':False,
                       'workflow_run_id':'123','workflow_attempt':'1',
                       'target':'chip-boot'},
                'sources':[{'id':'cpu','protocol':'axi4','role':'initiator',
                            'clock_domain':'soc_single_clock'}],
                'records':[{'kind':'event','source':'cpu','protocol':'axi4',
                            'operation':'read','id':'0x0',
                            'start_ps':100,'end_ps':200,'status':'observed',
                            'fields':{'note':'<img src=x onerror=alert(1)>'}}],
                'capture_complete':True,'issues':[]
            }
            site.dump(target/'protocol-transactions.json',report)
            (target/'protocols.html').write_text('<script>alert("injected")</script>')
            output=root/'site';output.mkdir()
            _,entries,_=site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            self.assertEqual(entries[0]['protocols'],['axi4'])
            self.assertEqual(entries[0]['protocol_observations'],1)
            page=output/entries[0]['path']
            self.assertIn('All captured protocol traffic',page.read_text())
            self.assertIn('id="all-protocol-traffic"',page.read_text())
            self.assertIn('src="protocols.html"',page.read_text())
            self.assertIn('href="protocol-transactions.json"',page.read_text())
            generated=(page.parent/'protocols.html').read_text()
            self.assertIn('Protocol Run Explorer',generated)
            self.assertNotIn('<img src=x onerror=alert(1)>',generated)
            self.assertNotIn('<script>alert("injected")</script>',generated)
            self.assertIn('\\u003cimg',generated)

    def test_generic_only_report_keeps_provenance_and_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence')
            site.dump(target/'protocol-transactions.json',{
                'schema_version':1,
                'run':{'commit':SHA,'dirty':False,
                       'workflow_run_id':'123','workflow_attempt':'1'},
                'sources':[{'id':'mac.rx','protocol':'ethernet',
                            'clock_domain':'mac_rx','role':'target'}],
                'records':[{'kind':'event','source':'mac.rx',
                            'protocol':'ethernet','operation':'frame_rx',
                            'start_ps':1000,'end_ps':1000,
                            'status':'observed','fields':{'length':64}}],
                'capture_complete':True,'issues':[]})
            output=root/'site';output.mkdir()
            _,entries,_=site.evidence_index(root/'evidence',output,'r987r/xezim-hello-world')
            self.assertFalse(entries[0]['axi'])
            self.assertEqual(entries[0]['protocols'],['ethernet'])
            self.assertIn('Protocol Run Explorer',(output/entries[0]['path']).read_text())
            self.assertTrue((output/'runs/123-1/chip-boot/protocol-transactions.json').is_file())

    def test_verified_canonical_run_id_directory_publishes_without_target_alias(self):
        from test_identity import selected, relative_path
        import shutil

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=fixture(root/'evidence')
            plan=yaml.safe_load((ROOT/'config/regression.yaml').read_text())['tests']['chip-boot']
            identity=selected('chip-boot',plan,run_id='ci-123-a1-012345abcdef')
            canonical=original.parent/relative_path(identity)
            canonical.parent.mkdir(parents=True)
            shutil.move(str(original),str(canonical))
            self.assertFalse(original.exists())
            site.dump(canonical/'plan.json',{**plan,'identity':identity})
            site.dump(canonical/'identity.json',identity)
            site.dump(canonical/'result.json',{
                'target':'chip-boot','passed':True,'stage':'all',
                'identity_sha256':identity['identity_sha256'],
                'canonical_id':relative_path(identity).as_posix()})
            out=root/'published'
            out.mkdir()
            _,entries,_=site.evidence_index(root/'evidence',out,'r987r/xezim-hello-world')
            self.assertEqual(len(entries),1)
            self.assertEqual(entries[0]['canonical_id'],relative_path(identity).as_posix())
            self.assertTrue((out/'runs'/relative_path(identity)/'report.html').is_file())
            self.assertFalse((out/'runs/123-1/chip-boot').exists())

            # A forged canonical-looking folder, even with valid source data,
            # cannot be mistaken for the originally reserved run workspace.
            swapped=canonical.with_name('ci-123-a1-ffffffffffff')
            canonical.rename(swapped)
            with self.assertRaisesRegex(ValueError,'invalid target in CI result artifact'):
                site.evidence_index(root/'evidence',root/'rejected',
                                    'r987r/xezim-hello-world')

    def test_missing_claimed_identity_is_never_silent_legacy_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence')
            run={'id':123,'head_sha':SHA,'run_attempt':1}
            result=json.loads((target/'result.json').read_text())
            result['identity_sha256']='f'*64
            site.dump(target/'result.json',result)
            self.assertIn('archived run identity source missing',
                          site.invalid_artifact_identity_provenance(
                              target.parent,run))
            with self.assertRaisesRegex(ValueError,'archived run identity source missing'):
                site.evidence_index(root/'evidence',root/'out',
                                    'r987r/xezim-hello-world')
            # The missing immutable source may not be reconstructed as a
            # "legacy" or source-measured result, even when run PASS is true.
            result.pop('identity_sha256')
            site.dump(target/'result.json',result)
            self.assertIsNone(site.invalid_artifact_identity_provenance(
                target.parent,run))
            result['canonical_id']='soc-default/chip-boot'
            site.dump(target/'result.json',result)
            self.assertIn('archived run identity source missing',
                          site.invalid_artifact_identity_provenance(target.parent,run))

    def test_collector_quarantines_incomplete_identity_but_retains_good_run(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def zipped(result):
                buffer=io.BytesIO()
                with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
                    z.writestr('chip-boot/result.json',json.dumps(result))
                    z.writestr('chip-boot/plan.json',json.dumps({'engine':'cocotb-verilator'}))
                return buffer.getvalue()
            bad=zipped({'target':'chip-boot','passed':True,
                        'identity_sha256':'f'*64})
            good=zipped({'target':'chip-boot','passed':True})
            artifacts=[
                {'id':10,'name':'ci-123-bad','size_in_bytes':len(bad),'expired':False},
                {'id':11,'name':'ci-123-good','size_in_bytes':len(good),'expired':False}]
            run={'id':123,'head_sha':SHA,'head_branch':'main',
                 'event':'workflow_dispatch','run_attempt':1,
                 'name':'Chip boot','path':'.github/workflows/full-chip.yml',
                 'status':'completed','conclusion':'success',
                 'created_at':'2026-11-04T00:00:00Z',
                 'updated_at':'2026-11-04T00:01:00Z',
                 'html_url':'https://github.com/r987r/xezim-hello-world/actions/runs/123'}
            def request(path,binary=False):
                if path.endswith('/artifacts?per_page=100'):
                    return {'artifacts':artifacts}
                if path.endswith('/artifacts/10/zip'):
                    return bad
                if path.endswith('/artifacts/11/zip'):
                    return good
                raise AssertionError('unexpected network request: '+path)
            client=Mock(repository='r987r/xezim-hello-world',
                        request=Mock(side_effect=request))
            workflows={'full-chip.yml':{'file':'full-chip.yml',
                                       'label':'Chip boot',
                                       'artifacts':['ci-${{ github.run_id }}']}}
            with patch.object(site,'discover_test_workflows',return_value=workflows), \
                 patch.object(site,'merged_main_pr_heads',return_value={}), \
                 patch.object(site,'select_workflow_runs',
                              return_value=({'full-chip.yml':[run]},[])), \
                 patch.object(site.subprocess,'check_output',return_value=(SHA+'\n').encode()):
                site.collect(client,CONFIG,root/'evidence')
            notes=json.loads((root/'evidence/collection.json').read_text())['notes']
            self.assertEqual(len(notes),1)
            self.assertIn('excluded unverified identity',notes[0])
            self.assertIn('archived run identity source missing',notes[0])
            self.assertFalse((root/'evidence/123-1/artifact-10').exists())
            self.assertTrue((root/'evidence/123-1/artifact-11/chip-boot/result.json').exists())
            out=root/'site'
            out.mkdir()
            _,entries,index_notes=site.evidence_index(root/'evidence',out,
                                                       'r987r/xezim-hello-world')
            self.assertEqual(len(entries),1)
            self.assertEqual(entries[0]['target'],'chip-boot')
            self.assertTrue(entries[0]['passed'])
            self.assertIn('excluded unverified identity',index_notes[0])

    def test_quarantine_wrong_historical_provenance_keeps_other_artifacts(self):
        run={'id':123,'head_sha':SHA,'run_attempt':2}
        def record(commit=SHA,workflow_id=123,attempt=2,dirty=False):
            return {'schema_version':1,'run':{
                'commit':commit,'workflow_run_id':workflow_id,
                'workflow_attempt':attempt,'dirty':dirty},
                'records':[]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            bad=root/'bad';good=root/'good'
            bad.mkdir();good.mkdir()
            site.dump(bad/'protocol-transactions.json',record(workflow_id=999))
            site.dump(good/'protocol-transactions.json',record())
            self.assertIn('workflow_run_id mismatch',
                site.invalid_artifact_trace_provenance(bad,run))
            self.assertIsNone(site.invalid_artifact_trace_provenance(good,run))
            site.dump(bad/'protocol-transactions.json',record(commit='b'*40))
            self.assertIn('tested SHA mismatch',
                site.invalid_artifact_trace_provenance(bad,run))
            site.dump(bad/'protocol-transactions.json',record(attempt=1))
            self.assertIn('workflow_attempt mismatch',
                site.invalid_artifact_trace_provenance(bad,run))
            site.dump(bad/'protocol-transactions.json',record(dirty=True))
            self.assertIn('dirty/missing',
                site.invalid_artifact_trace_provenance(bad,run))
            site.dump(bad/'protocol-transactions.json',record())
            site.dump(bad/'axi-transactions.json',record(workflow_id=321))
            self.assertIn('workflow_run_id mismatch',
                site.invalid_artifact_trace_provenance(bad,run))
            self.assertIsNone(site.invalid_artifact_trace_provenance(good,run))
            self.assertTrue((good/'protocol-transactions.json').exists())

    def test_quarantine_accepts_only_attested_pr_tested_shas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            root.joinpath('protocol-transactions.json').write_text(json.dumps({
                'schema_version':1,'run':{'commit':'c'*40,'dirty':False,
                 'workflow_run_id':777,'workflow_attempt':1},'records':[]}))
            run={'id':777,'head_sha':SHA,'run_attempt':1,
                 'verified_tested_shas':['c'*40]}
            self.assertIsNone(site.invalid_artifact_trace_provenance(root,run))
            run['verified_tested_shas']=[]
            self.assertIn('tested SHA mismatch',
                site.invalid_artifact_trace_provenance(root,run))

    def test_generic_report_wrong_ci_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence')
            site.dump(target/'protocol-transactions.json',{
                'schema_version':1,
                'run':{'commit':'b'*40,'dirty':False,'workflow_run_id':'123',
                       'workflow_attempt':'1'},
                'sources':[],'records':[],'capture_complete':True,'issues':[]})
            with self.assertRaisesRegex(ValueError,'protocol report provenance'):
                site.evidence_index(root/'evidence',root/'out','r987r/xezim-hello-world')

    def test_mismatched_axi_commit_or_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=fixture(root/'evidence',axi=True)
            data=json.loads((target/'axi-transactions.json').read_text());data['run']['commit']='b'*40
            site.dump(target/'axi-transactions.json',data)
            with self.assertRaisesRegex(ValueError,'provenance'):
                site.evidence_index(root/'evidence',root/'out','r987r/xezim-hello-world')

    def test_archive_selective_evidence_retains_pcie_result_without_build_products(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("pcie0/full_chip_build/huge.bin","X"*2000000)
                archive.writestr("regression/chip-pcie-host/result.json",
                                 '{"target":"chip-pcie-host","passed":true}')
                archive.writestr("regression/chip-pcie-host/plan.json",
                                 '{"engine":"cocotb-verilator"}')
                archive.writestr("regression/chip-pcie-host/protocol-transactions.json",
                                 '{"schema_version":1,"run":{},"records":[]}')
                archive.writestr("regression/chip-pcie-host/axi-transactions.json",
                                 '{"schema_version":2,"run":{}}')
                archive.writestr("regression/chip-pcie-host/simulation.log","observed link")
                archive.writestr("regression/chip-pcie-host/report.html",
                                 "<script>untrusted()</script>")
            payload=buf.getvalue()
            cfg={**CONFIG,"max_expanded_mib":1}
            digest="sha256:"+hashlib.sha256(payload).hexdigest()
            site.extract_archive(payload,Path(tmp),cfg,digest,evidence_only=True)
            folder=Path(tmp)/"regression/chip-pcie-host"
            self.assertEqual(json.loads((folder/"result.json").read_text())["target"],
                             "chip-pcie-host")
            self.assertTrue((folder/"protocol-transactions.json").is_file())
            self.assertTrue((folder/"axi-transactions.json").is_file())
            self.assertTrue((folder/"simulation.log").is_file())
            self.assertFalse((folder/"report.html").exists())
            self.assertFalse((Path(tmp)/"pcie0/full_chip_build/huge.bin").exists())

    def test_selective_evidence_rejects_oversized_selected_file_and_bad_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w") as archive:
                archive.writestr("regression/chip-pcie-host/axi-transactions.json",
                                 "Y"*(2*1024*1024))
            with self.assertRaisesRegex(ValueError,"expanded CI archive"):
                site.extract_archive(buf.getvalue(),Path(tmp),
                                     {**CONFIG,"max_expanded_mib":1},evidence_only=True)
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w") as archive:
                archive.writestr("../pcie0/full_chip_build/not-evidence.o","X")
            with self.assertRaisesRegex(ValueError,"unsafe"):
                site.extract_archive(buf.getvalue(),Path(tmp),
                                     CONFIG,evidence_only=True)

    def test_pcie_compact_ci_artifact_and_suite_navigation_present(self):
        workflow=(ROOT/".github/workflows/pcie0-integrated.yml").read_text()
        # Workflow artifact paths may be a multiline YAML scalar; validate the\n        # selected artifact value rather than requiring a specific indentation.\n        parsed=yaml.safe_load(workflow)\n        artifact_paths=[str(step.get("with",{}).get("path",""))\n                        for job in parsed["jobs"].values()\n                        for step in job.get("steps",[])\n                        if step.get("uses","").startswith("actions/upload-artifact@")]\n        self.assertTrue(any(".tools/regression/chip-pcie-host/" in path\n                            for path in artifact_paths),\n                        "PCIe CI must preserve the host regression evidence")
        self.assertNotIn("            .tools/pcie0/full_chip_build/",workflow)
        self.assertGreaterEqual(CONFIG["max_archive_mib"],130)
        site_html=(ROOT/"tools/templates/site_runs.html").read_text()
        self.assertIn('id="suite-summary"',site_html)
        self.assertIn('id="family"',site_html)
        self.assertIn('No recorded result',site_html)
        self.assertIn('const key=identityKey+"|"+e.workflow',site_html)
        self.assertIn('e.config_target',site_html)

    def test_archive_digest_and_traversal_are_checked(self):
        for name in ('../escape','/absolute','dir/../../escape','dir\\escape'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                memory=io.BytesIO()
                with zipfile.ZipFile(memory,'w') as z:z.writestr(name,'x')
                with self.assertRaisesRegex(ValueError,'unsafe'):
                    site.extract_archive(memory.getvalue(),Path(tmp),CONFIG)
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as z:z.writestr('result.json','{}')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'digest'):
                site.extract_archive(memory.getvalue(),Path(tmp),CONFIG,'sha256:'+'0'*64)
            site.extract_archive(memory.getvalue(),Path(tmp),CONFIG,'sha256:'+hashlib.sha256(memory.getvalue()).hexdigest())
            self.assertTrue((Path(tmp)/'result.json').exists())

    def test_unowned_output_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'unowned'):
                site.build(Path(tmp),Path(tmp)/'empty','r987r/xezim-hello-world',SHA,CONFIG)


if __name__=='__main__':unittest.main()
