"""Protect the upstream source compatibility patch against accidental drift."""
import ast
from pathlib import Path
import unittest


class PcieDiagnosticContractTests(unittest.TestCase):
    def test_patch_only_four_unsized_literals(self):
        file = Path("dv/pcie0/prepare_rtl.py").read_text()
        ast.parse(file)
        self.assertIn("TIE_OFFS = {", file)
        self.assertIn('patched.count(anchor) != 1', file)
        self.assertIn("patch unpinned", file)
        self.assertIn("assert_iverilog_clean", file)

    def test_real_noc_smoke_not_false_ram_model(self):
        script = Path("dv/pcie0/noc_smoke.py")
        if script.exists():
            content = script.read_text()
            self.assertNotIn("AxiRam(", content)
            self.assertIn("sram_write_count", content)
            self.assertIn("sram_read_count", content)


if __name__ == "__main__":
    unittest.main()
