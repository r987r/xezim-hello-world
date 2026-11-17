"""Source ownership, shared producer and evidence boundaries for project AXI tests."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from project_axi_smoke import selected_plan, ProjectAxiError
from unittest.mock import patch


class ProjectAxiSmokeContractTests(unittest.TestCase):
    def test_selected_project_must_have_own_compiled_source(self):
        # Unlike default gen/chip, this call must reject missing receipts.
        with self.assertRaises((ValueError, ProjectAxiError)):
            selected_plan("nonexistent_chip_id")

    def test_shared_real_cocotb_and_axi_adapter_no_synthetic_success(self):
        runner = (ROOT / "tools/project_axi_smoke.py").read_text()
        test = (ROOT / "dv/full_chip/test_project_axi.py").read_text()
        self.assertIn("from project_compile import selected", runner)
        self.assertIn("from sim_cocotb import main as simulate_cocotb", runner)
        self.assertIn("parse_filelist(filelist.read_text())", runner)
        self.assertIn("COCOTB_SIM=1", runner)
        self.assertIn("from cocotbext.axi import AxiBus, AxiMaster", test)
        self.assertIn('AxiBus.from_prefix(dut, "probe")', test)
        self.assertIn("master.write", test)
        self.assertIn("master.read", test)
        self.assertIn("bytes(r.data) == bytes(amended)", test)
        self.assertIn('"real_ddr_controller_qualified": False', test)

    def test_build_filelist_provenance_fails_closed(self):
        # No chosen chip is allowed to borrow another chip's result.
        from project_axi_smoke import run
        with self.assertRaises((ValueError, ProjectAxiError)):
            run("unknown_external_chip")


if __name__ == "__main__":
    unittest.main()
