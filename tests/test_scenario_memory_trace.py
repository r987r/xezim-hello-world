"""Pure source-neutral memory trace tests; synthetic data is never RTL proof."""
import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.scenario_memory_trace import build, embed_in_run_report
from dv.common.action_events import ActionEvidenceError
from dv.common.scenario import canonical_json


def fixture():
    plan={"schema_version":1,"kind":"soc_scenario_intent_only","scenario_id":"cpu_bfm_ddr_roundtrip",
          "execution_evidence":None,"seed":79,"actors":["cpu0","dma0"],"provenance":{},
          "regions":[
              {"name":"compute0.sram.payload","base":0x10002000,"modeled_bytes":8192,"kind":"sram","cpu_visible":True},
              {"name":"memory0.ddr0","base":0x140000100,"modeled_bytes":65280,"kind":"ddr","cpu_visible":False}],
          "allocations":[
              {"buffer":"src","region":"compute0.sram.payload","phys":0x10002000,"size":64,
               "token":1,"generation":1,"owner":"cpu0","phase":"run","allocated_by":"alloc_source","released_by":None},
              {"buffer":"return","region":"compute0.sram.payload","phys":0x10002040,"size":64,
               "token":2,"generation":1,"owner":"cpu0","phase":"run","allocated_by":"alloc_return","released_by":None},
              {"buffer":"ddr","region":"memory0.ddr0","phys":0x140000100,"size":64,
               "token":1,"generation":1,"owner":"cpu0","phase":"run","allocated_by":"alloc_ddr","released_by":None}],
          "actions":[
              {"action_instance_id":"alloc_source","actor":"cpu0","phase":"run","kind":"memory.allocate",
               "depends_on":[],"args":{"buffer":"src"}},
              {"action_instance_id":"alloc_return","actor":"cpu0","phase":"run","kind":"memory.allocate",
               "depends_on":["alloc_source"],"args":{"buffer":"return"}},
              {"action_instance_id":"alloc_ddr","actor":"cpu0","phase":"run","kind":"memory.allocate",
               "depends_on":[],"args":{"buffer":"ddr"}},
              {"action_instance_id":"init_source","actor":"cpu0","phase":"run","kind":"memory.initialize",
               "depends_on":["alloc_source"],"args":{"buffer":"src","pattern":{"kind":"constant","seed":90},"policy":"strict"}},
              {"action_instance_id":"copy_out","actor":"dma0","phase":"run","kind":"dma.copy",
               "depends_on":["init_source","alloc_ddr"],"args":{"src":"src","dst":"ddr"}},
              {"action_instance_id":"copy_back","actor":"dma0","phase":"run","kind":"dma.copy",
               "depends_on":["copy_out","alloc_return"],"args":{"src":"ddr","dst":"return"}},
              {"action_instance_id":"check_return","actor":"cpu0","phase":"check","kind":"memory.check",
               "depends_on":["copy_back"],"args":{"buffer":"return","length":64,
                     "pattern":{"kind":"constant","seed":90},"policy":"strict"}}]}
    raw=canonical_json(plan).encode()
    return plan,raw,hashlib.sha256(raw).hexdigest()


def axi():
    rows=[]
    for i,(operation,address) in enumerate((('read',0x10002000),('write',0x140000100),
                                            ('read',0x140000100),('write',0x10002040))):
        rows.append({"uid":f"compute0_local_data.dma:1:{i}","monitor":"compute0_local_data.dma",
                     "role":"initiator","operation":operation,"address":hex(address),
                     "status":"complete","response":"0x0","issues":[],
                     "start_ps":100+i*10,"end_ps":105+i*10})
    return {"run":{"capture_bound":True,"capture_overflow":False},
            "sections":{"axi":{"issues":[],"transactions":rows}}}


def evidence(sha,profile='real_cpu0_compiled_c'):
    e={"execution_state":"rtl_observed","scenario_id":"cpu_bfm_ddr_roundtrip",
       "plan_sha256":sha,"profile":profile,"intent_is_not_evidence":True,
       "observed_dma_axi_counts":{"src_ar":1,"ddr_aw":1,"ddr_ar":1,"return_aw":1}}
    if profile=='real_cpu0_compiled_c':
        e.update(cpu_result_checked=True,observed_cpu_allocations=[0x10002000,0x10002040,0x140000100])
    else:
        e['independently_readback_bytes']=64
    return e


def result(profile='real_cpu0_compiled_c'):
    return {"passed":True,"results":[{"passed":True,"exit_code":0}],
            "test_flow":({"status":"complete","passed":True,"issues":0,"steps":6}
                         if profile=='real_cpu0_compiled_c' else {"status":"unmeasured","issues":0,"steps":0})}


class ScenarioMemoryTraceTests(unittest.TestCase):
    def setUp(self):
        self.plan,self.raw,self.sha=fixture()

    def test_plan_is_not_cpu_allocation_proof(self):
        model=build(self.raw)
        self.assertEqual(model['status'],'plan_only_unmeasured')
        self.assertFalse(model['real_allocation_tokens_proven'])
        self.assertFalse(model['release_quiescence_proven'])
        self.assertTrue(all(x['phys_provenance']=='planner_only' and x['observed_accesses']==[]
                            for x in model['buffers']))

    def test_cpu_phys_from_qualified_run_but_tokens_remain_plan_only(self):
        model=build(self.raw,axi=axi(),execution=evidence(self.sha),result=result())
        buffers={x['buffer']:x for x in model['buffers']}
        self.assertEqual(model['status'],'cpu_phys_correlated_lifetimes_planned_only')
        self.assertTrue(all(b['phys_provenance']=='rtl_cpu_mailbox_checked_by_existing_test'
                            and b['token_provenance']=='planner_only' for b in buffers.values()))
        self.assertEqual([len(buffers[b]['observed_accesses']) for b in ('src','return','ddr')],[1,1,2])
        self.assertEqual(buffers['return']['checks'][0]['status'],'real_cpu0_firmware')
        self.assertEqual(model['target_model'],'modeled_memory_only_not_litedram_phy')

    def test_bfm_cannot_upgrade_a_predicted_allocation(self):
        bfm='reset_isolated_cocotb_bfm'
        model=build(self.raw,axi=axi(),execution=evidence(self.sha,bfm),result=result(bfm))
        self.assertEqual(model['status'],'bfm_traffic_observed_allocation_unmeasured')
        self.assertTrue(all(b['phys_provenance']=='planner_only' for b in model['buffers']))
        self.assertEqual([b for b in model['buffers'] if b['buffer']=='return'][0]['checks'][0]['status'],
                         'cocotb_axi_readback')

    def test_cpu_mismatched_physical_or_plan_sha_rejected(self):
        bad=evidence(self.sha)
        bad['observed_cpu_allocations'][0]+=64
        with self.assertRaisesRegex(ActionEvidenceError,'differs'):
            build(self.raw,axi=axi(),execution=bad,result=result())
        bad=evidence(self.sha);bad['plan_sha256']='0'*64
        with self.assertRaisesRegex(ActionEvidenceError,'not independently'):
            build(self.raw,axi=axi(),execution=bad,result=result())

    def test_failed_run_missing_axi_and_stale_tokens_rejected(self):
        with self.assertRaisesRegex(ActionEvidenceError,'requires independent'):
            build(self.raw,execution=evidence(self.sha),result=result())
        bad_result=result();bad_result['passed']=False
        with self.assertRaisesRegex(ActionEvidenceError,'not independently'):
            build(self.raw,axi=axi(),execution=evidence(self.sha),result=bad_result)
        p=copy.deepcopy(self.plan);p['allocations'][1]['token']=1
        with self.assertRaisesRegex(ActionEvidenceError,'duplicate C-compatible'):
            build(canonical_json(p).encode())

    def test_incomplete_capture_or_bad_axi_response_rejected(self):
        a=axi();a['run']['capture_overflow']=True
        with self.assertRaisesRegex(ActionEvidenceError,'not a complete'):
            build(self.raw,axi=a)
        a=axi();a['sections']['axi']['transactions'][0]['response']='0x2'
        with self.assertRaisesRegex(ActionEvidenceError,'incomplete/error'):
            build(self.raw,axi=a)

    def test_ambiguous_reused_address_needs_measured_lifetime(self):
        p=copy.deepcopy(self.plan)
        p['allocations'][1]['phys']=p['allocations'][0]['phys']
        with self.assertRaisesRegex(ActionEvidenceError,'ambiguous physical'):
            build(canonical_json(p).encode(),axi=axi())

    def test_render_into_single_original_run_page_and_escape_html(self):
        model=build(self.raw)
        with TemporaryDirectory() as temp:
            path=Path(temp)/'report.html'
            path.write_text('<html><main><h1>Existing test runs</h1></main></html>')
            embed_in_run_report(path,model)
            html=path.read_text()
            self.assertIn('Existing test runs',html)
            self.assertIn('Memory allocation and lifetime evidence',html)
            self.assertIn('planner_only',html)
            with self.assertRaisesRegex(ActionEvidenceError,'already contains'):
                embed_in_run_report(path,model)
            path.write_text('<html><main></main></html>')
            evil=copy.deepcopy(model);evil['buffers'][0]['buffer']='<script>alert(1)</script>'
            embed_in_run_report(path,evil)
            self.assertNotIn('<script>',path.read_text())
            self.assertIn('&lt;script&gt;',path.read_text())


if __name__=='__main__':
    unittest.main()
