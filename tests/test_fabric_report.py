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

    def test_reference_clock_min_average_max_and_table_coverage(self):
        stats=fabric_report._cycle_stats([100000,120000,140000],10000)
        self.assertEqual((stats['min_cycles'],stats['avg_cycles'],
                          stats['max_cycles']), (10,12,14))
        self.assertEqual(stats['median_cycles'],12)
        with self.assertRaises(fabric_report.FabricReportError):
            fabric_report._cycle_stats([100],0)
        report=fabric_report.latency_table(copy.deepcopy(self.report))
        self.assertEqual(report['stat_order'],['min','avg','max'])
        self.assertEqual(len(report['rows']),len(self.report['matrix']))
        self.assertEqual(set(report['mesh_columns']),{'data','config'})
        self.assertEqual(report['mesh_columns']['data'],[
            'compute0_local_data','compute1_local_data','global_data',
            'memory0_local_data'])
        denied=next(r for r in report['rows']
                    if r['source']=='compute1_local_data.cpu'
                    and r['destination']=='boot.rom')
        self.assertEqual(denied['access'],'none')
        self.assertIsNone(denied['route_id'])
        self.assertEqual(denied['mesh_cycles'],{})
        self.assertIsNone(denied['target_cycles']['read'])
        allowed=next(r for r in report['rows']
                     if r['source']=='compute0_local_data.cpu'
                     and r['destination']=='memory0.hbm0')
        self.assertEqual(allowed['network_path'],[
            'compute0_local_data','global_data','memory0_local_data'])
        self.assertEqual(allowed['mesh_cycles'],{})
        self.assertEqual(allowed['end_to_end_cycles'],{'read':None,'write':None})

    def test_stage_table_keeps_read_write_separate_and_source_provenance(self):
        report=copy.deepcopy(self.report)
        route=next(r for r in report['routes']
                   if r['source']=='compute0_local_data.cpu'
                   and r['target']=='memory0.hbm0')
        base={'sample_count':3,'clock_period_ps':10000,
              'source_sha':'c'*40,'matches_site_source':True,
              'run_report':'runs/123-1/supernoc/report.html'}
        def metric(samples):
            return fabric_report._cycle_stats(samples,10000)
        route['one_beat_stage_observations']=[
            {**base,'operation':'read',
             'end_to_end':metric([400000,420000,440000]),
             'stage_metrics':[
                 {'kind':'mesh','network':'compute0_local_data',
                  'sum_stats':metric([80000,90000,100000])},
                 {'kind':'mesh','network':'global_data',
                  'sum_stats':metric([80000,80000,80000])},
                 {'kind':'mesh','network':'memory0_local_data',
                  'sum_stats':metric([80000,90000,100000])},
                 {'kind':'terminal_axi_service',
                  'sum_stats':metric([160000,160000,160000])}]},
            {**base,'operation':'write',
             'end_to_end':metric([450000,480000,510000]),
             'stage_metrics':[
                 {'kind':'mesh','network':'compute0_local_data',
                  'sum_stats':metric([100000,110000,120000])},
                 {'kind':'mesh','network':'global_data',
                  'sum_stats':metric([90000,100000,110000])},
                 {'kind':'mesh','network':'memory0_local_data',
                  'sum_stats':metric([100000,110000,120000])},
                 {'kind':'terminal_axi_service',
                  'sum_stats':metric([160000,160000,160000])}]},
        ]
        table=fabric_report.latency_table(report)
        row=next(x for x in table['rows'] if x['route_id']==route['id'])
        rd=row['mesh_cycles']['compute0_local_data']['read']
        wr=row['mesh_cycles']['compute0_local_data']['write']
        self.assertEqual((rd['min_cycles'],rd['avg_cycles'],
                          rd['max_cycles']),(8,9,10))
        self.assertEqual((wr['min_cycles'],wr['avg_cycles'],
                          wr['max_cycles']),(10,11,12))
        self.assertEqual((row['end_to_end_cycles']['read']['min_cycles'],
                          row['end_to_end_cycles']['read']['avg_cycles'],
                          row['end_to_end_cycles']['read']['max_cycles']),(40,42,44))
        self.assertEqual(row['target_cycles']['write']['avg_cycles'],16)
        self.assertEqual(rd['n'],3)
        self.assertEqual(rd['reference_clock_period_ps'],10000)
        self.assertEqual(rd['run_sha'],'c'*40)
        route['one_beat_stage_observations'][0]['matches_site_source']=False
        table=fabric_report.latency_table(report)
        row=next(x for x in table['rows'] if x['route_id']==route['id'])
        self.assertIsNone(row['end_to_end_cycles']['read'])
        self.assertIsNotNone(row['end_to_end_cycles']['write'])

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
        with self.assertRaisesRegex(fabric_report.FabricReportError,'incompatible inter-mesh AXI widths|duplicate/unknown'):
            import yaml
            soc=yaml.safe_load((ROOT/'config/soc.yaml').read_text())
            knobs=yaml.safe_load((ROOT/'config/interface_contracts.yaml').read_text())
            from interface_contracts import build
            ports=build(soc,knobs,networks['global_data']['profile'])['ports']
            chip=json.loads((ROOT/'gen/chip/manifest.json').read_text())
            fabric_report.build(soc,knobs,manifest,networks,s,chip,ports)

    def test_serial_baseline_measures_mesh_forward_return_and_terminal_boundary(self):
        from collections import OrderedDict
        data=copy.deepcopy(self.report)
        route=next(r for r in data['routes']
                   if r['source']=='compute0_local_data.cpu' and r['target']=='memory0.hbm0')
        catalog=json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())
        mon_by_endpoint={endpoint:m for m in catalog['monitors']
                         for endpoint in m['endpoints']}
        endpoints=[route['source']]+[st['to'] for st in route['stages'] if st['kind']=='mesh']
        monitors=OrderedDict((mon_by_endpoint[ep]['id'],mon_by_endpoint[ep]) for ep in endpoints)
        self.assertEqual(len(monitors),4)
        time_pairs=[(100000,500000),(140000,460000),
                    (180000,420000),(220000,380000)]
        phase='Fabric baseline: single-outstanding one-beat'
        addr='0x100000080'
        rows=[]
        for (mid, m), (start,end) in zip(monitors.items(), time_pairs):
            rows.append({'monitor':mid,'role':m['role'],'status':'complete',
                         'expected_beats':1,'issues':[],'response':'0x0',
                         'latency_ps':end-start,'start_ps':start,'end_ps':end,
                         'address':addr,'operation':'read','plane':'data',
                         'phase':phase})
        self.assertEqual(rows[0]['monitor'],route['source'])
        payload={'run':{'capture_bound':True,'capture_overflow':False,
                        'dirty':False,'clock_period_ps':10000},
                 'sections':{'axi':{'transactions':rows,
                                    'monitors':catalog['monitors']}}}
        sha='f'*40
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'runs/9-1/noc';folder.mkdir(parents=True)
            (folder/'axi-transactions.json').write_text(json.dumps(payload))
            entry={'axi':True,'passed':True,'assets':['axi-transactions.json'],
                   'path':'runs/9-1/noc/report.html','source_sha':sha,
                   'target':'supernoc','engine':'cocotb-verilator'}
            fabric_report.attach_one_beat_observations(data,[entry],Path(tmp),sha)
        obs=route['one_beat_stage_observations']
        self.assertEqual(len(obs),1)
        self.assertEqual(obs[0]['sample_count'],1)
        self.assertEqual(obs[0]['end_to_end']['median_cycles'],40)
        stages=obs[0]['stage_metrics']
        self.assertEqual(len(stages),4)
        self.assertEqual([s['sum_stats']['median_cycles'] for s in stages],
                         [8,8,8,16])
        self.assertEqual([s['request_stats']['median_cycles'] for s in stages[:3]],
                         [4,4,4])
        self.assertEqual([s['response_stats']['median_cycles'] for s in stages[:3]],
                         [4,4,4])
        self.assertEqual(stages[-1]['kind'],'terminal_axi_service')
        self.assertIn('downstream',stages[-1]['note'])
        table=data['latency_table']
        row=next(x for x in table['rows'] if x['route_id']==route['id'])
        self.assertEqual(row['end_to_end_cycles']['read']['avg_cycles'],40)
        self.assertEqual(row['target_cycles']['read']['avg_cycles'],16)
        self.assertEqual(row['mesh_cycles']['global_data']['read']['avg_cycles'],8)
        self.assertIsNone(row['end_to_end_cycles']['write'])

    def test_same_tree_merge_evidence_is_measured_without_rewriting_tested_sha(self):
        data=copy.deepcopy(self.report)
        route=next(r for r in data['routes']
                   if r['source']=='compute0_local_data.cpu'
                   and r['target']=='compute0.sram')
        catalog=json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())
        by_ep={ep:m['id'] for m in catalog['monitors'] for ep in m['endpoints']}
        src=by_ep[route['source']]
        dst=by_ep[route['stages'][0]['to']]
        phase='Fabric baseline: single-outstanding one-beat'
        rows=[]
        for monitor,role,start,end in ((src,'initiator',10000,100000),
                                       (dst,'target',40000,70000)):
            rows.append({'monitor':monitor,'role':role,
                         'status':'complete','expected_beats':1,'issues':[],
                         'response':'0x0','latency_ps':end-start,
                         'start_ps':start,'end_ps':end,'address':'0x10000000',
                         'operation':'read','plane':'data','phase':phase})
        trace={'run':{'capture_bound':True,'capture_overflow':False,
                      'dirty':False,'clock_period_ps':10000},
               'sections':{'axi':{'transactions':rows,
                                  'monitors':catalog['monitors']}}}
        tested_sha='b'*40; site_sha='c'*40
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'runs/1-1/supernoc';folder.mkdir(parents=True)
            (folder/'axi-transactions.json').write_text(json.dumps(trace))
            entry={'axi':True,'passed':True,'assets':['axi-transactions.json'],
                   'path':'runs/1-1/supernoc/report.html','source_sha':tested_sha,
                   'target':'supernoc','engine':'cocotb-verilator',
                   'merged_pr':17, 'verified_site_source_sha':site_sha}
            fabric_report.attach_one_beat_observations(data,[entry],Path(tmp),site_sha)
        obs=route['one_beat_stage_observations']
        self.assertEqual(len(obs),1)
        self.assertEqual(obs[0]['source_sha'],tested_sha)
        self.assertEqual(obs[0]['source_equivalence'],'verified_same_tree')
        self.assertTrue(obs[0]['matches_site_source'])
        row=next(x for x in data['latency_table']['rows'] if x['route_id']==route['id'])
        self.assertEqual(row['mesh_cycles']['compute0_local_data']['read']['avg_cycles'],6)
        self.assertEqual(row['target_cycles']['read']['avg_cycles'],3)
        self.assertEqual(row['end_to_end_cycles']['read']['avg_cycles'],9)
        self.assertEqual(row['end_to_end_cycles']['read']['run_sha'],tested_sha)
        self.assertEqual(row['end_to_end_cycles']['read']['source_equivalence'],
                         'verified_same_tree')

    def test_newest_verified_run_selected_irrespective_of_artifact_order(self):
        data=copy.deepcopy(self.report)
        route=next(r for r in data['routes']
                   if r['source']=='compute0_local_data.cpu'
                   and r['target']=='compute0.sram')
        catalog=json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())
        by_ep={ep:m['id'] for m in catalog['monitors'] for ep in m['endpoints']}
        phase='Fabric baseline: single-outstanding one-beat'
        def capture(latency):
            rows=[]
            for monitor,role,lo,hi in (
                    (by_ep[route['source']],'initiator',10000,10000+latency),
                    (by_ep[route['stages'][0]['to']],'target',40000,latency-20000)):
                rows.append({'monitor':monitor,'role':role,'status':'complete',
                             'expected_beats':1,'issues':[],'response':'0x0',
                             'latency_ps':hi-lo,'start_ps':lo,'end_ps':hi,
                             'address':'0x10000000','operation':'read','plane':'data',
                             'phase':phase})
            return {'run':{'capture_bound':True,'capture_overflow':False,
                           'dirty':False,'clock_period_ps':10000},
                    'sections':{'axi':{'transactions':rows,
                                       'monitors':catalog['monitors']}}}
        with tempfile.TemporaryDirectory() as tmp:
            entries=[]
            for run_id,recorded_at,total in (
                    (1,'2026-01-01T00:00:00Z',90000),
                    (2,'2026-02-01T00:00:00Z',100000)):
                folder=Path(tmp)/f'runs/{run_id}-1/supernoc'
                folder.mkdir(parents=True)
                (folder/'axi-transactions.json').write_text(json.dumps(capture(total)))
                entries.append({'axi':True,'passed':True,
                                'assets':['axi-transactions.json'],
                                'path':f'runs/{run_id}-1/supernoc/report.html',
                                'source_sha':'c'*40,'target':'supernoc',
                                'engine':'cocotb-verilator',
                                'run_id':run_id,'recorded_at':recorded_at})
            fabric_report.attach_one_beat_observations(data,entries,Path(tmp),'c'*40)
        row=next(x for x in data['latency_table']['rows'] if x['route_id']==route['id'])
        self.assertEqual(row['end_to_end_cycles']['read']['avg_cycles'],10)
        self.assertIn('runs/2-1/',row['end_to_end_cycles']['read']['run_report'])
        self.assertEqual(len(route['one_beat_stage_observations']),2)

    def test_serial_baseline_does_not_project_historical_timings(self):
        data=copy.deepcopy(self.report)
        route=next(r for r in data['routes']
                   if r['source']=='compute0_local_data.cpu' and r['target']=='compute0.sram')
        catalog=json.loads((ROOT/'gen/supernoc/axi_monitors.json').read_text())
        tx={'monitor':route['source'],'role':'initiator','status':'complete',
            'expected_beats':1,'issues':[],'response':'0x0','latency_ps':30000,
            'start_ps':100000,'end_ps':130000,'address':'0x10000000',
            'operation':'read','plane':'data',
            'phase':'Fabric baseline: single-outstanding one-beat'}
        payload={'run':{'capture_bound':True,'capture_overflow':False,
                        'dirty':False,'clock_period_ps':10000},
                 'sections':{'axi':{'transactions':[tx],'monitors':catalog['monitors']}}}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'runs/9-1/noc';folder.mkdir(parents=True)
            (folder/'axi-transactions.json').write_text(json.dumps(payload))
            entry={'axi':True,'passed':True,'assets':['axi-transactions.json'],
                   'path':'runs/9-1/noc/report.html','source_sha':'f'*40,
                   'target':'supernoc','engine':'cocotb-verilator'}
            fabric_report.attach_one_beat_observations(data,[entry],Path(tmp),'a'*40)
        self.assertEqual(len(route['one_beat_observations']),1)
        self.assertEqual(route['one_beat_stage_observations'],[])
        row=next(x for x in data['latency_table']['rows'] if x['route_id']==route['id'])
        self.assertIsNone(row['end_to_end_cycles']['read'])
        self.assertEqual(row['mesh_cycles'],{})

    def test_only_bound_single_beat_successful_current_evidence_is_measured(self):
        data=copy.deepcopy(self.report)
        source='compute0_local_data.cpu'
        fixture={
            'run':{'capture_bound':True,'capture_overflow':False,'dirty':False,
                   'clock_period_ps':10000},
            'sections':{'axi':{'transactions':[
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':1,
                 'issues':[],'response':'0x0','latency_ps':140,'address':'0x10000000',
                 'operation':'read','plane':'data','start_ps':100,'end_ps':240},
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':1,
                 'issues':[],'response':'0x0','latency_ps':180,'address':'0x10000000',
                 'operation':'read','plane':'data','start_ps':500,'end_ps':680},
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':1,
                 'issues':[],'response':'0x2','latency_ps':200,'address':'0x10000000',
                 'operation':'read','plane':'data','start_ps':800,'end_ps':1000},
                {'monitor':source,'role':'initiator','status':'complete','expected_beats':2,
                 'issues':[],'response':'0x0','latency_ps':400,'address':'0x10000000',
                 'operation':'read','plane':'data','start_ps':1100,'end_ps':1500}
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
