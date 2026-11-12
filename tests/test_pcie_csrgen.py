"""Contract tests for generated PCIe endpoint pre-link CSRs.

No behavioral model is substituted for real PeakRDL output. Source
compilation, generated AXI4-Lite module, C header and catalog are tested
independently of the still-unconnected CPU0 Config-NoC frontdoor.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.pcie_csrgen import (
    RDL, SOC, PcieCsrError, compile_rdl, config_aperture,
    execute, generate, header, registers,
)


class PcieCsrGenerationTests(unittest.TestCase):
    def test_source_compiles_and_preserves_existing_pcie_requester_abi(self):
        aperture = config_aperture(SOC)
        self.assertEqual(aperture["base"], 0x40040000)
        self.assertEqual(aperture["size"], 0x10000)
        rows=registers(compile_rdl(RDL), aperture)
        self.assertEqual([r["offset"] for r in rows],
                         [0x1000,0x1004,0x1008,0x100c,
                          0x1010,0x1014,0x1018])
        self.assertGreaterEqual(min(r["offset"] for r in rows),0x40)
        self.assertEqual(rows[2]["fields"][0]["mask"],"0x00000001")
        self.assertEqual(rows[2]["fields"][1]["mask"],"0x00000002")
        self.assertTrue(all(x["access"] == "r" for x in rows[-1]["fields"]))
        self.assertEqual(rows[1]["address"],0x40041004)
        self.assertEqual(rows[4]["offset"],0x1010)
        self.assertEqual(rows[4]["fields"][0]["mask"],"0xfffffff0")
        self.assertEqual(rows[5]["fields"][0]["mask"],"0x00000002")
        # Host-owned Type-0 BAR0/MSE must be CPU read-only hardware aliases.
        self.assertEqual([r["access"] for r in rows[4:]], ["r","r","r"])
        self.assertEqual([r["address"] for r in rows[4:]],
                         [0x40041010,0x40041014,0x40041018])
        h=header(rows,aperture["base"],aperture["size"])
        self.assertIn("SOC_PCIE_EP_CTRL_BASE UINT32_C(0x40040000)",h)
        self.assertIn("SOC_PCIE_EP_CONTROL_COMMIT_MASK UINT32_C(0x00000001)",h)
        self.assertIn("SOC_PCIE_EP_STATUS_VIOLATION_MASK UINT32_C(0x00000008)",h)
        self.assertIn("SOC_PCIE_EP_HOST_COMMAND_MEMORY_SPACE_ENABLE_MASK",h)
        self.assertNotIn("SOC_PCIE_WR_HOST_LO",h)

    def test_real_peakrdl_regblock_and_check_generated(self):
        with TemporaryDirectory() as temp:
            out=Path(temp)/"result"
            self.assertEqual(execute(SOC,RDL,out,False),0)
            self.assertEqual(execute(SOC,RDL,out,True),0)
            self.assertTrue((out/"soc_pcie_ep_prelink_regs.h").is_file())
            rtl=out/"rtl/soc_pcie_ep_prelink_regblock.sv"
            self.assertTrue(rtl.is_file())
            self.assertIn("module soc_pcie_ep_prelink_regblock",rtl.read_text())
            data=json.loads((out/"csr-map.json").read_text())
            self.assertFalse(data["generated_rtl_attached_to_full_chip"])
            self.assertFalse(data["cpu0_frontdoor_verified"])
            self.assertEqual(data["host_pcie_configuration_space"],
                             "distinct_vendor_type0_rdl")
            self.assertEqual(len(data["registers"]),7)
            aliases=data["shared_host_state_aliases"]
            self.assertEqual(aliases["host_type0_bar0"]["cpu_dbi_offset"],"0x1010")
            self.assertEqual(aliases["host_type0_bar0"]["pcie_config_offset"],"0x10")
            self.assertEqual(aliases["host_type0_bar0"]["cpu_access"],"read_only")
            self.assertEqual(aliases["host_type0_command_mse"]["pcie_config_offset"],"0x04")
            self.assertEqual(aliases["host_type0_command_mse"]["cpu_access"],"read_only")
            (out/"soc_pcie_ep_prelink_regs.h").write_text("illegal manual edit")
            self.assertEqual(execute(SOC,RDL,out,True),1)

    def test_reject_abi_mutations(self):
        original=RDL.read_text()
        cases=[
            ("bar0_aperture @0x1000","bar0_aperture @0x0000"),
            ("bar0_target @0x1004","bar0_target @0x1010"),
            ("sw = r; hw = w; reset = 0;","sw = rw; hw = w; reset = 0;"),
            ("} commit[0:0];","} commit[2:2];"),
            ("} pci_bus_base[31:4];","} pci_bus_base[31:0];"),
            ("} memory_space_enable[1:1];","} memory_space_enable[2:2];"),
            ("swwe;",""),
        ]
        with TemporaryDirectory() as temp:
            path=Path(temp)/"incorrect.rdl"
            for old,new in cases:
                with self.subTest(mutation=old):
                    self.assertIn(old,original)
                    path.write_text(original.replace(old,new,1))
                    with self.assertRaises(PcieCsrError):
                        registers(compile_rdl(path),config_aperture(SOC))

    def test_alias_cannot_be_cpu_writable_or_unbound_from_hardware(self):
        original=RDL.read_text()
        old="        } pci_bus_base[31:4];"
        self.assertIn(old,original)
        for before, after in (
            ("            sw = r;\n            hw = w;\n            reset = 0;",
             "            sw = rw;\n            hw = w;\n            reset = 0;"),
            ("            sw = r;\n            hw = w;\n            reset = 0;",
             "            sw = r;\n            hw = r;\n            reset = 0;"),
        ):
            with self.subTest(replacement=after), TemporaryDirectory() as temp:
                p=Path(temp)/"invalid_alias.rdl"
                self.assertIn(before,original)
                p.write_text(original.replace(before,after,1))
                with self.assertRaises(PcieCsrError):
                    registers(compile_rdl(p),config_aperture(SOC))

    def test_reject_stale_region_or_unowned_destination(self):
        cfg=SOC.read_text()
        self.assertIn("name: pcie0.ctrl",cfg)
        with TemporaryDirectory() as temp:
            file=Path(temp)/"soc.yaml"
            file.write_text(cfg.replace("name: pcie0.ctrl","name: pcie9.ctrl"))
            with self.assertRaisesRegex(PcieCsrError,"exactly one"):
                config_aperture(file)


if __name__=="__main__":
    unittest.main()
