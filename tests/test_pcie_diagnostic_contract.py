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

    def test_high_bar_uses_rc_tlp_address_space_not_low_host_pool(self):
        # The low host pool ends before BAR0; the reserved MSI range
        # begins at 0x80000000. Register ONLY the 4KiB BAR TLP region.
        script = Path("dv/pcie0/noc_smoke.py").read_text()
        self.assertIn("rc.mem_address_space.register_region(", script)
        self.assertIn("host_bar = 0x80001000", script)
        self.assertIn("bar_size = 0x1000", script)
        self.assertIn("rc.mem_region, host_bar, bar_size, offset=None", script)
        self.assertIn("matches[0][3] is rc.mem_region", script)
        self.assertNotIn("rc.mem_pool.register_region(rc.mem_region, 0x80000000", script)
        self.assertNotIn("rc.mem_region, 0x80000000, 0x100000", script)
        self.assertIn("sram_write_count", script)
        self.assertIn("sram_read_count", script)


if __name__ == "__main__":
    unittest.main()
