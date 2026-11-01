import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import socgen


class SocConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=yaml.safe_load((ROOT/'config/soc.yaml').read_text())

    def test_baseline_two_different_memories_and_cpus(self):
        m=socgen.validate(copy.deepcopy(self.base))
        self.assertEqual(m['ingress'],2)
        self.assertEqual([x['name'] for x in m['targets']],['memory0.hbm0','memory0.ddr0'])
        self.assertEqual([x['kind'] for x in m['targets']],['hbm','ddr'])
        self.assertEqual([x['base'] for x in m['targets']],[0x100000000,0x140000000])
        self.assertEqual([x['ip'] for x in m['cpu_instances']],['picorv32','serv'])
        self.assertEqual(m['common_dma'],'pulp_idma')
        self.assertEqual(len(m['subsystems']),3)

    def test_deterministic_generation_and_noc_ir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'memory'
            cfg=ROOT/'config/soc.yaml'
            socgen.run(cfg,out)
            first=(out/'memory_tb.sv').read_bytes()
            manifest=json.loads((out/'manifest.json').read_text())
            ir=json.loads((out.parent/'noc/fabric_ir.json').read_text())
            socgen.run(cfg,out)
            self.assertEqual((out/'memory_tb.sv').read_bytes(),first)
            self.assertIn(b'axi_crossbar',first)
            self.assertIn(b'axi_memory_target_model',first)
            self.assertIn(b'N_IN = 2',first)
            self.assertEqual(manifest['targets'][1]['sim_pipeline'],True)
            self.assertEqual(ir['memory']['targets'],['memory0.hbm0','memory0.ddr0'])
            self.assertEqual(ir['fabrics']['global_data']['backend'],'floonoc')
            self.assertFalse(ir['fabrics']['global_data']['emitter_available'])

    def test_overlap_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['address_map']['data'][3]['base']='0x100000000'
        with self.assertRaisesRegex(socgen.ConfigError,'overlap'): socgen.validate(doc)

    def test_unknown_subsystem_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['subsystems'][0]['type']='typo'
        with self.assertRaisesRegex(socgen.ConfigError,'unknown subsystem'): socgen.validate(doc)

    def test_changed_ingress_requires_agent_count(self):
        doc=copy.deepcopy(self.base)
        doc['subsystem_types']['memory']['data_ingress_ports']=3
        with self.assertRaisesRegex(socgen.ConfigError,'master agents'): socgen.validate(doc)

    def test_extra_compute_needs_no_new_memory_sv(self):
        doc=copy.deepcopy(self.base)
        doc['subsystems'].append({'name':'compute2','type':'compute','cpu':{'ip':'serv','bus':'wishbone','adapter':'serv_wishbone'}})
        doc['networks']['global_config']['reachable_subsystems'].append('compute2')
        m=socgen.validate(doc)
        self.assertEqual(len(m['subsystems']),4)
        self.assertEqual(len(m['targets']),2)

    def test_missing_output_target_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['networks']['global_data']['outputs'][1]['target']='missing.ddr'
        with self.assertRaisesRegex(socgen.ConfigError,'missing target'): socgen.validate(doc)

    def test_wrong_cpu_adapter_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['subsystems'][1]['cpu']['adapter']='picorv32_axi'
        with self.assertRaisesRegex(socgen.ConfigError,'incorrect bus/adapter'): socgen.validate(doc)

    def test_unknown_noc_backend_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['fabrics']['global_data']['backend']='unknown'
        with self.assertRaisesRegex(socgen.ConfigError,'unknown NoC backend'): socgen.validate(doc)

    def test_noc_backend_replacement_needs_implementation(self):
        doc=copy.deepcopy(self.base)
        doc['fabrics']['memory_data']['backend']='pulp_axi'
        with self.assertRaisesRegex(socgen.ConfigError,'No RTL generator implemented'): socgen.validate(doc)

    def test_unknown_controller_or_model_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['memory_targets'][0]['controller']='vendor_hbm'
        with self.assertRaisesRegex(socgen.ConfigError,'unsupported hbm controller'): socgen.validate(doc)
        doc=copy.deepcopy(self.base)
        doc['memory_targets'][1]['simulation']['backend']='litedram'
        with self.assertRaisesRegex(socgen.ConfigError,'only axi_ram behavioral'): socgen.validate(doc)

    def test_config_unreachable_rejected(self):
        doc=copy.deepcopy(self.base)
        doc['networks']['global_config']['reachable_subsystems'].remove('compute1')
        with self.assertRaisesRegex(socgen.ConfigError,'each subsystem exactly once'): socgen.validate(doc)

    def test_pin_present_for_real_ip(self):
        locked=yaml.safe_load((ROOT/'config/ip.lock.yaml').read_text())['third_party']
        for ip in ('verilog_axi','picorv32','serv','pulp_idma','litedram','hisa_hbm','pulp_axi'):
            self.assertIn(ip,locked)
            self.assertRegex(locked[ip]['commit'],r'^[a-f0-9]{40}$')


if __name__=='__main__': unittest.main()
