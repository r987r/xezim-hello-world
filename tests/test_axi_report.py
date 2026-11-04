"""Reporting semantics: bursts, ID ordering, reset and lossless wide values."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import axi_report


CATALOG = {'monitors':[{'id':'cpu','role':'initiator','plane':'data',
                       'network':'local','endpoints':['cpu'],'prefix':'tap_cpu'}],
           'regions':[{'plane':'data','name':'ram','base':'0x1000','size':'0x1000'}]}


def event(channel, time, **fields):
    return {'channel':channel,'time_ps':time,'monitor':'cpu',
            'fields':{key:hex(value) for key,value in fields.items()}}


class AxiReportTests(unittest.TestCase):
    def test_w_before_aw_and_b_reordering_across_ids(self):
        events = [event('w',1,data=0xaa,strb=15,last=0),
                  event('w',2,data=0xbb,strb=3,last=1),
                  event('aw',3,id=0,addr=0x1000,len=1,size=2),
                  event('aw',4,id=1,addr=0x1010,len=0,size=2),
                  event('w',5,data=0xcc,strb=15,last=1),
                  event('b',6,id=1,resp=2),event('b',9,id=0,resp=0)]
        rows,issues,_ = axi_report.correlate(events,CATALOG)
        self.assertFalse(issues)
        self.assertEqual([r['end_ps'] for r in rows],[9,6])
        self.assertEqual([b['data'] for b in rows[0]['beats']],['0xaa','0xbb'])
        self.assertEqual(rows[0]['beats'][1]['strb'],'0x3')
        self.assertEqual(rows[1]['response'],'0x2')
        self.assertEqual(rows[0]['latency_ps'],6)

    def test_interleaved_read_ids_and_reused_id_queue(self):
        events = [event('ar',1,id=0,addr=0x1000,len=1,size=3),
                  event('ar',2,id=1,addr=0x1100,len=0,size=3),
                  event('ar',3,id=0,addr=0x1200,len=0,size=3),
                  event('r',4,id=0,data=11,last=0,resp=2),
                  event('r',5,id=1,data=22,last=1,resp=0),
                  event('r',6,id=0,data=33,last=1,resp=0),
                  event('r',7,id=0,data=44,last=1,resp=0)]
        rows,issues,_ = axi_report.correlate(events,CATALOG)
        self.assertFalse(issues)
        self.assertEqual([r['end_ps'] for r in rows],[6,5,7])
        self.assertEqual(rows[0]['response'],'0x2')
        self.assertEqual(rows[2]['beats'][0]['data'],'0x2c')

    def test_reset_aborts_pending_and_does_not_pair_across_epochs(self):
        events = [event('ar',1,id=2,addr=0x1000,len=0,size=2),
                  {'channel':'reset','time_ps':2,'active':True},
                  event('r',3,id=2,data=42,last=1,resp=0),
                  event('ar',4,id=2,addr=0x1004,len=0,size=2)]
        rows,issues,_ = axi_report.correlate(events,CATALOG)
        self.assertEqual([r['status'] for r in rows],['reset_aborted','incomplete'])
        self.assertEqual(len(issues),1)
        self.assertNotEqual(rows[0]['epoch'],rows[1]['epoch'])
        self.assertIsNone(rows[1]['end_ps'])

    def test_phase_and_measured_clock_period_are_preserved(self):
        events=[
            {'channel':'capture_start','time_ps':0,'monitors':['cpu']},
            {'channel':'clock_period','time_ps':10000,'period_ps':10000},
            {'channel':'phase','time_ps':20000,
             'label':'Fabric baseline: single-outstanding one-beat'},
            event('ar',30000,id=0,addr=0x1000,len=0,size=3),
            event('r',50000,id=0,data=42,last=1,resp=0),
            {'channel':'phase','time_ps':60000,'label':'Stalled stress'},
            event('ar',70000,id=1,addr=0x1008,len=0,size=3),
            event('r',90000,id=1,data=43,last=1,resp=0)]
        rows,issues,controls=axi_report.correlate(events,CATALOG)
        self.assertEqual(issues,[])
        self.assertEqual([r['phase'] for r in rows],
                         ['Fabric baseline: single-outstanding one-beat','Stalled stress'])
        self.assertEqual(next(c['period_ps'] for c in controls
                              if c['channel']=='clock_period'),10000)
        data,summary=self.intent_report(events[1:])
        self.assertEqual(data['run']['clock_period_ps'],10000)
        self.assertEqual(data['sections']['axi']['transactions'][0]['phase'],
                         'Fabric baseline: single-outstanding one-beat')
        self.assertEqual(summary['issues'],0)

    def test_same_cycle_request_response_and_bad_last_length(self):
        # Collector coroutine ordering within an edge is not channel ordering.
        events = [event('r',1,id=0,data=123,last=1,resp=0),
                  event('ar',1,id=0,addr=0x1000,len=3,size=2)]
        rows,issues,_ = axi_report.correlate(events,CATALOG)
        self.assertFalse(issues)
        self.assertEqual(rows[0]['latency_ps'],0)
        self.assertIn('read beat count',rows[0]['issues'][0])

    def test_catalog_covers_every_endpoint_with_intermesh_links_once(self):
        catalog = json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())
        manifest = json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())
        import yaml
        expected = {name+'.'+ep['name'] for name,n in manifest['networks'].items()
                    for ep in yaml.safe_load((ROOT/'gen/noc/floonoc'/n['config']).read_text())['endpoints']}
        endpoints = [e for m in catalog['monitors'] for e in m['endpoints']]
        self.assertEqual(set(endpoints),expected)
        self.assertEqual(len(endpoints),len(expected))
        fabric = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        self.assertEqual(sum(m['role']=='link' for m in catalog['monitors']),len(fabric['connections']))
        self.assertEqual(len(catalog['monitors']),len(fabric['masters'])+len(fabric['slaves'])+len(fabric['connections']))

    def test_report_retains_wide_hex_failed_result_and_escapes_script_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            catalog=directory/'catalog.json';catalog.write_text(json.dumps(CATALOG))
            events=[{'channel':'capture_start','time_ps':0,'monitors':['cpu']},
                    event('ar',1,id=15,addr=0xffffffffffffffff,len=0,size=3),
                    event('r',3,id=15,data=0xfedcba9876543210,last=1,resp=0)]
            (directory/'axi-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
            plan={'target':'</script><img src=x onerror=alert(1)>','engine':'cocotb-verilator',
                  'report':{'axi':{'catalog':str(catalog)}}}
            summary=axi_report.write_report(directory,plan,{'passed':False})
            data=json.loads((directory/'axi-transactions.json').read_text())
            row=data['sections']['axi']['transactions'][0]
            self.assertEqual(row['address'],'0xffffffffffffffff')
            self.assertEqual(row['beats'][0]['data'],'0xfedcba9876543210')
            self.assertFalse(data['run']['result']['passed'])
            self.assertTrue(summary['capture_bound'])
            html=(directory/'report.html').read_text()
            self.assertNotIn('</script><img',html)
            self.assertIn('\\u003c/script',html)

    def test_failed_startup_and_truncated_jsonl_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); catalog=directory/'catalog.json'
            catalog.write_text(json.dumps(CATALOG))
            (directory/'axi-events.jsonl').write_text('{"truncated":')
            summary=axi_report.write_report(directory,{'target':'failed','engine':'cocotb-verilator',
                'report':{'axi':{'catalog':str(catalog)}}},{'passed':False})
            self.assertFalse(summary['capture_bound'])
            self.assertGreater(summary['issues'],0)
            self.assertTrue((directory/'report.html').is_file())

    def intent_report(self, events, annotated=True):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);catalog=directory/'catalog.json'
            catalog.write_text(json.dumps(CATALOG))
            start={'channel':'capture_start','time_ps':0,'monitors':['cpu']}
            if annotated:start['annotations_version']=1
            (directory/'axi-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in [start,*events]))
            summary=axi_report.write_report(directory,{'target':'scope','engine':'cocotb-verilator',
                'report':{'axi':{'catalog':str(catalog)}}},{'passed':True})
            return json.loads((directory/'axi-transactions.json').read_text()),summary

    def test_expectation_consumed_once_and_only_at_exact_address_and_operation(self):
        expected={'channel':'expect_response','time_ps':1,'monitor':'cpu','operation':'read',
                  'address':'0x1000','response':'0x2','reason':'Deliberate capacity check'}
        data,summary=self.intent_report([expected,
            event('ar',2,id=0,addr=0x1010,len=0,size=2),event('r',3,id=0,data=0,last=1,resp=0),
            event('ar',4,id=0,addr=0x1000,len=0,size=2),event('r',5,id=0,data=0,last=1,resp=2),
            event('ar',6,id=0,addr=0x1000,len=0,size=2),event('r',7,id=0,data=0,last=1,resp=2)])
        rows=data['sections']['axi']['transactions']
        self.assertEqual([r['error_intent'] for r in rows],['none','expected','undeclared'])
        self.assertEqual(rows[1]['expected_reason'],'Deliberate capacity check')
        self.assertEqual(summary['issues'],1)

    def test_legacy_error_is_not_retroactively_declared_expected(self):
        data,summary=self.intent_report([event('ar',1,id=0,addr=0x1000,len=0,size=2),
                                       event('r',2,id=0,data=0,last=1,resp=2)],annotated=False)
        self.assertFalse(data['run']['annotations_available'])
        self.assertEqual(data['sections']['axi']['transactions'][0]['error_intent'],'observed')
        self.assertEqual(summary['issues'],0)

    def test_expected_response_mismatch_is_a_capture_failure(self):
        data,summary=self.intent_report([
            {'channel':'expect_response','time_ps':1,'monitor':'cpu','operation':'read',
             'address':'0x1000','response':'0x2','reason':'Injected fault'},
            event('ar',2,id=0,addr=0x1000,len=0,size=2),event('r',3,id=0,data=0,last=1,resp=0)])
        self.assertEqual(summary['issues'],1)
        self.assertIn('declared expectation',data['sections']['axi']['issues'][0]['message'])

    def test_chip_actors_distinguish_cpus_bfm_and_idle_reserved_dma(self):
        chip=json.loads((ROOT/'gen/chip/manifest.json').read_text())
        self.assertEqual(chip['dma_engines_instantiated'],0)
        self.assertEqual(chip['axi_actors']['compute0_local_data.cpu']['kind'],'rtl_cpu')
        self.assertEqual(chip['axi_actors']['compute0_local_data.dma']['kind'],'verification_bfm')
        self.assertEqual(chip['axi_actors']['compute1_local_data.dma']['kind'],'reserved_idle')


if __name__=='__main__':
    unittest.main()
