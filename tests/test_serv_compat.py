"""Fail closed if our external pinned SERV compatibility patch stops matching."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from serv_compat import ServPatchError, patch_serv_top


class ServCompatTests(unittest.TestCase):
    SOURCE = '''module serv_top;
   serv_decode decode (
     .i_wb_rdt           (i_wb_rdt[31:2]));
   serv_immdec immdec (
     .i_wb_rdt     (i_wb_rdt[31:7]));
endmodule
'''

    def test_keeps_range_on_both_module_inputs(self):
        result = patch_serv_top(self.SOURCE)
        self.assertIn('wire [31:2] decode_instr_indexed = i_wb_rdt[31:2];', result)
        self.assertIn('wire [31:7] imm_instr_indexed = i_wb_rdt[31:7];', result)
        self.assertIn('.i_wb_rdt           (decode_instr_indexed)', result)
        self.assertIn('.i_wb_rdt     (imm_instr_indexed)', result)
        self.assertNotIn('.i_wb_rdt           (i_wb_rdt[31:2])', result)
        self.assertNotIn('.i_wb_rdt     (i_wb_rdt[31:7])', result)

    def test_refuses_unknown_or_already_patched_versions(self):
        with self.assertRaises(ServPatchError):
            patch_serv_top('module serv_top; endmodule')
        with self.assertRaises(ServPatchError):
            patch_serv_top(patch_serv_top(self.SOURCE))

    def test_does_not_depend_on_untracked_vendor_source(self):
        self.assertFalse((ROOT / 'rtl' / 'adapters' / 'serv_cpu_adapter.sv').read_text().find('serv_rf_top') < 0)


if __name__ == '__main__':
    unittest.main()
