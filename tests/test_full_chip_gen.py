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
            self.assertEqual(top.count('soc_idma_engine #('), 2)
            self.assertEqual(top.count('soc_dma_regs #('), 2)
            for name in ('compute0','compute1'):
                self.assertIn('u_dma_'+name,top)
                self.assertIn('u_dma_csr_'+name,top)
                self.assertIn('m_'+name+'_local_data_dma_req',top)
                self.assertIn('s_'+name+'_local_config_dma_regs_req',top)
            self.assertIn('DmaEnable',top)
            self.assertIn('DmaTestMode',tb)
            self.assertIn('cpu0_data_bfm_awid', tb)
            self.assertIn('cpu0_config_bfm_awid', tb)
            self.assertIn('.probe_awid(cpu0_data_bfm_awid)', tb)
            self.assertIn('.cfgprobe_awid(cpu0_config_bfm_awid)', tb)
            self.assertIn('NumAxInFlight(2)',top)
            self.assertIn('DescriptorPrefetch(0)',top)
            self.assertEqual(chip['dma_parameters_by_compute']['compute0'],
                             self.cfg['subsystem_types']['compute']['dma_parameters'])
            # Host-driven NoC traffic must not leak B/R replies back into the
            # held CPU adapter; its width-converter arbiter asserts otherwise.
            self.assertIn("assign cpu_data_0_rsp = DmaTestMode ? '0 :", top)
            self.assertIn("assign cpu_config_0_rsp = DmaTestMode ? '0 :", top)
            self.assertNotIn('$readmemh',top)
            self.assertTrue((out/'dma_actors.json').exists())

    def test_cpu_dma_variant_reuses_real_boot_generator_and_checker(self):
        meta = json.loads((ROOT/'gen/supernoc/manifest.json').read_text())
        cfg=copy.deepcopy(self.cfg)
        flash=next(r for r in cfg['address_map']['data']
                   if r['name']=='boot.flash')
        hook=int(flash['base'],0)+0x1000
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            result=full_chip_gen.emit(
                cfg,meta,ROOT/'gen/noc/floonoc',out,
                cpu0_run_hook=hook,image_prefix='tmp/shared-cpu-dma',
                cpu_dma_mode=True)
            fw=json.loads((out/'firmware.json').read_text())
            self.assertEqual(fw['cpu0_run_hook'],hook)
            self.assertEqual(result['dma_engines_instantiated'],2)
            self.assertIn('real CPUs execute C',result['dma_configuration'])
            self.assertEqual(result['axi_actors']['compute0_local_data.dma']['kind'],'rtl_dma')
            tb=(out/'full_chip_tb.sv').read_text()
            top=(out/'soc_top.sv').read_text()
            image=(out/'compute0.lst').read_text()
            self.assertIn(".DmaEnable(1'b1)",tb)
            self.assertIn('cpu_dma_success',tb)
            self.assertIn('CPU C DMA evidence',tb)
            self.assertIn('tmp/shared-cpu-dma/compute0.hex',tb)
            self.assertIn('"tmp/shared-cpu-dma/flash.hex"',top)
            self.assertIn('jalr ra, 0(a0)',image)
            self.assertIn('bne a0, zero, dma_error',image)
            self.assertNotIn('$readmemh',top)
            self.assertLessEqual(len(fw['cores'][0]['words'])*4,
                                 cfg['boot']['flash_slot_stride'])
            with self.assertRaises(ValueError):
                full_chip_gen.emit(cfg,meta,ROOT/'gen/noc/floonoc',out,
                                   cpu_dma_mode=True)

    def test_cpu_dma_hook_is_bounded_to_immutable_flash(self):
        import chip_bootgen
        cfg=copy.deepcopy(self.cfg)
        flash=next(r for r in cfg['address_map']['data'] if r['name']=='boot.flash')
        base=int(flash['base'],0)
        for bad in (base,base+0x10,base+0x1001,base+int(flash['size'],0)):
            with self.subTest(addr=bad),self.assertRaises(ValueError):
                chip_bootgen.build(cfg,cpu0_run_hook=bad)

    def test_dma_parameters_are_per_compute_and_fail_closed(self):
        compute0=self.cfg['subsystems'][0]
        compute1=self.cfg['subsystems'][1]
        self.assertEqual(full_chip_gen.dma_params_for(self.cfg, compute0),
                         {'num_ax_in_flight':2,'buffer_depth':3,'descriptor_prefetch':0})
        cfg=copy.deepcopy(self.cfg)
        cfg['subsystems'][0]['dma_parameters']={
            'num_ax_in_flight':3, 'descriptor_prefetch':4}
        self.assertEqual(full_chip_gen.dma_params_for(cfg,cfg['subsystems'][0]),
                         {'num_ax_in_flight':3,'buffer_depth':3,'descriptor_prefetch':4})
        self.assertEqual(full_chip_gen.dma_params_for(cfg,cfg['subsystems'][1])['num_ax_in_flight'],2)
        for bad in ({'num_ax_in_flight':0},{'num_ax_in_flight':1},{'descriptor_prefetch':-1},
                    {'buffer_depth':0},{'invented_option':123}):
            cfg['subsystems'][0]['dma_parameters']=bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                full_chip_gen.dma_params_for(cfg,cfg['subsystems'][0])

    def test_unimplemented_runtime_and_memory_provider_fail_closed(self):
        for field,value in [('phases',['init','run']),('memory_model','pretend_ddr')]:
            cfg=copy.deepcopy(self.cfg)
            cfg['verification']['full_chip_boot'][field]=value
            with self.assertRaises(ValueError): chip_bootgen.build(cfg)
