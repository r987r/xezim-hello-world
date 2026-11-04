"""Host-compile and run the freestanding C DMA descriptor allocator."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DmaSoftwareTests(unittest.TestCase):
    def test_freestanding_allocator(self):
        cc = shutil.which("cc")
        if not cc:
            self.skipTest("C compiler unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/"dma_allocator_test"
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-pedantic", str(ROOT/"sw/common/sram_pool.c"),
                            str(ROOT/"sw/dma/dma.c"),
                            str(ROOT/"sw/dma/tests/test_dma.c"), "-o", str(output)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([str(output)], check=True,
                                    capture_output=True, text=True)
            self.assertIn("PASS dma C descriptor allocator, chain ABI and CPU CSR driver", result.stdout)
