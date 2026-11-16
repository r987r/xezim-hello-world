"""Synthetic log fixtures only; actual OpenPCIe Verilator remains authority."""
import unittest
from tools.pcie_mem_ingress_evidence import check
from tests.test_pcie_bar0_evidence import sample

PLAN = "a"*64
GOOD = (
  "PCIE_RC_BAR_MWR_TX: action=write_bar0 addr=80001100 data=a5c36e91 plan="+PLAN+"\n"
  "PCIE_EP_INTERNAL_CFG_RX_BEAT: data=01000040 keep=f last=0 at 10000\n"
  "PCIE_EP_INTERNAL_CFG_RX_BEAT: data=0f060100 keep=f last=0 at 10010\n"
  "PCIE_EP_MEM_TLP_BACKPRESSURE: original endpoint valid ready=0 data=01000040 keep=f last=0 at 10020\n"
  "PCIE_EP_INTERNAL_CFG_RX_BEAT: data=00110080 keep=f last=0 at 10020\n"
  "PCIE_EP_INTERNAL_CFG_RX_BEAT: data=a5c36e91 keep=f last=1 at 10030\n"
  "PCIE_SCN_DRIVER: plan="+PLAN+" action=write_bar0 stage=driver_done\n"
)

class MemIngressEvidence(unittest.TestCase):
    def test_exact_original_packet_and_no_fake_axi_completion(self):
        result=check(sample()+GOOD)
        self.assertTrue(result["qualified_original_memwrite_ingress"],result["issues"])
        self.assertEqual(result["original_host_bus_address"],"0x80001100")
        self.assertEqual(result["original_host_word"],"0xa5c36e91")
        self.assertEqual(result["noc_sram_bytes"],"unmeasured")
        self.assertFalse(result["axi_accepted"])
        self.assertEqual(result["pci_completion"],"not_applicable_posted_write")

    def test_modified_wire_bytes_missing_words_or_fake_completion_fail(self):
        original=sample()+GOOD
        for wrong in (
            original.replace("data=00110080 keep=f last=0","data=00110000 keep=f last=0"),
            original.replace("data=a5c36e91 keep=f last=1","data=916ec3a5 keep=f last=1"),
            original.replace("data=01000040 keep=f last=0 at 10000","data=01000000 keep=f last=0 at 10000"),
            original.replace("data=0f060100 keep=f last=0 at 10010","data=0e060100 keep=f last=0 at 10010"),
            original.replace("keep=f last=1 at 10030","keep=f last=0 at 10030"),
            original.replace("PCIE_EP_MEM_TLP_BACKPRESSURE:","NOT_BACKPRESSURED:"),
            original.replace("action=write_bar0 stage=driver_done","action=write_bar0 stage=issued"),
            original.replace("PCIE_RC_CFG_MSE_ENABLED: command=00000002 completions=6",""),
        ):
            with self.subTest(wrong=wrong[-105:]):
                self.assertFalse(check(wrong)["qualified_original_memwrite_ingress"])


if __name__=="__main__":
    unittest.main()
