"""Compile and link actual RV32I CPU DMA in both CSR header modes."""
from pathlib import Path
import tempfile
import unittest
import shutil

import yaml

from tools.cpu_dma_firmware import compile_firmware

ROOT = Path(__file__).resolve().parents[1]


class CpuGeneratedCsrImageTests(unittest.TestCase):
    def test_generated_csr_bases_match_legacy_rv32i_and_reject_missing_windows(self):
        for tool in ("clang", "llvm-objcopy", "ld.lld"):
            if not shutil.which(tool):
                self.skipTest(f"missing test-specific RV32I compiler tool: {tool}")
        cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        with tempfile.TemporaryDirectory(prefix="csr-bases-") as tmp:
            root = Path(tmp)
            legacy = compile_firmware(cfg, root / "legacy",
                                      use_config_csr_header=False)
            generated = compile_firmware(cfg, root / "generated")
            self.assertEqual(legacy["data"], generated["data"],
                             "selected generated CSR address changed executable bytes")
            self.assertEqual(legacy["sha256"], generated["sha256"])
            self.assertIsNone(legacy["csr_base_header_sha256"])
            self.assertEqual(len(generated["csr_base_header_sha256"]), 64)
            header = (root / "generated/soc_variant_csr_bases.h").read_text()
            self.assertIn("#define SOC_DMA0_CSR SOC_CSR_COMPUTE0_DMA_BASE", header)
            self.assertIn("SOC_CSR_COMPUTE0_DMA_BASE", header)
            self.assertNotIn("#define SOC_PCIE_CTRL SOC_CSR_PCIE0_CTRL_BASE", header)
            missing = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
            missing["address_map"]["config"] = [
                row for row in missing["address_map"]["config"]
                if row["name"] != "compute0.dma"
            ]
            with self.assertRaisesRegex(ValueError, "missing selected SoC CSR"):
                compile_firmware(missing, root / "invalid")
            selected = compile_firmware(cfg, root / "pcie", pcie_host_mode=True,
                                        pcie_outbound_mode=True)
            self.assertIn("SOC_PCIE_CTRL", selected["defines"])
            pcie_header = (root / "pcie/soc_variant_csr_bases.h").read_text()
            self.assertIn("#define SOC_PCIE_CTRL SOC_CSR_PCIE0_CTRL_BASE", pcie_header)

    def test_generated_and_legacy_linked_cpu_images_are_identical(self):
        for tool in ("clang", "llvm-objcopy", "ld.lld"):
            if not shutil.which(tool):
                self.skipTest(f"missing test-specific RV32I compiler tool: {tool}")
        cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        with tempfile.TemporaryDirectory(prefix="csr-fw-") as tmp:
            old = compile_firmware(cfg, Path(tmp)/"legacy",
                                   use_legacy_dma_csr=True)
            generated = compile_firmware(cfg, Path(tmp)/"generated",
                                         use_generated_dma_csr=True)
            production = compile_firmware(cfg, Path(tmp)/"production")
            self.assertTrue(production["generated_dma_csr_enabled"])
            self.assertFalse(old["generated_dma_csr_enabled"])
            self.assertEqual(len(production["generated_dma_csr_header_sha256"]), 64)
            self.assertEqual(production["data"], generated["data"])
            self.assertEqual(old["sha256"], generated["sha256"],
                             "generated header changed real CPU firmware instructions")
            self.assertEqual(old["data"], generated["data"])
            self.assertEqual(len(old["data"]), len(generated["data"]))
            self.assertEqual(old["hook"], generated["hook"])
            self.assertEqual(old["defines"], generated["defines"])
            self.assertTrue((Path(tmp)/"generated/csr/soc_dma_shim_regs.h").is_file())
            self.assertTrue((Path(tmp)/"generated/csr/soc_dma_shim_map.json").is_file())


if __name__ == "__main__":
    unittest.main()
