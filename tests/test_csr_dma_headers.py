"""SystemRDL-generated existing DMA CSR source/ABI checks."""
import json
from pathlib import Path
import re
import tempfile
import unittest

# SystemRDL is intentionally optional for the normal NoC/SoC test environment.
# The dedicated csr-firmware workflow installs the pinned compiler and executes
# these tests unconditionally; don't break unrelated unit-test discovery.
try:
    from tools import csr_dma_headers
except ModuleNotFoundError as exc:
    if exc.name != "systemrdl":
        raise
    csr_dma_headers = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(csr_dma_headers is None, "requires pinned CSR compiler; enforced by csr-firmware CI")
class DmaCsrTests(unittest.TestCase):
    def test_rdl_layout_and_generated_legacy_aliases(self):
        regs = csr_dma_headers.extract()
        self.assertEqual([r["offset"] for r in regs], [0, 4, 8, 12])
        self.assertEqual([r["name"] for r in regs], ["head_lo", "head_hi", "command", "status"])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            csr_dma_headers.emit(out)
            csr_dma_headers.emit(out, check=True)
            header = (out / "soc_dma_shim_regs.h").read_text()
            for name in ("HEAD_LO", "HEAD_HI", "COMMAND", "STATUS"):
                self.assertIn(f"#define SOC_DMA_REG_{name} SOC_DMA_SHIM_{name}_OFFSET", header)
            for name in ("SUBMIT", "IRQ_ACK", "APB_BUSY", "IRQ", "APB_ERROR", "RAW_IRQ"):
                self.assertIn(f"#define SOC_DMA_{'CMD' if name in ('SUBMIT','IRQ_ACK') else 'STATUS'}_{name}", header)
            metadata = json.loads((out / "soc_dma_shim_map.json").read_text())
            self.assertEqual([i["name"] for i in metadata["instances"]],
                             ["compute0.dma", "compute1.dma"])
            self.assertTrue(metadata["registers_are_external"])
            self.assertEqual(metadata["instances"][0]["registers"][-1]["address"], "0x4000000c")

    def test_legacy_header_offsets_equal_rdl(self):
        old = (ROOT / "sw/dma/dma.h").read_text()
        found = dict(re.findall(r"#define\s+SOC_DMA_REG_(HEAD_LO|HEAD_HI|COMMAND|STATUS)\s+(0x[0-9a-fA-F]+)u", old))
        self.assertEqual({key: int(value, 16) for key, value in found.items()},
                         {r["name"].upper(): r["offset"] for r in csr_dma_headers.extract()})
        # No claim that the generated definitions have already replaced this source:
        # the production migration is a separate, full CPU firmware regression.

    def test_drift_check_detects_stale_generated_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            csr_dma_headers.emit(tmp)
            path = Path(tmp) / "soc_dma_shim_regs.h"
            path.write_text(path.read_text().replace("SOC_DMA_REG_COMMAND", "BAD_LEGACY"))
            with self.assertRaisesRegex(csr_dma_headers.DmaCsrError, "differ"):
                csr_dma_headers.emit(tmp, check=True)


if __name__ == "__main__":
    unittest.main()
