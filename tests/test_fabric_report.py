"""Read-only fabric report correctness, routing and evidence provenance."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import fabric_report


class FabricExplorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=fabric_report.load(ROOT)

    def pair(self,source,target):
        return next(m for m in self.report['matrix']
                    if m['source']==source and m['target']==target)

    def test_inventory_traces_all_current_generated_meshed_boundaries(self):
        data=self.report
        self.assertEqual(data['summary']['meshes'],8)
        self.assertEqual(data['summary']['cross_mesh_links'],11)
        self.assertEqual(data['summary']['initiators'],6)
        self.assertEqual(data['summary']['targets'],10)
        self.assertEqual(len({i['name'] for i in data['interfaces']}),len(data['interfaces']))
        self.assertEqual(data['summary']['interfaces'],len(data['interfaces']))
        self.assertEqual(data['summary']['reachable_routes'],len(data['routes']))
        self.assertTrue(all(i['clock_signal']=='clk_i' for i in data['interfaces']))
        self.assertTrue(all(i['clock_frequency_hz'] is None for i in data['interfaces']))
        self.assertTrue(all(i['fabric_shared_max_txns'] is not None
                            for i in data['interfaces'] if i['fabric']!='memory0.memory_data'))

    def test_local_and_remote_sram_xy_hops(self):
        local=next(r for r in self.report['routes']
                   if r['source']=='compute0_local_data.cpu' and r['target']=='compute0.sram')
        self.assertEqual(local['network_path'],['compute0_local_data'])
        self.assertEqual(local['stages'][0]['routers'],[
            'compute0_local_data.router_0_0','compute0_local_data.router_0_1'])
        self.assertEqual(local['router_links'],1)
        remote=next(r for r in self.report['routes']
                    if r['source']=='compute0_local_data.cpu' and r['target']=='compute1.sram')
        self.assertEqual(remote['network_path'],[
            'compute0_local_data','global_data','compute1_local_data'])
        self.assertEqual(remote['inter_mesh_links'],2)
        self.assertEqual(remote['router_links'],
                         sum(s['router_links'] for s in remote['stages']))
        self.assertTrue(all(s['latency_cycles'] is None for s in remote['stages']))
        self.assertIsNone(remote['latency']['end_to_end_read_cycles'])

    def test_memory_targets_pass_through_real_local_crossbar_model(self):
        route=next(r for r in self.report['routes']
                   if r['source']=='compute0_local_data.cpu' and r['target']=='memory0.hbm0')
        self.assertEqual(route['network_path'],[
            'compute0_local_data','global_data','memory0_local_data'])
        self.assertEqual(route['router_links'],5)
        self.assertEqual(route['inter_mesh_links'],2)
        self.assertEqual(route['stages'][-2]['kind'],'memory_crossbar')
        self.assertEqual(route['stages'][-1]['kind'],'target_service')
        self.assertEqual(route['target_integration'],'behavioral_memory_model')
        self.assertEqual(self.pair('compute0_local_data.cpu','memory0.ddr0')['access'],'RW')

    def test_denied_routes_and_boot_read_only_policy(self):
        self.assertEqual(self.pair('compute1_local_data.cpu','boot.rom')['access'],'none')
        self.assertEqual(self.pair('compute1_local_data.cpu','boot.flash')['access'],'none')
        self.assertEqual(self.pair('compute0_local_data.cpu','boot.rom')['access'],'R')
        self.assertEqual(self.pair('compute0_local_data.cpu','boot.flash')['access'],'R')
        self.assertEqual(self.pair('compute0_local_config.cpu','memory0.ctrl')['access'],'RW')
        self.assertEqual(self.pair('compute1_local_config.cpu','compute0.dma')['access'],'RW')
        self.assertEqual(set(m['plane'] for m in self.report['matrix']),{'data','config'})

    def test_detects_routing_mismatch_and_duplicate_links(self):
        manifest=json.loads((ROOT/'gen/noc/floonoc/manifest.json').read_text())
        networks=fabric_report.prepare_networks(manifest,ROOT/'gen/noc/floonoc')
        s=json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        s['connections'][0]['to']=s['connections'][1]['to']
        with self.assertRaisesRegex(fabric_report.FabricReportError,'duplicate/unknown'):
            import yaml
            soc=yaml.safe_load((ROOT/'config/soc.yaml').read_text())
            knobs=yaml.safe_load((ROOT/'config/interface_contracts.yaml').read_text())
            from interface_contracts import build
            ports=build(soc,knobs,networks['global_data']['profile'])['ports']
            chip=json.loads((ROOT/'gen/chip/manifest.json').read_text())
            fabric_report.build(soc,knobs,manifest,networks,s,chip,ports)

    def test_only_bound_single_beat_successful_current_evidence_is_measured(self):
        data=copy.deepcopy(self.report)
        source='compute0_local_data.cpu'
        fixture={
            'run':{'capture_bound':True,'capture_overflow':False,'dirty':False},
            'sections':{'axi':{'transactions':[
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':1,
                 'issues':[],'response':'0x0','latency_ps':140,'address':'0x10000000',
                 'operation':'read','plane':'data'},
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':1,
                 'issues':[],'response':'0x0','latency_ps':180,'address':'0x10000000',
                 'operation':'read','plane':'data'},
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':1,
                 'issues':[],'response':'0x2','latency_ps':200,'address':'0x10000000',
                 'operation':'read','plane':'data'},
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':2,
                 'issues':[],'response':'0x0','latency_ps':400,'address':'0x10000000',
                 'operation':'read','plane':'data'}
            ]}}
        }
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'runs/9-1/chip';folder.mkdir(parents=True)
            (folder/'axi-transactions.json').write_text(json.dumps(fixture))
            entry={'axi':True,'passed':True,'assets':['axi-transactions.json'],
                   'path':'runs/9-1/chip/report.html','source_sha':'f'*40,
                   'target':'chip','engine':'verilator'}
            fabric_report.attach_one_beat_observations(data,[entry],Path(tmp),'a'*40)
        r=next(x for x in data['routes'] if x['id']==source+'->compute0.sram')
        obs=r['one_beat_observations']
        self.assertEqual(len(obs),1)
        self.assertEqual(obs[0]['count'],2)
        self.assertEqual(obs[0]['min_ps'],140)
        self.assertEqual(obs[0]['median_ps'],160)
        self.assertFalse(obs[0]['matches_site_source'])
        self.assertIsNone(r['latency']['end_to_end_read_cycles'])
        self.assertEqual(sum(len(x['one_beat_observations']) for x in data['routes']),1)


if __name__=='__main__':unittest.main()
