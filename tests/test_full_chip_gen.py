import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import chip_bootgen
import full_chip_gen


class FullChipTests(unittest.TestCase):
    def setUp(self):
        self.cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())

    def test_hello_images_are_real_rv32i_and_fit_declared_slots(self):
        fw = chip_bootgen.build(self.cfg)
        self.assertEqual([c['name'] for c in fw['cores']], ['compute0','compute1'])
        for code in fw['images'].values():
            self.assertLessEqual(len(code)*4, fw['stride'])
            self.assertTrue({0x03,0x23,0x63} <= {w & 0x7f for w,_ in code})
            self.assertEqual(code[-1][0], 0x6f)
        self.assertTrue(any('copy_1' in asm for _,asm in fw['rom']))

    def test_more_serv_cores_use_same_bounded_barrier_firmware(self):
        cfg = copy.deepcopy(self.cfg)
        for index in range(2,16):
            name = f'compute{index}'
            cfg['subsystems'].insert(-1, {'name':name, 'type':'compute', 'cpu':
                {'ip':'serv','bus':'wishbone','adapter':'serv_wishbone'}})
            cfg['address_map']['data'].append({'name':name+'.sram','base':hex(0x10000000+index*0x1000000),'size':'0x100000'})
        fw = chip_bootgen.build(cfg)
        self.assertEqual(len(fw['images']),16)
        self.assertTrue(all(len(code)*4 <= fw['stride'] for code in fw['images'].values()))

    def test_relocated_map_changes_firmware_without_a_preload(self):
        for region in self.cfg['address_map']['data']:
            if region['name']=='compute0.sram': region['base']='0x12000000'
            if region['name']=='compute1.sram': region['base']='0x13000000'
        with tempfile.TemporaryDirectory() as tmp:
            _, meta = chip_bootgen.emit(self.cfg, Path(tmp))
            self.assertEqual(meta['mailbox'],0x12000400)
            self.assertEqual([c['sram_base'] for c in meta['cores']],[0x12000000,0x13000000])
            self.assertIn('none:',meta['sram_initialization'])

    def test_chip_and_bfm_share_one_real_noc_assembly(self):
        meta = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            chip = full_chip_gen.emit(self.cfg,meta,ROOT/'gen/noc/floonoc',root)
            top=(root/'soc_top.sv').read_text()
            self.assertEqual(chip['cores'],2)
            self.assertEqual(chip['networks'],8)
            self.assertEqual(chip['memory_crossbar_inputs'],1)
            self.assertIn('soc_noc u_noc',top)
            self.assertIn('axi_crossbar #(',top)
            self.assertIn('axi_to_axi_lite #(',top)
            self.assertIn('ProbeEnable ? probe_req',top)
            self.assertEqual(len(chip['memory_models']),2)
            self.assertNotIn('$readmemh',top)  # SRAM initialization cannot be hidden in top wiring

    def test_dma_wiring_is_generated_for_every_compute_and_real_config_target(self):
        meta = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            chip = full_chip_gen.emit(self.cfg, meta, ROOT/'gen/noc/floonoc', out)
            top = (out/'soc_top.sv').read_text()
            tb = (out/'full_chip_dma_tb.sv').read_text()
            self.assertEqual(chip['dma_engines_instantiated'], 2)
            self.assertEqual(top.count('soc_idma_engine u_dma_'), 2)
            self.assertEqual(top.count('soc_dma_regs #('), 2)
            for name in ('compute0','compute1'):
                self.assertIn('u_dma_'+name,top)
                self.assertIn('u_dma_csr_'+name,top)
                self.assertIn('m_'+name+'_local_data_dma_req',top)
                self.assertIn('s_'+name+'_local_config_dma_regs_req',top)
            self.assertIn('DmaEnable',top)
            self.assertIn('DmaTestMode',tb)
            self.assertNotIn('$readmemh',top)
            self.assertTrue((out/'dma_actors.json').exists())

    def test_unimplemented_runtime_and_memory_provider_fail_closed(self):
        for field,value in [('phases',['init','run']),('memory_model','pretend_ddr')]:
            cfg=copy.deepcopy(self.cfg)
            cfg['verification']['full_chip_boot'][field]=value
            with self.assertRaises(ValueError): chip_bootgen.build(cfg)
