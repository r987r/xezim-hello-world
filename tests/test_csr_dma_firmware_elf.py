"""Compile and link actual RV32I CPU DMA in both CSR header modes."""
from pathlib import Path
import tempfile
import unittest
import shutil

import yaml

from tools.cpu_dma_firmware import compile_firmware

ROOT = Path(__file__).resolve().parents[1]


class CpuGeneratedCsrImageTests(unittest.TestCase):
    def test_generated_and_legacy_linked_cpu_images_are_identical(self):
        for tool in ("clang", "llvm-objcopy", "ld.lld"):
            if not shutil.which(tool):
                self.skipTest(f"missing test-specific RV32I compiler tool: {tool}")
        cfg = yaml.safe_load((ROOT / "config/soc.yaml").read_text())
        with tempfile.TemporaryDirectory(prefix="csr-fw-") as tmp:
            old = compile_firmware(cfg, Path(tmp)/"legacy")
            generated = compile_firmware(cfg, Path(tmp)/"generated",
                                         use_generated_dma_csr=True)
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
