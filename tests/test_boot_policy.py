import copy
import sys
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import bootgen


class BootPolicyTests(unittest.TestCase):
    def setUp(self):
        self.cfg=yaml.safe_load((ROOT/'config/soc.yaml').read_text())

    def test_supported_boot_policy(self):
        self.assertIn('bootrom',bootgen.build(self.cfg)['addresses'])
        self.assertEqual(bootgen.build(self.cfg)["addresses"]["sram1"], 0x11000000)

    def test_unimplemented_boot_policies_fail_closed(self):
        for key,bad in [('strategy','direct_sram'),('image_source','spi_nor'),
                        ('secondary_release','automatic'),('sram_powerup','zero')]:
            with self.subTest(key=key):
                cfg=copy.deepcopy(self.cfg)
                cfg['boot'][key]=bad
                with self.assertRaisesRegex(ValueError,'not implemented'):
                    bootgen.build(cfg)

if __name__=='__main__':
    unittest.main()
