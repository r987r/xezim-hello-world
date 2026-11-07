"""Fail-closed source-derived diagram -> parsed RTL root-instance associations."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from rtl_instance_bindings import resolve


def graph(*ids):
    return {"nodes":[{"id":x,"module":"soc_boundary"} for x in ids]}


def parsed(*pairs):
    return {"modules":[
        {"name":"soc_top","instances":[
            {"name":name,"module":module,"source":"gen/chip/soc_top.sv",
             "conditional_generate":False} for name,module in pairs]},
        {"name":"picorv32_cpu_adapter","instances":[]},
        {"name":"soc_idma_engine","instances":[]},
        {"name":"axi_sram_target","instances":[]},
    ]}


class RtlBindingTests(unittest.TestCase):
    def test_real_root_instance_wins_over_similarly_named_helper(self):
        result=resolve(graph("compute0.cpu","compute0.dma","compute0.dma_csr"),
            parsed(("u_cpu_compute0","picorv32_cpu_adapter"),
                   ("u_dma_compute0","soc_idma_engine"),
                   ("u_dma_csr_compute0","soc_dma_regs")),top="soc_top")
        self.assertEqual(result["compute0.cpu"]["module"],"picorv32_cpu_adapter")
        self.assertEqual(result["compute0.dma"]["instance"],"u_dma_compute0")
        self.assertEqual(result["compute0.dma_csr"]["module"],"soc_dma_regs")
        self.assertFalse(result["compute0.dma"]["conditional_generate"])
        self.assertIn("not_elaborated",result["compute0.dma"]["evidence"])

    def test_optional_uninstantiated_ip_must_not_be_invented(self):
        result=resolve(graph("ethernet0.ip","pcie0.ip","ethernet0.sram"),
            parsed(("u_s_ethernet0_local_data_sram","axi_sram_target"),
                   ("u_reserved_s_ethernet0_local_config_controller_regs","axi_err_slv")),
            top="soc_top")
        self.assertEqual(result["ethernet0.ip"]["status"],"no_root_instance_match")
        self.assertEqual(result["pcie0.ip"]["status"],"no_root_instance_match")
        self.assertEqual(result["ethernet0.sram"]["module"],"axi_sram_target")

    def test_ambiguous_matching_does_not_choose_a_module(self):
        result=resolve(graph("compute0.cpu"),
            parsed(("u_cpu_compute0_a","a"),("u_cpu_compute0_b","b")),top="soc_top")
        self.assertEqual(result["compute0.cpu"]["status"],"ambiguous_root_instance")
        self.assertEqual(result["compute0.cpu"]["candidate_names"],
                         ["u_cpu_compute0_a","u_cpu_compute0_b"])
        self.assertNotIn("module",result["compute0.cpu"])

    def test_no_parser_yields_explicit_unavailable_and_wrong_top_fails(self):
        self.assertEqual(resolve(graph("compute0.cpu"),{"modules":[]},top="soc_top")
                         ["compute0.cpu"]["status"],"compiler_parse_unavailable")
        with self.assertRaisesRegex(ValueError,"missing generated top"):
            resolve(graph("compute0.cpu"),parsed(("u_cpu_compute0","cpu")),top="another_top")

    def test_existing_source_name_without_parsed_definition_is_opaque(self):
        result=resolve(graph("compute0.dma"),
            parsed(("u_dma_compute0","third_party_dma")),top="soc_top")
        self.assertEqual(result["compute0.dma"]["status"],"unique_root_instance")
        self.assertFalse(result["compute0.dma"]["parsed_module_available"])


if __name__=="__main__":
    unittest.main()
