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
    def test_complete_offline_site_links_are_relative_and_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'site';dataset=site.build(output,Path(tmp)/'empty','r987r/xezim-hello-world',SHA,CONFIG)
            self.assertEqual(len(dataset['tests']),18)
            self.assertTrue((output/'fabric.html').is_file())
            self.assertTrue((output/'data/fabric.json').is_file())
            self.assertEqual(json.loads((output/'data/fabric.json').read_text())['summary']['meshes'],8)
            self.assertNotIn('__FABRIC_DATA__',(output/'fabric.html').read_text())
            self.assertFalse(dataset['entries'])
            self.assertEqual(len(dataset['monitors']),26)
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
