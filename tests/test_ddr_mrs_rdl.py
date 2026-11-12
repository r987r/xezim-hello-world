"""Pinned SystemRDL compiler validation of the DDR4 virtual MR image catalog.

This is a protocol/firmware field view, NOT a generated AXI-Lite register
bank and NOT a replacement for LiteDRAM's native CSR JSON.
"""
import unittest
from pathlib import Path

from systemrdl import RDLCompiler
from rtl.memory.ddr4.mrs_check import RDL, catalog


class DDR4ModeRegisterRDL(unittest.TestCase):
    def test_compiler_and_protocol_catalog_agree(self):
        compiler = RDLCompiler()
        compiler.compile_file(str(RDL))
        root = compiler.elaborate(top_def_name="ddr4_mode_registers")
        registers = list(root.top.registers(unroll=True))
        expected = catalog()["registers"]
        self.assertEqual(len(registers), 7)
        for register in registers:
            name = register.inst_name
            self.assertTrue(name.startswith("mr"), name)
            index = int(name[2:])
            self.assertIn(index, expected)
            self.assertEqual(register.absolute_address, 4 * index)
            self.assertEqual(register.get_property("regwidth"), 32)
            compiled = {
                f.inst_name: (f.lsb, f.msb)
                for f in register.fields()
            }
            actual = {
                f["name"]: (f["lsb"], f["msb"])
                for f in expected[index]["fields"]
            }
            self.assertEqual(compiled, actual)
            for f in register.fields():
                self.assertEqual(getattr(f.get_property("sw"), "name").lower(), "r")
                self.assertEqual(getattr(f.get_property("hw"), "name").lower(), "w")


if __name__ == "__main__":
    unittest.main()
