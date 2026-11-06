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
            self.assertEqual(addr['config_sha256'],
                hashlib.sha256((ROOT/'config/soc.yaml').read_bytes()).hexdigest())
            self.assertEqual(next(r for r in addr['regions']
                if r['name']=='memory0.ddr0')['modeled_capacity_bytes'],65536)
            self.assertIn('external mem',(output/'data/soc-data-memories.rdl').read_text())
            map_html=(output/'address-map.html').read_text()
            self.assertIn('id="address-map-data"',map_html)
            self.assertIn('register definitions are not RTL test coverage',map_html)
            self.assertNotIn('__ADDRESS_MAP_DATA__',map_html)
            self.assertIn('href="address-map.html"',(output/'index.html').read_text())
            self.assertIn('href="address-map.html"',(output/'reference.html').read_text())
            self.assertTrue((output/'data/fabric.json').is_file())
            expected_networks=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())['networks']
            self.assertEqual(json.loads((output/'data/fabric.json').read_text())['summary']['meshes'],len(expected_networks))
            self.assertNotIn('__FABRIC_DATA__',(output/'fabric.html').read_text())
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
            self.assertIn('Unified protocol explorer',page.read_text())
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
