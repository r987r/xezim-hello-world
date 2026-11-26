"""Evidence provenance, safe extraction and project-subpath publication."""
import hashlib
from html.parser import HTMLParser
import io
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
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
    def test_connected_checker_requires_final_dedicated_job_and_exact_attempt(self):
        from copy import deepcopy
        c=site.connected
        run=dict(id=123,run_attempt=2,head_sha=SHA,status='completed',conclusion='success')
        good=dict(id=7,name=c.JOB,run_id=123,run_attempt=2,head_sha=SHA,
                  status='completed',conclusion='success',
                  steps=[dict(name=name,status='completed',conclusion='success') for name in c.STEPS])
        self.assertEqual(c.require_job(run,[good]),7)
        for bad in (dict(good,conclusion='failure'),dict(good,run_attempt=1)):
            with self.assertRaises(ValueError):
                c.require_job(run,[bad])
        bad=deepcopy(good)
        bad['steps'][1]['conclusion']='failure'
        with self.assertRaises(ValueError):
            c.require_job(run,[bad])
        base='verilator/pcie-connected-memory-default/host-to-sram-roundtrip/'
        self.assertTrue(c.matches_run(base+'ci-123-a2-e6075aea7be1',run))
        self.assertFalse(c.matches_run(base+'ci-123-a1-e6075aea7be1',run))

    def test_connected_entry_is_filtered_out_of_every_chip_project(self):
        c=site.connected
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            folder=root/'run'; out=root/'site'
            artifact=folder/'connected-artifact-42'
            run=dict(id=123,run_attempt=1,head_sha=SHA,conclusion='success',
                     html_url='https://github.com/example/project/actions/runs/123',
                     label='Isolated checker',created_at='2026-11-04T00:00:00Z')
            canonical='verilator/pcie-connected-memory-default/host-to-sram-roundtrip/ci-123-a1-e6075aea7be1'
            source=artifact/canonical
            source.mkdir(parents=True)
            for file in c.FILES:
                (source/file).write_text(file)
            record=dict(canonical_id=canonical,tested_sha=SHA,archive_digest='sha256:'+'a'*64,
                        job_id=7,artifact_id=42,sources=281,expires_at='2099-01-01T00:00:00+00:00',
                        files={f:c.digest((source/f).read_bytes()) for f in c.FILES})
            site.dump(artifact/'verified-connected.json',record)
            entries,notes=[],[]
            site.append_connected_entries(folder,run,out,entries,notes,'example/project',SHA)
            self.assertEqual(len(entries),1)
            self.assertFalse(notes)
            entry=entries[0]
            self.assertIsNone(entry['passed'])
            self.assertEqual(entry['protocols'],[])
            self.assertFalse(entry['axi'])
            self.assertEqual(site.project_entries(entries,'chip_a','chip_a'),[])
            self.assertEqual(site.project_entries(entries,'chip_b','chip_a'),[])
            self.assertIn('Not a full-chip regression',(out/entry['path']).read_text())
            for file in c.FILES:
                self.assertEqual((out/entry['path']).with_name(file).read_bytes(),(source/file).read_bytes())
            (source/'sources.f').write_text('tampered')
            site.append_connected_entries(folder,run,root/'other',entries,notes,'example/project',SHA)
            self.assertEqual(len(entries),1)
            self.assertIn('bytes no longer match',notes[-1])

    def test_ci_producer_discovery_includes_new_protocol_workflows(self):
        workflows=site.discover_test_workflows(ROOT)
        self.assertIn("ethernet-mvp.yml",workflows)
        self.assertIn("ethernet-standalone.yml",workflows)
        self.assertIn("pcie0-integrated.yml",workflows)
        self.assertIn("pcie-digital-link.yml",workflows)
        self.assertTrue(any("pcie-cross-provider-" in a
                            for a in workflows["pcie-digital-link.yml"]["artifacts"]))
        self.assertIn("full-chip.yml",workflows)
        self.assertIn("dma.yml", workflows)
        self.assertTrue(any(a.startswith("dma-canonical-verilator-")
                            for a in workflows["dma.yml"]["artifacts"]))
        self.assertNotIn(".tools/regression/dma-rtl/",
                         (ROOT/".github/workflows/dma.yml").read_text())
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

    def test_canonical_only_workflow_is_discovered_for_existing_pages_consumer(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)/".github/workflows"
            directory.mkdir(parents=True)
            (directory/"standalone-axi.yml").write_text(
                "name: Canonical-only Cocotb\njobs:\n  test:\n    steps:\n"
                "      - uses: actions/upload-artifact@v4\n"
                "        with:\n"
                "          name: original-verilator-${{ github.run_id }}\n"
                "          path: .tools/runs/verilator/\n")
            result = site.discover_test_workflows(Path(temp))
            self.assertEqual(result["standalone-axi.yml"]["artifacts"],
                             ["original-verilator-${{ github.run_id }}"])
            self.assertNotIn("legacy", str(result))

    def test_supernoc_migration_preserves_ci_archive_discovery(self):
        workflows = site.discover_test_workflows(ROOT)
        self.assertIn("supernoc-real-axi-traffic",
                      workflows["floonoc-elab.yml"]["artifacts"])
        self.assertTrue(any(a.startswith("supernoc-axi-run-reports-")
                            for a in workflows["floonoc-elab.yml"]["artifacts"]))
        self.assertTrue(any(a.startswith("fabric-latency-supernoc-")
                            for a in workflows["dv-fabric-latency.yml"]["artifacts"]))
        self.assertNotIn(".tools/regression/supernoc",
                         (ROOT/".github/workflows/floonoc-elab.yml").read_text())
        self.assertNotIn(".tools/regression/supernoc",
                         (ROOT/".github/workflows/dv-fabric-latency.yml").read_text())

    def test_any_future_protocol_capture_artifact_is_discovered(self):
        # No protocol or controller-name registration is needed.
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/".github/workflows"
            directory.mkdir(parents=True)
            (directory/"new-ip.yml").write_text(
                "name: New abstract monitor\njobs:\n  smoke:\n    steps:\n"
                "      - run: python3 -m unittest tests.test_protocol_report\n"
                "      - uses: actions/upload-artifact@v4\n"
                "        with:\n"
                "          name: monitor-" + "$" + "{{ github.run_id }}\n"
                "          path: .tools/device/observations/protocol-transactions.json\n")
            discovery=site.discover_test_workflows(Path(temp))
            self.assertEqual(discovery["new-ip.yml"]["artifacts"],
                             ["monitor-"+"$"+"{{ github.run_id }}"])

    def test_capture_only_publisher_accepts_any_protocol_never_forges_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            evidence=root/"evidence"
            fixture(evidence)
            for i,proto in enumerate(("pcie","dfi","ethernet"),101):
                data={
                    "schema_version":1,"capture_complete":True,"issues":[],
                    "run":{"commit":SHA,"dirty":False,"workflow_run_id":"123",
                           "workflow_attempt":"1","target":f"{proto}-real-link",
                           "engine":"cocotb-verilator"},
                    "sources":[{"id":f"device.{proto}","protocol":proto,
                                "clock_domain":"device","role":"link",
                                "implementation":"source_observed_testbench"}],
                    "records":[{"kind":"event","source":f"device.{proto}",
                                "protocol":proto,"operation":"pin_transition",
                                "start_ps":150,"end_ps":150,"status":"observed",
                                "id":None,"fields":{"register_index":5}}],
                }
                # Use a real Actions-style ZIP: selective extraction must
                # preserve versioned captures despite ignoring simulator builds.
                archive=io.BytesIO()
                with zipfile.ZipFile(archive,"w") as z:
                    z.writestr(f".tools/device/{proto}/protocol-transactions.json",
                               json.dumps(data))
                    z.writestr("obj_dir/huge-object.o","compiler output excluded")
                target=evidence/"123-1"/f"artifact-{i}"
                site.extract_archive(archive.getvalue(),target,CONFIG,
                                     evidence_only=True)
                self.assertFalse((target/"obj_dir/huge-object.o").exists())
            output=root/"site";output.mkdir()
            _,entries,notes=site.evidence_index(
                evidence,output,"r987r/xezim-hello-world")
            self.assertFalse(notes,notes)
            captures=[e for e in entries if e.get("evidence_only")]
            self.assertEqual(len(captures),3)
            self.assertEqual({e["protocols"][0] for e in captures},
                             {"pcie","dfi","ethernet"})
            self.assertTrue(all(e["passed"] is None and
                                e["evidence_scope"]=="isolated_observation_only"
                                for e in captures))
            for e in captures:
                self.assertNotIn("/.tools/",e["path"])
                self.assertRegex(e["path"],r"^runs/capture-only/123-1/artifact-[0-9]+/[a-z0-9-]+/report[.]html$")
                published=output/Path(e["path"]).parent
                self.assertTrue((published/"protocols.html").is_file())
                self.assertFalse((published/"result.json").exists())
                self.assertIn("NOT A FULL-CHIP REGRESSION PASS",
                              (published/"report.html").read_text())
                self.assertIn("pin_transition",
                              (published/"protocols.html").read_text())
                self.assertEqual(e["protocol_links"]["sources"][0]["count"],1)
            ui=(ROOT/"tools/templates/site_runs.html").read_text()
            self.assertIn('e.evidence_only?"OBSERVED"',ui)
            self.assertIn('e.evidence_only||(outcome==="pass")',ui)

    def test_canonical_capture_uses_original_identity_and_no_regression_pass(self):
        from test_identity import selected, relative_path

        for fault in (None, "filelist", "identity", "dirty", "foreign-source"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                evidence=root/"evidence"
                fixture(evidence)
                original=b"src/original_openpcie.sv\n"
                target="pcie-link-isolated"
                plan={"engine":"verilator","target":target,"sources":"pcie-link",
                      "logical_test":"link-training","top":"test",
                      "source_revision":SHA,"evidence_scope":"isolated_observation_only"}
                identity=selected(target,plan,root=ROOT,filelist_bytes=original,
                                  run_id="ci-123-a1-123456789abc")
                path=relative_path(identity)
                report={"schema_version":1,"capture_complete":True,"issues":[],
                        "run":{"commit":SHA,"dirty":fault=="dirty","workflow_run_id":"123",
                               "workflow_attempt":"1","target":target,"engine":"verilator"},
                        "sources":[{"id":"pcie.ltssm","protocol":"pcie","clock_domain":"pipe"}],
                        "records":[{"kind":"event","source":"pcie.ltssm","protocol":"pcie",
                                    "operation":"transition","start_ps":7,"end_ps":7,
                                    "status":"observed","id":None,"fields":{}}]}
                plan.update(identity=identity)
                if fault=="foreign-source":
                    plan["source_revision"]="b"*40
                archive=io.BytesIO()
                with zipfile.ZipFile(archive,"w") as z:
                    z.writestr(str(path/"plan.json"),json.dumps(plan))
                    z.writestr(str(path/"sources.f"),b"tampered" if fault=="filelist" else original)
                    z.writestr(str(path/"protocol-transactions.json"),json.dumps(report))
                    if fault!="identity":
                        z.writestr(str(path/"identity.json"),json.dumps(identity))
                site.extract_archive(archive.getvalue(),evidence/"123-1"/"artifact-101",
                                     CONFIG,evidence_only=True)
                output=root/"site"
                output.mkdir()
                _,entries,notes=site.evidence_index(evidence,output,"r987r/xezim-hello-world")
                captures=[e for e in entries if e.get("evidence_only")]
                if fault:
                    self.assertFalse(captures)
                    self.assertTrue(notes)
                    continue
                self.assertFalse(notes,notes)
                [capture]=captures
                self.assertEqual(capture["canonical_id"],path.as_posix())
                self.assertEqual(capture["path"],f"runs/{path}/report.html")
                self.assertIsNone(capture["passed"])
                directory=output/"runs"/path
                self.assertFalse((directory/"result.json").exists())
                self.assertEqual((directory/"sources.f").read_bytes(),original)
                self.assertEqual((directory/"protocol-transactions.json").read_text(),
                                 json.dumps(report))

    def test_capture_only_quarantines_unqualified_and_missing_monitor_evidence(self):
        for label in ("dirty","wrong_sha","wrong_attempt","invalid_source",
                      "incomplete","no_observations"):
            with self.subTest(label=label),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                fixture(root/"evidence")
                folder=root/"evidence"/"123-1"/"artifact-101"/"observations"
                folder.mkdir(parents=True)
                data={"schema_version":1,"capture_complete":True,"issues":[],
                      "run":{"target":"future-dfi","commit":SHA,"dirty":False,
                             "workflow_run_id":"123","workflow_attempt":"1"},
                      "sources":[{"id":"ddr.dfi","protocol":"dfi"}],
                      "records":[{"kind":"event","source":"ddr.dfi","protocol":"dfi",
                                  "operation":"mr_write","status":"observed",
                                  "start_ps":500,"end_ps":500,"id":None,
                                  "fields":{"mr_index":1}}]}
                if label=="dirty":data["run"]["dirty"]=True
                if label=="wrong_sha":data["run"]["commit"]="b"*40
                if label=="wrong_attempt":data["run"]["workflow_attempt"]="2"
                if label=="invalid_source":data["records"][0]["source"]="unknown"
                if label=="incomplete":data["capture_complete"]=False
                if label=="no_observations":data["records"]=[]
                site.dump(folder/"protocol-transactions.json",data)
                output=root/"site";output.mkdir()
                _,entries,notes=site.evidence_index(
                    root/"evidence",output,"r987r/xezim-hello-world")
                self.assertFalse(any(e.get("evidence_only") for e in entries))
                self.assertTrue(any("omitted unverified standalone" in note
                                    for note in notes))

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

    def test_workflow_history_deduplicates_pagination_without_consuming_a_history_slot(self):
        from unittest.mock import Mock
        name="full-chip.yml"
        run={"id":123,"run_attempt":1,"path":".github/workflows/"+name,
             "head_branch":"main","head_sha":SHA,"event":"workflow_dispatch"}
        duplicate=dict(run,updated_at="2026-11-22T22:22:22Z")
        next_run=dict(run,id=124)
        ignored=[dict(run,head_branch="unmerged",event="pull_request")]*99
        client=Mock(repository="r987r/xezim-hello-world",request=Mock(
            side_effect=[{"workflow_runs":[run,*ignored]},
                         {"workflow_runs":[duplicate,next_run]}]))
        selected,notes=site.select_workflow_runs(client,{name:{}},{},2)
        self.assertEqual(selected[name],[run,next_run])
        self.assertFalse(notes)
        self.assertEqual(client.request.call_count,2)

        # Different attempts from successive pages cannot share a snapshot.
        client.request=Mock(return_value={"workflow_runs":[run,dict(run,run_attempt=2)]})
        with self.assertRaisesRegex(ValueError,'conflicting duplicate Actions run identity'):
            site.select_workflow_runs(client,{name:{}},{},2)

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
    def test_combined_source_review_fails_closed_on_tampered_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'config').mkdir()
            shutil.copyfile(ROOT / 'config/soc.yaml', root / 'config/soc.yaml')
            self.assertEqual(site.combined_source_review(root, root), '')
            relative = Path('gen/projects/xezim_soc_dv/variants/ethernet-ddr-pcie')
            shutil.copytree(ROOT / relative, root / relative)
            (root / relative / 'rtl/soc_top.sv').write_text('module foreign; endmodule\n')
            with self.assertRaisesRegex(ValueError, 'generated file digest changed'):
                site.combined_source_review(root, root)

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
            self.assertEqual(set(dataset['test_names']),set(dataset['tests']))
            self.assertEqual(dataset['test_names']['chip-boot'],
                             'verilator/soc-default/multicore-cold-boot')
            self.assertEqual(dataset['test_names']['chip-ddr4-real'],
                             'verilator/soc-ddr-cpu-dma/dma-controller-readback')
            self.assertFalse(dataset['entries'],'a configured identity is not a run')
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
            pcie=region['pcie0.ctrl']
            self.assertEqual(pcie['registers'],[])
            self.assertEqual(len(pcie['source_registers']),22)
            pcie_regs={r['name']:r for r in pcie['source_registers']}
            self.assertEqual(pcie_regs['wr_command']['access'],'w')
            self.assertEqual(pcie_regs['rd_command']['access'],'w')
            self.assertEqual(pcie_regs['bar0_aperture']['address'],'0x40041000')
            self.assertEqual(pcie_regs['host_bar0']['fields'][0]['access'],'r')
            coverage=json.loads((output/'data/csr-source-coverage.json').read_text())
            self.assertFalse(coverage['unacknowledged'])
            self.assertNotIn('pcie0.ctrl',{g['instance'] for g in coverage['gaps']})
            self.assertEqual(next(r for r in coverage['instances']
                if r['instance']=='pcie0.ctrl')['source_only_registers'],22)
            self.assertEqual(addr['config_sha256'],
                hashlib.sha256((ROOT/'config/soc.yaml').read_bytes()).hexdigest())
            self.assertEqual(next(r for r in addr['regions']
                if r['name']=='memory0.ddr0')['modeled_capacity_bytes'],65536)
            self.assertIn('external mem',(output/'data/soc-data-memories.rdl').read_text())
            map_html=(output/'address-map.html').read_text()
            self.assertIn('id="address-map-data"',map_html)
            self.assertIn('id="ddr-csr-variants-data"',map_html)
            self.assertIn('id="am-variant"',map_html)
            self.assertIn('href="data/csr-source-coverage.json"',map_html)
            self.assertEqual(json.loads((output/'data/ddr-csr-verified-runs.json').read_text()),[])
            self.assertNotIn('__DDR_CSR_VARIANTS__',map_html)
            self.assertIn('configured decode windows and register definitions, not test results',map_html)
            self.assertNotIn('__ADDRESS_MAP_DATA__',map_html)
            overview=(output/'soc-overview.html').read_text()
            self.assertIn('Targets with recorded evidence',overview)
            self.assertIn('Retained PASS targets',overview)
            self.assertIn('Latest results on published SHA',overview)
            self.assertNotIn('Passing recorded test reports',overview)
            test_runs=(output/'runs.html').read_text()
            self.assertIn('Exact tested/site SHA',test_runs)
            self.assertIn('Verified same Git tree',test_runs)
            self.assertIn('Fabric inputs equivalent only',test_runs)
            self.assertIn('Historical tested SHA',test_runs)
            self.assertIn('recorded flow steps',test_runs)
            self.assertNotIn('through eight connected FlooNoC meshes',(output/'soc-overview.html').read_text())
            self.assertIn('peripheral-attachment-status',(output/'topology.html').read_text())
            self.assertIn('Unmeasured',(output/'fabric.html').read_text())
            self.assertIn('href="address-map.html"',(output/'soc-overview.html').read_text())
            self.assertIn('href="address-map.html"',(output/'reference.html').read_text())
            self.assertTrue((output/'data/fabric.json').is_file())
            expected_networks=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())['networks']
            self.assertEqual(json.loads((output/'data/fabric.json').read_text())['summary']['meshes'],len(expected_networks))
            self.assertNotIn('__FABRIC_DATA__',(output/'fabric.html').read_text())
            self.assertNotIn('__PROTOCOL_LINK_DATA__',(output/'explorer.html').read_text())
            self.assertIn('id="arch-embedded-protocol-links"',(output/'explorer.html').read_text())
            self.assertIn('id="ex-embedded-rtl-bindings"',(output/'explorer.html').read_text())
            self.assertNotIn('__RTL_INSTANCE_BINDINGS__',(output/'explorer.html').read_text())
            explorer = (output/'explorer.html').read_text()
            self.assertNotIn('__COMBINED_SOURCE_REVIEW__', explorer)
            self.assertIn('id="arch-combined-source"', explorer)
            self.assertIn('does not show elaborated connections or observed traffic', explorer)
            prefix = 'gen/projects/xezim_soc_dv/variants/'
            for rel in ('default/rtl/soc_top.sv', 'ethernet-ddr-pcie/rtl/soc_top.sv',
                        'ethernet-ddr-pcie/manifest.json', 'ethernet-ddr-pcie/compiler/sources.f'):
                self.assertIn(f'href="{prefix}{rel}"', explorer)
                self.assertEqual((output/(prefix+rel)).read_bytes(), (ROOT/(prefix+rel)).read_bytes())
            diff = (output/'data/default-vs-combined-top.diff').read_text()
            self.assertIn('not an elaborated or semantic diff', diff)
            self.assertIn('--- '+prefix+'default/rtl/soc_top.sv', diff)
            self.assertIn('+++ '+prefix+'ethernet-ddr-pcie/rtl/soc_top.sv', diff)
            self.assertIn('href="data/default-vs-combined-top.diff"', explorer)
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
            self.assertIn('AXI target read',html)
            self.assertIn('AXI target write',html)
            self.assertIn('not a DDR4 DRAM device',html)
            self.assertIn('PCIe host and Ethernet rows',html)
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

    def test_run_compiler_manifest_is_extracted_bound_to_attempt_and_linked(self):
        from runtime_contract import digest
        from run_workspace import reserve_run
        from selected_rtl_provenance import archive_selected_filelist
        from test_identity import relative_path, selected

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=fixture(root/'evidence')
            repo=root/'writer'
            repo.mkdir()
            top=repo/'gen/chip/soc_top.sv'
            top.parent.mkdir(parents=True)
            top.write_text('module soc_top; endmodule\n')
            raw=(str(top)+'\n').encode()
            profile='chip-boot'
            definition={'engine':'cocotb-verilator','sources':'noc',
                        'top':'full_chip_tb','logical_test':'multicore-cold-boot'}
            identity=selected(profile,definition,filelist_bytes=raw,
                              run_id='ci-123-a1-012345abcdef')
            run_dir=reserve_run(repo/'.tools/runs',identity)
            filelist=run_dir/'sources.f'
            filelist.write_bytes(raw)
            plan={**definition,'target':profile,'source_target':'noc','sources':[str(top)],
                  'includes':[],'defines':[],'identity':identity}
            site.dump(run_dir/'plan.json',plan)
            manifest=archive_selected_filelist(repo,profile,definition,plan,filelist,directory=run_dir)
            plan['selected_source_manifest']={
                'path':(run_dir/site.SELECTED_RTL_MANIFEST).relative_to(repo).as_posix(),
                'compiler_input_sha256':manifest['compiler_input_sha256']}
            site.dump(run_dir/'plan.json',plan)
            site.dump(run_dir/'result.json',{
                'target':profile,'passed':False,'stage':'run',
                'identity_sha256':identity['identity_sha256'],
                'canonical_id':relative_path(identity).as_posix()})
            for path in original.iterdir():
                path.unlink()
            original.rmdir()
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as zip_file:
                for name in ('plan.json','result.json','identity.json','sources.f',
                             site.SELECTED_RTL_MANIFEST):
                    value=run_dir/name
                    zip_file.write(value,value.relative_to(repo))
                zip_file.writestr('unselected.sv','not web evidence')
            site.extract_archive(archive.getvalue(),original.parent,CONFIG,evidence_only=True)
            extracted=original.parent/run_dir.relative_to(repo)
            self.assertTrue((extracted/site.SELECTED_RTL_MANIFEST).is_file())
            self.assertFalse((original.parent/'unselected.sv').exists())
            for case in ('original','missing','tampered','foreign','rehash','unbound'):
                with self.subTest(case=case):
                    path=extracted/site.SELECTED_RTL_MANIFEST
                    candidate=dict(manifest)
                    supplied=dict(plan)
                    if case=='missing':
                        path.unlink()
                    else:
                        if case=='tampered':
                            candidate['source_count']=99
                        if case=='foreign':
                            candidate['identity_sha256']='b'*64
                        if case=='rehash':
                            candidate['source_sha256']={'gen/chip/soc_top.sv':'b'*64}
                        if case in ('foreign','rehash'):
                            candidate['manifest_sha256']=digest({k:v for k,v in
                                candidate.items() if k!='manifest_sha256'})
                        path.write_bytes((run_dir/site.SELECTED_RTL_MANIFEST).read_bytes())
                        if case in ('tampered','foreign','rehash'):
                            site.dump(path,candidate)
                    if case=='unbound':
                        supplied.pop('selected_source_manifest')
                    site.dump(extracted/'plan.json',supplied)
                    output=root/case
                    _,entries,notes=site.evidence_index(root/'evidence',output,
                                                       'r987r/xezim-hello-world')
                    e=entries[0]
                    report=output/e['path']
                    self.assertFalse(e['passed'])
                    if case=='original':
                        self.assertEqual(e['compiler_inputs']['compiler_input_sha256'],
                                         manifest['compiler_input_sha256'])
                        self.assertIn('Archived compiler input manifest',report.read_text())
                        self.assertEqual((report.parent/site.SELECTED_RTL_MANIFEST).read_bytes(),
                                         (run_dir/site.SELECTED_RTL_MANIFEST).read_bytes())
                    else:
                        self.assertIsNone(e['compiler_inputs'])
                        self.assertNotIn('Archived compiler input manifest',report.read_text())
                        self.assertFalse((report.parent/site.SELECTED_RTL_MANIFEST).exists())
                        self.assertEqual(bool(notes),case!='missing')

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

    def test_canonical_structural_compile_is_not_reported_as_simulation(self):
        from test_identity import relative_path, selected
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = fixture(root/'evidence')
            name = 'noc-xezim'
            plan = {'engine': 'xezim-compile', 'sources': 'noc',
                    'logical_test': 'noc-rtl-compile'}
            identity = selected(name, plan, filelist=old/'sources.f',
                                run_id='ci-123-a1-012345abcdef')
            run_dir = old.parent/relative_path(identity)
            run_dir.parent.mkdir(parents=True)
            old.rename(run_dir)
            site.dump(run_dir/'identity.json', identity)
            site.dump(run_dir/'plan.json', {**plan, 'identity': identity})
            site.dump(run_dir/'result.json', {
                'target': name, 'passed': True, 'stage': 'all',
                'identity_sha256': identity['identity_sha256'],
                'canonical_id': relative_path(identity).as_posix()})
            out = root/'site'
            out.mkdir()
            _, entries, _ = site.evidence_index(
                root/'evidence', out, 'r987r/xezim-hello-world')
            entry, = entries
            self.assertEqual(entry['acceptance_scope'], 'compile_only')
            self.assertFalse(entry['axi'])
            self.assertEqual(entry['protocols'], [])
            self.assertIn('Compile/lint only PASS', (out/entry['path']).read_text())
            self.assertNotIn('Regression PASS', (out/entry['path']).read_text())

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
            self.assertIn('src="protocols.html?embed=1"',page.read_text())
            self.assertIn('href="protocol-transactions.json"',page.read_text())
            generated=(page.parent/'protocols.html').read_text()
            self.assertIn('Protocol Run Explorer',generated)
            self.assertNotIn('<img src=x onerror=alert(1)>',generated)
            self.assertNotIn('<script>alert("injected")</script>',generated)
            self.assertIn('\\u003cimg',generated)

    def test_bulky_public_captures_pack_losslessly_without_renaming_report_or_small_assets(self):
        import gzip
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=fixture(root/'evidence',axi=True)
            axi=json.loads((target/'axi-transactions.json').read_bytes())
            note='large original evidence <not HTML> '*(1024**2//25)
            axi['sections']['axi']['issues']=[note]
            site.dump(target/'axi-transactions.json',axi)
            site.dump(target/'protocol-transactions.json',{
                'schema_version':1,'capture_complete':True,'issues':[],
                'run':axi['run'],'sources':[{'id':'cpu','protocol':'axi4',
                           'role':'initiator','clock_domain':'clk'}],
                'records':[{'kind':'event','source':'cpu','protocol':'axi4',
                            'operation':'read','start_ps':1,'end_ps':1,
                            'status':'observed','fields':{'note':note}}]})
            (target/'axi-events.jsonl').write_text(json.dumps({'exact':note})+'\n')
            (target/'protocol-events.jsonl').write_text('{"small":"unchanged"}\n')
            output=root/'site'
            built=site.build(output,root/'evidence','r987r/xezim-hello-world',SHA,CONFIG)
            entry,=built['entries']
            self.assertEqual(entry['path'],'runs/123-1/chip-boot/report.html')
            self.assertEqual(entry['source_sha'],SHA)
            self.assertEqual(entry['protocol_observations'],1)
            compressed=entry['compressed_assets']
            self.assertEqual(set(compressed),{'axi-transactions.json','axi-events.jsonl',
                                              'protocol-transactions.json'})
            report=output/entry['path']
            for name,packed in compressed.items():
                self.assertFalse(report.with_name(name).exists())
                self.assertEqual(gzip.decompress(report.with_name(packed).read_bytes()),
                                 (target/name).read_bytes())
                self.assertIn(f'href="{packed}"',report.read_text())
            self.assertEqual(report.with_name('protocol-events.jsonl').read_bytes(),
                             (target/'protocol-events.jsonl').read_bytes())
            for name,source in [('report.html','axi-transactions.json.gz'),
                                ('protocols.html','protocol-transactions.json.gz')]:
                html=report.with_name(name).read_text()
                self.assertIn(f'data-capture-source="{source}"',html)
                self.assertNotIn('large original evidence',html)
            explorer=(output/'explorer.html').read_text()
            self.assertIn('runs/123-1/chip-boot/protocol-transactions.json.gz',explorer)
            self.assertEqual(json.loads((output/'data/site.json').read_text())['entries'][0]
                             ['compressed_assets'],compressed)

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

    def test_previously_published_legacy_route_survives_rolling_window_until_provider_removes_it(self):
        from unittest.mock import Mock

        repo='r987r/xezim-hello-world'
        workflow='ddr4-foundation.yml'
        path='.github/workflows/'+workflow
        target='ddr4-standalone'
        old_report='runs/123-1/ddr4-standalone/report.html'
        source_sha='b'*40
        head_sha='a'*40
        sha_before='d'*40
        checked_repo={'full_name':repo}
        old_run={'id':123,'run_attempt':1,'head_sha':head_sha,'head_branch':'legacy-ddr',
                 'event':'pull_request','status':'completed','conclusion':'success',
                 'name':'DDR4 foundation','path':path,'repository':checked_repo,
                 'head_repository':checked_repo,'created_at':'2026-11-04T00:00:00Z',
                 'updated_at':'2026-11-04T00:01:00Z',
                 'html_url':f'https://github.com/{repo}/actions/runs/123',
                 'verified_merged_pr':20}
        new_run=dict(old_run,id=124,head_branch='main',event='workflow_dispatch',
                     html_url=f'https://github.com/{repo}/actions/runs/124')
        published=dict(new_run,id=100,path='.github/workflows/pages.yml',head_sha=sha_before)
        trace={'schema_version':1,'run':{'target':target,'engine':'cocotb-verilator',
            'commit':source_sha,'dirty':False,'workflow_run_id':'123','workflow_attempt':'1'},
            'capture_complete':True,'issues':[],
            'sources':[{'id':'memory0.ddr0.dfi','protocol':'dfi','role':'link',
                        'clock_domain':'ddr_source_clk','implementation':'test_fixture'}],
            'records':[{'kind':'event','source':'memory0.ddr0.dfi','protocol':'dfi',
                        'operation':'rd','status':'observed','start_ps':100,
                        'end_ps':200,'id':None,'fields':{'dfi_phase':2}}]}
        plan={'target':target,'engine':'cocotb-verilator'}
        result={'target':target,'passed':True,'stage':'run'}
        trace_bytes=json.dumps(trace).encode()
        result_bytes=json.dumps(result).encode()
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('result.json',result_bytes)
            z.writestr('plan.json',json.dumps(plan))
            z.writestr('protocol-transactions.json',trace_bytes)
        original=archive.getvalue()
        digest='sha256:'+hashlib.sha256(original).hexdigest()
        artifact={'id':900,'name':'ddr4-dfi-123','expired':False,'size_in_bytes':len(original),
                  'digest':digest,'workflow_run':{'id':123}}
        seed={'repository':repo,'production':{'run_id':100,'source_sha':sha_before,
              'site_index_sha256':'c'*64},'reports':[{'run_id':123,'attempt':1,
              'workflow':path,'merged_pr':20,'head_sha':head_sha,'tested_sha':source_sha,
              'report_path':old_report,'artifact_id':900,'artifact_name':artifact['name'],
              'artifact_digest':digest}]}
        selected=[old_run]
        retained_fault={}

        def request(url,binary=False):
            if url.endswith('/123/artifacts?per_page=100'):
                return {'artifacts':[artifact.copy()]}
            if url.endswith('/124/artifacts?per_page=100'):
                return {'artifacts':[]}
            if url.endswith('/100'):
                return published.copy()
            if url.endswith('/123/attempts/1'):
                return old_run.copy()
            if url.endswith('/artifacts/900'):
                if 'http' in retained_fault:
                    raise HTTPError(url,retained_fault['http'],'fixture',{},None)
                return dict(artifact,**retained_fault.get('metadata',{}))
            if url.endswith('/pulls/20'):
                return {'number':20,'merged_at':'2026-11-05T00:00:00Z',
                        'head':{'sha':head_sha,'ref':'legacy-ddr'},
                        'base':{'ref':'main','repo':checked_repo}}
            if url.endswith('/git/commits/'+source_sha):
                return {'parents':[{'sha':'c'*40},{'sha':head_sha}]}
            if url.endswith('/artifacts/900/zip') and binary:
                return retained_fault.get('zip',original)
            raise AssertionError('unexpected API request: '+url)

        client=Mock(repository=repo,request=Mock(side_effect=request))
        producers={workflow:{'file':workflow,'label':old_run['name'],
                             'artifacts':[artifact['name']]}}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(site,'discover_test_workflows',return_value=producers), \
             patch.object(site,'merged_main_pr_heads',return_value={(head_sha,'legacy-ddr'):20}), \
             patch.object(site,'select_workflow_runs',return_value=({workflow:selected},[])), \
             patch.object(site,'verified_pr_tree_equivalent',return_value=False):
            root=Path(tmp)
            evidence=root/'evidence'
            out=root/'site'
            site.collect(client,CONFIG,evidence,seed)
            first=site.build(out,evidence,repo,SHA,CONFIG)
            self.assertEqual([e['path'] for e in first['entries']],[old_report])
            self.assertNotIn('retained_legacy_comparison',first['entries'][0])
            selected[:]=[new_run]
            site.collect(client,CONFIG,evidence,seed)
            second=site.build(out,evidence,repo,SHA,CONFIG)
            kept,=second['entries']
            self.assertEqual(kept['path'],old_report)
            self.assertIsNone(kept['canonical_id'])
            self.assertTrue(kept['retained_legacy_comparison'])
            self.assertEqual(kept['source_sha'],source_sha)
            self.assertNotIn('verified_site_source_sha',kept)
            self.assertEqual((out/old_report).with_name('protocol-transactions.json').read_bytes(),
                             trace_bytes)
            self.assertEqual((out/old_report).with_name('result.json').read_bytes(),result_bytes)
            notes=(evidence/'collection.json').read_bytes()
            saved=(evidence/'123-1/artifact-900/protocol-transactions.json')

            for fault,error in (
                    ({'http':503}, HTTPError),
                    ({'metadata':{'size_in_bytes':2*1024**2}}, ValueError),
                    ({'zip':original[:-1]+bytes([original[-1]^1])}, ValueError)):
                with self.subTest(fault=fault):
                    retained_fault.clear()
                    retained_fault.update(fault)
                    with self.assertRaises(error):
                        site.collect(client,CONFIG,evidence,seed)
                    self.assertEqual(saved.read_bytes(),trace_bytes)
                    self.assertEqual((evidence/'collection.json').read_bytes(),notes)
            retained_fault.clear()
            with self.assertRaisesRegex(ValueError,'oversized legacy comparison inventory'):
                site.collect(client,CONFIG,evidence,dict(seed,reports=seed['reports']*5))
            self.assertEqual(saved.read_bytes(),trace_bytes)
            forged=dict(seed,production=dict(seed['production'],source_sha='e'*40))
            with self.assertRaisesRegex(ValueError,'verified production Pages run'):
                site.collect(client,CONFIG,evidence,forged)
            self.assertEqual(saved.read_bytes(),trace_bytes)
            for fault,reason in (({'metadata':{'expired':True}},'original artifact expired'),
                                 ({'http':410},'original run or artifact no longer offered')):
                with self.subTest(fault=fault):
                    retained_fault.clear()
                    site.collect(client,CONFIG,evidence,seed)
                    self.assertTrue(saved.is_file())
                    retained_fault.update(fault)
                    site.collect(client,CONFIG,evidence,seed)
                    after=site.build(out,evidence,repo,SHA,CONFIG)
                    self.assertFalse(after['entries'])
                    self.assertFalse((out/old_report).exists())
                    self.assertFalse(saved.exists())
                    self.assertTrue(any(reason in n for n in after['notes']))

    def test_collection_refresh_expires_old_evidence_without_rewriting_retained_bytes(self):
        from unittest.mock import Mock
        from test_identity import relative_path, selected

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            evidence=root/'evidence'
            evidence.mkdir()
            # Neither a numeric name nor a symlink is evidence-cache ownership.
            (evidence/'987-1').mkdir()
            (evidence/'987-1'/'keep').write_text('unrelated')
            (evidence/'988-1').symlink_to(evidence/'987-1',target_is_directory=True)
            target='chip-boot'
            source=b'/original/selected.sv\n'
            (root/'sources.f').write_bytes(source)
            plans={}
            server={}
            snapshots={}
            downloads=[]

            def records(run_id, canonical=False):
                plan={'engine':'cocotb-verilator','sources':'noc','top':'full_chip_tb',
                      'logical_test':'multicore-cold-boot'}
                result={'target':target,'passed':True,'stage':'all'}
                files={}
                relative=Path(target)
                if canonical:
                    identity=selected(target,plan,filelist=root/'sources.f',
                                      run_id=f'ci-{run_id}-a1-012345abcdef')
                    relative=relative_path(identity)
                    files['identity.json']=json.dumps(identity)
                    plan['identity']=identity
                    result.update(identity_sha256=identity['identity_sha256'],
                                  canonical_id=relative.as_posix())
                transcript=f'actual simulator log {run_id}\n'.encode()
                files.update({'result.json':json.dumps(result),'plan.json':json.dumps(plan),
                              'sources.f':source,'simulation.log':transcript})
                buffer=io.BytesIO()
                with zipfile.ZipFile(buffer,'w') as archive:
                    for name,content in files.items():
                        archive.writestr(str(relative/name),content)
                payload=buffer.getvalue()
                server[run_id]=payload
                snapshots[run_id]=[{'id':run_id,'name':f'ci-{run_id}',
                                    'size_in_bytes':len(payload),'expired':False}]
                plans[run_id]=(transcript,
                               Path('runs')/(relative if canonical else Path(f'{run_id}-1')/relative))
                return {'id':run_id,'run_attempt':1,'head_sha':SHA,'head_branch':'main',
                        'event':'workflow_dispatch','name':'Chip boot','status':'completed',
                        'conclusion':'success','path':'.github/workflows/full-chip.yml',
                        'created_at':'2026-11-04T00:00:00Z','updated_at':'2026-11-04T00:01:00Z',
                        'html_url':f'https://github.com/r987r/xezim-hello-world/actions/runs/{run_id}'}

            runs=[records(123),records(124),records(125),records(126),records(127),
                  records(128,canonical=True)]
            workflows={'full-chip.yml':{'file':'full-chip.yml','label':'Chip boot',
                                       'artifacts':['ci-${{ github.run_id }}']}}
            race={}

            def request(path,binary=False):
                if path.endswith('/artifacts?per_page=100'):
                    return {'artifacts':snapshots[int(path.split('/')[-2])]}
                if path.endswith('/zip') and binary:
                    artifact_id=int(path.split('/')[-2])
                    downloads.append(artifact_id)
                    if artifact_id in race:
                        raise HTTPError(path,race[artifact_id],'test provider response',{},None)
                    return server[artifact_id]
                raise AssertionError('unexpected network request: '+path)

            client=Mock(repository='r987r/xezim-hello-world',request=Mock(side_effect=request))
            out=root/'site'
            with patch.object(site,'discover_test_workflows',return_value=workflows), \
                 patch.object(site,'merged_main_pr_heads',return_value={}), \
                 patch.object(site,'select_workflow_runs',
                              return_value=({'full-chip.yml':runs},[])), \
                 patch.object(site.subprocess,'check_output',return_value=(SHA+'\n').encode()):
                site.collect(client,CONFIG,evidence)
                first=site.build(out,evidence,client.repository,SHA,CONFIG)
                self.assertEqual({e['run_id'] for e in first['entries']},set(plans))
                for _,path in plans.values():
                    self.assertTrue((out/path/'report.html').is_file())
                old_notes=(evidence/'collection.json').read_bytes()

                # A still-selected run with a provider-expired or deleted archive,
                # an archive deleted after list(), and a run outside the window.
                snapshots[123][0]['expired']=True
                snapshots[124].clear()
                race[125]=410
                runs.remove(next(r for r in runs if r['id']==126))
                # A non-retention API failure after earlier runs were processed
                # must leave the prior committed evidence and notes intact.
                race[128]=503
                with self.assertRaises(HTTPError):
                    site.collect(client,CONFIG,evidence)
                self.assertEqual((evidence/'collection.json').read_bytes(),old_notes)
                self.assertTrue((evidence/'123-1/artifact-123').is_dir())
                self.assertTrue((evidence/'126-1/artifact-126').is_dir())

                del race[128]
                downloads.clear()
                site.collect(client,CONFIG,evidence)
                self.assertEqual(downloads,[125,127,128])
                second=site.build(out,evidence,client.repository,SHA,CONFIG)
                # An incoming run must not replace an unrelated symlink at
                # its exact destination, nor disturb the committed snapshot.
                notes=(evidence/'collection.json').read_bytes()
                runs.append(records(988))
                with self.assertRaisesRegex(ValueError,'unowned path collides'):
                    site.collect(client,CONFIG,evidence)
                self.assertEqual((evidence/'collection.json').read_bytes(),notes)

            self.assertEqual({e['run_id'] for e in second['entries']},{127,128})
            self.assertTrue(any('expired artifact ci-123' in note for note in second['notes']))
            self.assertTrue(any('expired or removed during collection' in note for note in second['notes']))
            for absent in (123,124,125,126):
                self.assertFalse((evidence/f'{absent}-1'/f'artifact-{absent}').exists())
                self.assertFalse((out/plans[absent][1]/'report.html').exists())
            self.assertFalse((evidence/'126-1').exists())
            for retained in (127,128):
                raw,path=plans[retained]
                self.assertTrue((out/path/'report.html').is_file())
                self.assertEqual((out/path/'simulation.log').read_bytes(),raw)
            self.assertEqual((evidence/'987-1'/'keep').read_text(),'unrelated')
            self.assertTrue((evidence/'988-1').is_symlink())

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
        # Workflow artifact paths may be multiline YAML scalars: parse
        # the selected path, rather than demanding an indentation spelling.
        parsed=yaml.safe_load(workflow)
        artifact_paths=[str(step.get("with",{}).get("path",""))
                        for job in parsed["jobs"].values()
                        for step in job.get("steps",[])
                        if step.get("uses","").startswith("actions/upload-artifact@")]
        self.assertTrue(any("format('.tools/runs/{0}/', steps.pcie-host-execution" in path
                            for path in artifact_paths),
                        "PCIe CI must preserve the selected host regression evidence")
        for mode in ("legacy", "relocated"):
            self.assertTrue(any(
                f"steps.native-noc.outputs.{mode}_canonical_id != '' && "
                f"format('.tools/runs/{{0}}/', steps.native-noc.outputs.{mode}_canonical_id)"
                in path for path in artifact_paths),
                "each original standalone PCIe execution must retain its native archive")
        for path in artifact_paths:
            if "steps.pcie-host-execution" in path:
                # The real preflight source keeps .tools/ as the upload
                # common root: do not strip the host's simulator component.
                self.assertIn(".tools/pcie0/normalized/pcie_axi_master.v", path.splitlines())
        self.assertNotIn(".tools/pcie0/noc-builds/", workflow)
        self.assertNotIn("pcie_bridge_check.vvp", workflow)
        self.assertNotIn("            .tools/pcie0/full_chip_build/",workflow)
        self.assertGreaterEqual(CONFIG["max_archive_mib"],130)
        site_html=(ROOT/"tools/templates/site_runs.html").read_text()
        self.assertIn('id="suite-summary"',site_html)
        self.assertIn('id="family"',site_html)
        self.assertIn('No recorded result',site_html)
        self.assertIn('const key=identityKey+"|"+e.workflow',site_html)
        self.assertIn('e.config_target',site_html)

    def test_isolated_outbound_artifact_is_not_a_regression_report_producer(self):
        workflow = ".github/workflows/pcie-outbound.yml"
        jobs = yaml.safe_load((ROOT / workflow).read_text())["jobs"]
        archive = next(step for step in jobs["outbound-pcie-rtl"]["steps"]
                       if step.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(archive["with"]["name"], "pcie-outbound-${{ github.run_id }}")
        self.assertEqual(archive["with"]["path"].splitlines(), [
            "dv/pcie0/upstream.lock.json", "${{ steps.native-outbound.outputs.archive_dir }}"])
        self.assertIn("steps.native-outbound.outputs.archive_dir != ''", archive["if"])
        # The prefix-based archive matcher must never collect this name:
        # old native ZIPs under that name have a standalone scoreboard named
        # result.json but it does not meet the shared regression schema.
        discovered = site.discover_test_workflows(ROOT)["pcie-outbound.yml"]
        self.assertEqual(discovered["artifacts"], [
            "pcie-outbound-fullchip-${{ github.run_id }}"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = fixture(root / "evidence")
            (directory / "result.json").unlink()
            (directory / "outbound-result.json").write_text('{"passed":true}')
            runs, reports, notes = site.evidence_index(
                root / "evidence", root / "site", "r987r/xezim-hello-world")
            self.assertEqual(len(runs), 1)
            self.assertEqual(reports, [])
            self.assertEqual(notes, [])

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
