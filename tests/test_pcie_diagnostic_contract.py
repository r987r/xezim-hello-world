"""Protect the upstream source compatibility patch against accidental drift."""
import ast
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


class PcieDiagnosticContractTests(unittest.TestCase):
    def test_patch_only_four_unsized_literals(self):
        file = Path("dv/pcie0/prepare_rtl.py").read_text()
        ast.parse(file)
        self.assertIn("TIE_OFFS = {", file)
        self.assertIn('patched.count(anchor) != 1', file)
        self.assertIn("patch unpinned", file)
        self.assertIn("assert_iverilog_clean", file)

    def test_fullchip_bridge_source_and_probe_have_separate_owners(self):
        from dv.pcie0 import prepare_rtl

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vendor = root / "vendor"
            source = vendor / "rtl/pcie_axi_master.v"
            source.parent.mkdir(parents=True)
            source.write_text("\n".join(f".{name}(0)," for name in prepare_rtl.TIE_OFFS))
            lock = root / "lock.json"
            lock.write_text(json.dumps({"commit": "pinned", "rtl_modules": ["rtl/pcie_axi_master.v"]}))
            default = root / "normalized/pcie_axi_master.v"
            with patch.object(prepare_rtl, "LOCK", lock), \
                 patch.object(prepare_rtl, "UPSTREAM", vendor), \
                 patch.object(prepare_rtl, "OUTPUT", default), \
                 patch.object(prepare_rtl.subprocess, "check_output", return_value="pinned\n"), \
                 patch.object(prepare_rtl.subprocess, "run", return_value=types.SimpleNamespace(
                     returncode=0, stdout="", stderr="")) as compile_bridge:
                for owner in ("run-one", "run-two"):
                    normalized = root / "evidence" / owner / "variant/pcie_axi_master.v"
                    probe = root / "build" / owner / "pcie_bridge_check.vvp"
                    self.assertEqual(prepare_rtl.assert_iverilog_clean(
                        output=normalized, probe=probe), normalized)
                    argv = compile_bridge.call_args.args[0]
                    self.assertEqual(argv[argv.index("-o") + 1], str(probe))
                    self.assertIn(str(normalized), argv)
                    for name, value in prepare_rtl.TIE_OFFS.items():
                        self.assertIn(f".{name}({value}),", normalized.read_text())
                    self.assertFalse((normalized.parent / probe.name).exists())
                self.assertFalse(default.exists())
                self.assertEqual(prepare_rtl.assert_iverilog_clean(), default)

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
