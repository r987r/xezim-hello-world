"""Fast pre-simulation gate for the full real-CPU C DMA firmware image.

The same compiler, source list, linker, memory configuration and ELF entry
are used by the later full-chip RTL run. This catches unresolved RV32I
runtime symbols BEFORE the much slower NoC/DMA Verilator build.
"""
import shutil
import tempfile
from pathlib import Path
import unittest
import yaml

from tools.cpu_dma_firmware import compile_firmware

ROOT = Path(__file__).resolve().parents[1]


class CpuDmaFirmwareTests(unittest.TestCase):
    def test_combined_cpu_dma_pcie_c_image_links(self):
        # The same real C, SRAM allocator and iDMA driver; the PCIe/DDR
        # transfer only compiles into the opt-in PCIe host variant.
        if not all(shutil.which(t) for t in ("clang", "ld.lld", "llvm-objcopy")):
            self.skipTest("LLVM cross toolchain unavailable")
        cfg=yaml.safe_load((ROOT/"config/soc.yaml").read_text())
        pcie=int(next(r["base"] for r in cfg["address_map"]["data"]
                      if r["name"]=="pcie0.sram"),0)
        with tempfile.TemporaryDirectory() as tmp:
            image=compile_firmware(cfg,Path(tmp),pcie_host_mode=True)
            self.assertEqual(image["defines"]["SOC_PCIE_SRAM"],pcie)
            self.assertGreater(len(image["data"]),0)
            self.assertLess(len(image["data"]),image["flash_limit"]-0x1000)
            self.assertTrue((Path(tmp)/"cpu_dma.elf").is_file())

    def test_full_c_image_links_at_real_boot_hook(self):
        if not all(shutil.which(t) for t in ("clang", "ld.lld", "llvm-objcopy")):
            self.skipTest("LLVM cross toolchain unavailable")
        cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())
        base = int(next(r["base"] for r in cfg["address_map"]["data"]
                        if r["name"] == "boot.flash"), 0)
        with tempfile.TemporaryDirectory() as tmp:
            build = compile_firmware(cfg, Path(tmp))
            self.assertEqual(build["hook"], base + 0x1000)
            self.assertGreater(len(build["data"]), 0)
            self.assertTrue((Path(tmp)/"cpu_dma.elf").is_file())
            self.assertTrue((Path(tmp)/"cpu_dma.bin").is_file())
            self.assertEqual(len(build["sha256"]), 64)
