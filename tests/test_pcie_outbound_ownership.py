"""Merge-blocking ownership contract for #76 full-chip DMA.

PCIe Root Complex and TLP BFMs are allowed *outside* device RTL.
The full-chip test may not issue internal requester descriptors; the real
CPU/Config-NoC/CSR block must own that traffic. Isolated unit tests are
intentionally not included in this full-chip-only policy.
"""
import ast
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]


class OutboundOwnershipContract(unittest.TestCase):
    def test_no_internal_descriptor_pins_exported_to_fullchip(self):
        import sys
        sys.path.insert(0,str(ROOT/"tools"))
        import pcie_outbound
        external="\n".join(pcie_outbound.top_ports()+pcie_outbound.instance_ports())
        self.assertNotRegex(external,r"(s_axis_(read|write)_desc|m_axis_(read|write)_desc)")
        self.assertIn("tx_wr_req_tlp",external)
        self.assertIn("tx_rd_req_tlp",external)
        self.assertIn("rx_cpl_tlp",external)
        internal=pcie_outbound.csr_ports()
        for name in ("s_axis_read_desc_valid","s_axis_write_desc_valid",
                     "m_axis_read_desc_status_valid",
                     "m_axis_write_desc_status_valid"):
            self.assertEqual(internal[name],name)
        self.assertIn("dma_if_pcie",pcie_outbound.requester_lines())
        self.assertIn("logic s_axis_write_desc_valid;",pcie_outbound.requester_lines())

    def test_host_participant_never_issues_internal_descriptors(self):
        file=ROOT/"dv/pcie0/host_adapter.py"
        source=file.read_text()
        tree=ast.parse(source,filename=str(file))
        forbidden=re.compile(r"^(s_axis_(read|write)_desc|m_axis_(read|write)_desc)")
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute) and forbidden.match(node.attr):
                self.fail(f"Cocotb touches internal device DMA descriptor: {node.attr}")
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                self.assertNotRegex(node.value,r"^s_axis_(read|write)_desc")
        self.assertNotIn("DescSource",source)
        self.assertNotIn("define_stream",source)
        self.assertNotIn("self.out_wr_desc",source)
        self.assertNotIn("self.out_rd_desc",source)
        self.assertIn("self.bar.write(",source)
        self.assertIn("self.host_mem",source)

    def test_real_config_noc_owns_requester_and_firmware(self):
        gen=(ROOT/"tools/full_chip_gen.py").read_text()
        csr=(ROOT/"rtl/adapters/pcie_requester_axi_regs.sv").read_text()
        fw=(ROOT/"sw/dma/tests/cpu_dma_run.c").read_text()
        api=(ROOT/"sw/pcie/pcie_requester.h").read_text()
        build=(ROOT/"tools/regress.py").read_text()
        self.assertIn("pcie_requester_axi_regs",gen)
        self.assertIn("**pcie_outbound.csr_ports()",gen)
        self.assertIn("'live_pcie_requester_axi4_lite'",gen)
        self.assertIn("pcie_requester_axi_regs.sv",build)
        self.assertIn("axi_to_axi_lite",csr)
        self.assertIn("s_axis_write_desc_valid = wr_pending_q",csr)
        self.assertIn("s_axis_read_desc_valid = rd_pending_q",csr)
        self.assertIn("#ifdef SOC_PCIE_OUTBOUND",fw)
        self.assertIn("soc_pcie_transfer(requester,false",fw)
        self.assertIn("soc_pcie_transfer(requester,true",fw)
        self.assertIn("soc_pcie_fence()",api)
        self.assertIn("SOC_PCIE_WR_COMMAND",api)
        self.assertIn("SOC_PCIE_RD_COMMAND",api)
        self.assertNotIn("requester_descriptor_control\":\"cocotb",(
            ROOT/"dv/pcie0/host_adapter.py").read_text())

    def test_isolated_requester_unit_test_is_allowed(self):
        smoke=(ROOT/"dv/pcie0/outbound_smoke.py").read_text()
        self.assertIn("DescSource",smoke)
        self.assertIn("isolated",smoke.lower())


if __name__=="__main__":
    unittest.main()
