"""Opt-in Ethernet0 generated NoC attachment tests.

This is source-generation evidence, not a traffic or PHY qualification.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "tools"))
import full_chip_gen


class EthernetVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=yaml.safe_load((ROOT/"config/soc.yaml").read_text())
        cls.noc_manifest=json.loads((ROOT/"gen/supernoc/manifest.json").read_text())
        cls.noc_root=ROOT/"gen/noc/floonoc"

    def emit_variant(self,**kwargs):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            full_chip_gen.emit(self.cfg,self.noc_manifest,self.noc_root,out,
                               image_prefix=str(out),**kwargs)
            return {
                "top":(out/"soc_top.sv").read_text(),
                "dma_tb":(out/"full_chip_dma_tb.sv").read_text(),
                "manifest":json.loads((out/"manifest.json").read_text())
            }

    def test_opt_in_has_real_data_and_config_noc_attachments(self):
        built=self.emit_variant(ethernet_mode=True)
        source=built["top"]
        self.assertIn("ethernet0_axi_mvp",source)
        self.assertIn("ethernet_queue_axi_regs",source)
        self.assertIn("u_ethernet_mvp",source)
        self.assertIn("u_ethernet_queue_regs",source)
        self.assertIn("m_ethernet0_local_data_packet_dma_req",source)
        self.assertIn("s_ethernet0_local_config_controller_regs_req",source)
        self.assertIn("64'h0000000013001000",source)
        self.assertIn("64'h0000000013001200",source)
        self.assertIn("64'h0000000013001400",source)
        self.assertIn("64'h0000000013001600",source)
        self.assertIn("64'h0000000140000000",source)
        self.assertIn("32'h40050000",source)
        self.assertIn("gmii_tx_clk",built["dma_tb"])
        self.assertIn("eth_irq_o(eth_irq)",built["dma_tb"])
        eth=next(x for x in built["manifest"]["peripheral_subsystems"]
                 if x["name"]=="ethernet0")
        self.assertEqual(eth["rtl_attachment"],"live_ethernet_gmii_queue_axi_mvp")
        self.assertEqual(eth["csr_attachment"],"live_ethernet_queue_axi4_lite")
        self.assertFalse(built["manifest"]["ethernet0"]["gmii_test_proven"])
        self.assertFalse(built["manifest"]["ethernet0"]["completion_test_proven"])

    def test_default_main_generation_keeps_ethernet_reserved(self):
        built=self.emit_variant()
        eth=next(x for x in built["manifest"]["peripheral_subsystems"]
                 if x["name"]=="ethernet0")
        self.assertEqual(eth["rtl_attachment"],"reserved_idle")
        self.assertEqual(eth["csr_attachment"],"explicit_axi_error")
        self.assertNotIn("ethernet0_axi_mvp",built["top"])
        self.assertNotIn("ethernet_queue_axi_regs",built["top"])
        self.assertNotIn("gmii_rx_clk",built["top"])
        self.assertNotIn("gmii_rx_clk",built["dma_tb"])


if __name__=="__main__":
    unittest.main()
