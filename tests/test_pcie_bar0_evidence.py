"""Fail-closed regression for physical RC->TLP->EP->AXI BAR0 endianness.

These are intentionally synthetic LOG FIXTURES: the cross-provider Verilator
Actions job is the authoritative hardware proof. We must not claim TLP/NoC
bytes from software-only tests.
"""
from __future__ import annotations

import unittest
from tools.pcie_bar0_evidence import check

BEGIN="PCIE_RC_CFG_BEGIN: action=enumerate_bar0 plan="+"a"*64+" bar=0 aperture=4096 base=80001000"
CASES=[
    ("Wr",0x10,0xffffffff,0x0a,0,None),
    ("Rd",0x10,None,0x4a,4,0xfffff000),
    ("Wr",0x10,0x80001000,0x0a,0,None),
    ("Rd",0x10,None,0x4a,4,0x80001000),
    ("Wr",0x04,0x00000002,0x0a,0,None),
    ("Rd",0x04,None,0x4a,4,0x00000002),
]


def sample():
    lines=[BEGIN]
    for tag,(op,addr,word,kind,bytes_,readback) in enumerate(CASES):
        if op=="Wr":
            lines.append(f"PCIE_RC_CFG_TX: CfgWr0 addr={addr:03x} data={word:08x} tag={tag}")
            lines.append(f"PCIE_EP_INTERNAL_CFG_RX_BEAT: data={word:08x} keep=f last=1 at {500+tag}")
            lines.append(f"PCIE_EP_BAR_CFG_AXI: AW=1 W=0 AR=0 awaddr={addr:03x} araddr={addr:03x} wdata={word:08x} committed=1 pending_aw=0 pending_w=0 probe=0 mask=fffff000 hostbase=00000000 readbar=0 rdldata=00000000 hostdata=00000000 at {600+tag}")
            lines.append(f"PCIE_EP_BAR_CFG_AXI: AW=0 W=1 AR=0 awaddr={addr:03x} araddr={addr:03x} wdata={word:08x} committed=1 pending_aw=1 pending_w=0 probe=0 mask=fffff000 hostbase=00000000 readbar=0 rdldata=00000000 hostdata=00000000 at {700+tag}")
            lines.append(f"PCIE_EP_INTERNAL_CFG_CPL_TX_BEAT: data=00000{tag:03x} keep=3 last=1 at {800+tag}")
        else:
            lines.append(f"PCIE_RC_CFG_TX: CfgRd0 addr={addr:03x} tag={tag}")
            lines.append(f"PCIE_EP_INTERNAL_CFG_RX_BEAT: data=00000000 keep=f last=1 at {500+tag}")
            lines.append(f"PCIE_EP_BAR_CFG_AXI: AW=0 W=0 AR=1 awaddr={addr:03x} araddr={addr:03x} wdata=00000000 committed=1 pending_aw=0 pending_w=0 probe=1 mask=fffff000 hostbase=80001000 readbar=0 rdldata=00000000 hostdata=00000000 at {600+tag}")
            lines.append(f"PCIE_EP_INTERNAL_CFG_CPL_TX_BEAT: data={readback:08x} keep=f last=1 at {800+tag}")
        lines.append(f"PCIE_RC_CFG_RX_CPL: tag={tag} status=0 type={kind:02x} bytes={bytes_} timestamp={1000+tag}")
        lines.append(f"PCIE_RC_CFG_RESULT: tag={tag} seen=1 status=0 bytes={bytes_} ok=1")
        if tag==1:
            lines.append("PCIE_RC_CFG_PROBE_OK: BAR0 mask=fffff000")
        if tag==3:
            lines.append("PCIE_RC_CFG_BAR_ASSIGNED: BAR0 bus=80001000")
        if tag==5:
            lines.append("PCIE_RC_CFG_MSE_ENABLED: command=00000002 completions=6")
    lines.append("PCIE_SCN_DRIVER: plan="+"a"*64+" action=enumerate_bar0 stage=driver_done")
    return "\n".join(lines)+"\n"


class PcieBar0EvidenceTests(unittest.TestCase):
    def test_six_genuine_config_transactions_preserve_word_value(self):
        r=check(sample())
        self.assertTrue(r["qualified_over_link_bar0"],r["issues"])
        self.assertEqual(len(r["transactions"]),6)
        self.assertEqual(r["transactions"][2]["endpoint_received_payload"],"0x80001000")
        self.assertEqual(r["transactions"][2]["axi_accepted_wdata"],"0x80001000")
        self.assertEqual(r["transactions"][4]["axi_accepted_wdata"],"0x2")
        self.assertEqual(r["noc_axi_transfer"],"unmeasured")

    def test_any_swapped_or_missing_payload_must_fail(self):
        good=sample()
        wrong=good.replace("wdata=80001000 committed", "wdata=00100080 committed")
        self.assertFalse(check(wrong)["qualified_over_link_bar0"])
        wrong=good.replace("data=80001000 keep=f last=1", "data=00100080 keep=f last=1")
        self.assertFalse(check(wrong)["qualified_over_link_bar0"])
        wrong=good.replace("wdata=00000002 committed", "wdata=02000000 committed")
        self.assertFalse(check(wrong)["qualified_over_link_bar0"])
        wrong=good.replace("data=00000002 keep=f last=1", "data=02000000 keep=f last=1")
        self.assertFalse(check(wrong)["qualified_over_link_bar0"])
        wrong=good.replace("data=80001000 keep=f last=1", "")
        self.assertFalse(check(wrong)["qualified_over_link_bar0"])

    def test_failed_completion_or_faked_bar_milestone_must_fail(self):
        s=sample()
        for wrong in (
            s.replace("PCIE_RC_CFG_RX_CPL: tag=3 status=0", "PCIE_RC_CFG_RX_CPL: tag=3 status=1"),
            s.replace("PCIE_RC_CFG_BAR_ASSIGNED: BAR0 bus=80001000", ""),
            s.replace("PCIE_RC_CFG_RESULT: tag=5 seen=1", "PCIE_RC_CFG_RESULT: tag=5 seen=0"),
            s.replace("PCIE_EP_INTERNAL_CFG_CPL_TX_BEAT: data=fffff000", "PCIE_EP_INTERNAL_CFG_CPL_TX_BEAT: data=00000000"),
            s.replace("PCIE_EP_INTERNAL_CFG_CPL_TX_BEAT: data=80001000", "PCIE_EP_INTERNAL_CFG_CPL_TX_BEAT: data=00100080"),
            s.replace("PCIE_RC_CFG_MSE_ENABLED: command=00000002 completions=6", ""),
            s + "PCIE_RC_CFG_FAIL: BAR0 sizing actual=0 expected=fffff000\n",
        ):
            with self.subTest(edited=wrong[:50]):
                self.assertFalse(check(wrong)["qualified_over_link_bar0"])

if __name__=="__main__":
    unittest.main()
