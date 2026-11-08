"""Fast source-only SuperNoC wrapper interface sanity tests."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import supernoc_interface_check as contract


def texts():
    names = ("clk_i", "rst_ni",
             "m_compute0_local_data_cpu_awid",
             "m_ethernet0_local_data_packet_dma_awvalid",
             "m_pcie0_local_data_host_awvalid",
             "s_memory0_local_data_target_crossbar_awvalid")
    widths = {"m_compute0_local_data_cpu_awid": 4}
    declarations = [
        f"input logic [{widths[n]-1}:0] {n}" if n in widths else f"input logic {n}"
        for n in names
    ]
    ports = ",\n".join(declarations)
    binding = ",\n".join(f".{n}({n})" for n in names)
    return (f"module supernoc_tb (\n{ports}\n);\nsoc_noc u_noc (\n{binding}\n);\nendmodule\n",
            f"module soc_noc (\n{ports}\n);\nendmodule\n")


class GeneratedInterfaceTests(unittest.TestCase):
    def test_actual_generated_source_inventory(self):
        # This is a source binding test, never a synthetic proof of elaborated RTL.
        result = contract.check()
        self.assertEqual(result["ports_compared"], 899)
        self.assertFalse(result["compiler_elaboration_proven"])
        self.assertFalse(result["internal_floonoc_routes_proven"])
        self.assertFalse(result["runtime_axi_transactions_proven"])

    def test_wrong_pin_alias_and_missing_binding_fail(self):
        wrapper, core = texts()
        self.assertEqual(contract.verify(wrapper, core)["ports_compared"], 6)
        aliased = wrapper.replace(".rst_ni(rst_ni)", ".rst_ni(clk_i)")
        with self.assertRaisesRegex(contract.InterfaceContractError, "source binding"):
            contract.verify(aliased, core)
        missing = wrapper.replace(".rst_ni(rst_ni),\n", "")
        with self.assertRaisesRegex(contract.InterfaceContractError, "inventory mismatch"):
            contract.verify(missing, core)

    def test_width_direction_clock_reset_and_duplicate_fail(self):
        wrapper, core = texts()
        with self.assertRaisesRegex(contract.InterfaceContractError, "width/direction"):
            contract.verify(wrapper, core.replace("[3:0]", "[2:0]"))
        with self.assertRaisesRegex(contract.InterfaceContractError, "width/direction"):
            contract.verify(wrapper, core.replace("input logic rst_ni", "output logic rst_ni"))
        with self.assertRaisesRegex(contract.InterfaceContractError, "single-bit inputs"):
            wide = wrapper.replace("input logic clk_i", "input logic [1:0] clk_i")
            contract.verify(wide, core.replace("input logic clk_i", "input logic [1:0] clk_i"))
        with self.assertRaisesRegex(contract.InterfaceContractError, "duplicate binding"):
            contract.verify(wrapper.replace(".rst_ni(rst_ni),", ".rst_ni(rst_ni),\n.rst_ni(rst_ni),"), core)

    def test_unrecognized_complex_binding_fails_not_silently_skipped(self):
        wrapper, core = texts()
        with self.assertRaisesRegex(contract.InterfaceContractError, "unsupported binding"):
            contract.verify(wrapper.replace(".rst_ni(rst_ni)", ".rst_ni(~rst_ni)"), core)


if __name__ == "__main__":
    unittest.main()
