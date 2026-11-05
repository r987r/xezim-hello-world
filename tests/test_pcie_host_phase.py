"""Fast reusable contract tests for host/CPU shared INIT/RUN/CHECK."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import chip_bootgen
import full_chip_gen
import pcie_chip


class PcieHostPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())

    def test_existing_cold_boot_does_not_enable_host_or_require_ip(self):
        fw = chip_bootgen.build(copy.deepcopy(self.cfg))
        image = [asm for _, asm in fw["images"]["compute0"]]
        self.assertFalse(any("wait_host_" in instruction for instruction in image))
        self.assertFalse(any("0x12000800" in instruction for instruction in image))

    def test_cpu0_real_remote_sram_init_run_check_barriers(self):
        fw = chip_bootgen.build(pcie_chip.host_variant_config(self.cfg), pcie_host_phase=True)
        code = [asm for _, asm in fw["images"]["compute0"]]
        self.assertTrue(any("wait_host_init" in asm for asm in code))
        self.assertTrue(any("wait_host_run" in asm for asm in code))
        self.assertTrue(any("wait_host_check" in asm for asm in code))
        self.assertTrue(any("jal zero" in asm for asm in code))
        self.assertTrue(all("wait_host_" not in asm
                            for _, asm in fw["images"]["compute1"]))
        self.assertLessEqual(len(code) * 4, pcie_chip.host_variant_config(self.cfg)["boot"]["flash_slot_stride"])
        self.assertEqual(fw["sram_bases"], [0x10000000, 0x11000000])

    def test_minimal_real_dma_host_variant_is_one_chip(self):
        # Existing pinned iDMA + real PCIe bridge are both enabled.
        cfg=pcie_chip.host_variant_config(self.cfg)
        flash=next(int(x["base"],0) for x in cfg["address_map"]["data"]
                   if x["name"]=="boot.flash")
        hook=flash+0x1000
        manifest=json.loads((ROOT/"gen/supernoc/manifest.json").read_text())
        fw=chip_bootgen.build(cfg,cpu0_run_hook=hook,pcie_host_phase=True)
        opcodes="\\n".join(asm for _,asm in fw["images"]["compute0"])
        self.assertIn("jalr ra, 0(a0)",opcodes)
        self.assertIn("wait_host_init",opcodes)
        self.assertIn("wait_host_run",opcodes)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            result=full_chip_gen.emit(cfg,manifest,ROOT/"gen/noc/floonoc",path,
                     image_prefix="gen/chip",cpu0_run_hook=hook,
                     cpu_dma_mode=True,pcie_host_mode=True)
            tb=(path/"full_chip_tb.sv").read_text()
            rtl=(path/"soc_top.sv").read_text()
            self.assertIn(".DmaEnable(1'b1)",tb)
            self.assertIn("pcie_axi_master",rtl)
            self.assertIn("gen_dma_compute0",rtl)
            self.assertIn("m_pcie0_local_data_host_req = pcie_req",rtl)
            self.assertIn("cpu0_run_hook",result)
            self.assertIn("external_host",json.loads((path/"firmware.json").read_text()))

    def test_host_and_firmware_have_distinct_bounded_dma_buffers(self):
        host=(ROOT/"dv/pcie0/host_adapter.py").read_text()
        firmware=(ROOT/"sw/dma/tests/cpu_dma_run.c").read_text()
        self.assertIn("0x500",host)
        self.assertIn("0x600",host)
        self.assertIn("SOC_PCIE_SRAM + 0x500u",firmware)
        self.assertIn("SOC_PCIE_SRAM + 0x600u",firmware)
        self.assertIn("SOC_DDR_BASE + 0x800u",firmware)
        self.assertIn("soc_dma_chain_build(&desc, across_pcie, 3",firmware)
        self.assertIn("host_verify[i] !=",firmware)

    def test_host_contract_rejects_missing_peripheral(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["subsystems"] = [s for s in cfg["subsystems"]
                             if s["name"] != "pcie0"]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            chip_bootgen.build(cfg, pcie_host_phase=True)

    def test_relocatable_sram_phase_mailbox_not_hardcoded(self):
        cfg = copy.deepcopy(self.cfg)
        win = next(w for w in cfg["address_map"]["data"]
                   if w["name"] == "pcie0.sram")
        win["base"] = "0x13000000"
        fw = chip_bootgen.build(pcie_chip.host_variant_config(cfg), pcie_host_phase=True)
        cpu0 = "\n".join(asm for _, asm in fw["images"]["compute0"])
        self.assertIn("lui x12, 0x13001", cpu0)
        self.assertNotIn("lui x12, 0x12001", cpu0)

    def test_generic_generator_keeps_explicit_reserved_peripheral_control(self):
        manifest = json.loads((ROOT/"gen/supernoc/manifest.json").read_text())
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            full_chip_gen.emit(self.cfg, manifest, ROOT/"gen/noc/floonoc",
                               path, image_prefix="gen/chip",
                               pcie_host_mode=True)
            chip = (path/"soc_top.sv").read_text()
            tb = (path/"full_chip_tb.sv").read_text()
            firmware = json.loads((path/"firmware.json").read_text())
            self.assertIn("pcie_axi_master", chip)
            self.assertIn("m_pcie0_local_data_host_req = pcie_req", chip)
            self.assertIn("u_s_pcie0_local_data_sram", chip)
            self.assertIn("u_reserved_s_pcie0_local_config_controller_regs", chip)
            self.assertIn("status_error_uncor", tb)
            self.assertIn("wire rst = ~rst_n", tb)
            self.assertEqual(firmware["external_host"]["mailbox_base"],0x12000800)
            self.assertEqual(firmware["external_host"]["roles"],
                             ["enumerate","init_ack","run_data","check_ack"])
            for field in pcie_chip.TLP_PORTS:
                self.assertIn(field, chip)
                self.assertIn(field, tb)

if __name__ == "__main__":
    unittest.main()
