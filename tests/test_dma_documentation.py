"""Fail fast when DMA implementation status or published docs go stale."""
import json
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class DmaDocumentContract(unittest.TestCase):
    def test_published_dma_status_matches_generated_core_inventory(self):
        cfg = yaml.safe_load((ROOT/'config/soc.yaml').read_text())
        computes = [s['name'] for s in cfg['subsystems'] if s['type']=='compute']
        chip = json.loads((ROOT/'gen/chip/manifest.json').read_text())
        actors = json.loads((ROOT/'gen/chip/dma_actors.json').read_text())['axi_actors']
        self.assertEqual(chip['dma_engines_instantiated'], len(computes))
        self.assertIn('DmaEnable=1', chip['dma_configuration'])
        top = (ROOT/'gen/chip/soc_top.sv').read_text()
        for name in computes:
            self.assertIn(f'u_dma_{name}', top)
            self.assertIn(f'u_dma_csr_{name}', top)
            self.assertEqual(actors[name+'_local_data.dma']['kind'], 'rtl_dma')
            self.assertEqual(actors[name+'_local_config.dma_regs']['kind'], 'rtl_registers')
        tb = (ROOT/'gen/chip/full_chip_dma_tb.sv').read_text()
        self.assertIn('DmaTestMode', tb)
        self.assertIn('cpu0_data_bfm_awid', tb)
        self.assertIn('cpu0_config_bfm_awid', tb)
        self.assertEqual(chip['dma_parameters_by_compute']['compute0'],
                         cfg['subsystem_types']['compute']['dma_parameters'])
        self.assertIn('CPU0 AXI BFM',
                      actors['compute0_local_data.cpu']['label'])
        self.assertIn('no PCIe',
                      actors['compute0_local_config.cpu']['label'])

    def test_docs_show_optional_real_dma_but_not_cpu_firmware_or_phy(self):
        files = ['README.md', 'AGENTS.md', 'docs/architecture.md',
                 'docs/implementation-status.md', 'docs/full-chip-boot.md',
                 'docs/dma-bringup.md', 'docs/publication.md']
        contents = {f: (ROOT/f).read_text() for f in files}
        for f in ('README.md','docs/full-chip-boot.md','docs/dma-bringup.md'):
            self.assertIn('DmaEnable=1', contents[f], f)
            self.assertIn('dv-chip-dma', contents[f], f)
        for f in ('README.md','docs/implementation-status.md','docs/dma-bringup.md'):
            self.assertTrue('pending' in contents[f].lower(), f)
        report_doc=(ROOT/'docs/axi-run-reports.md').read_text()
        for required in ('BVALID && BREADY', 'RVALID && RREADY && RLAST',
                         'CPU0 AXI BFM', 'DDR4 controller'):
            self.assertIn(required,report_doc)
        stale = ('real PULP iDMA integration, DMA CSRs and interrupts',
                 'There are **zero instantiated DMA engines**',
                 'Real DMA backend/frontend integration and CSR mapping are pending',
                 'No DMA engine is currently instantiated.',
                 'The real DMA is **not attached** to the full-chip FlooNoC')
        for f, data in contents.items():
            for phrase in stale:
                self.assertNotIn(phrase, data, f)


if __name__=='__main__':
    unittest.main()
