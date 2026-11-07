"""Full-chip DDR DFI probe contract and protocol event conversion tests."""
import json
from pathlib import Path
import re
import tempfile
import unittest

from dfi_probe_contract import PHASES,BANKS,DFI_FIELDS,BANK_FIELDS
from dfi_probe import DFIProbe,get_internal_pins
from dfi_to_protocol import export_fullchip_probe,DFI,BANK
from dv.common.protocol_trace import ProtocolTrace


ROOT=Path(__file__).resolve().parents[3]


class _Value:
    def __init__(self,value):
        self.value=value


class FullChipDFIContractTests(unittest.TestCase):
    def test_only_72_audited_readonly_aliases_and_no_memory_arrays(self):
        rtl=(ROOT/"rtl/memory/ddr4/soc_fullchip_target.sv").read_text()
        aliases=re.findall(
            r"\bdfi_obs_(?:p\d+|bank\d+)_[A-Za-z0-9_]+\s*/\*\s*verilator\s+public_flat_rd\s*\*/",
            rtl)
        self.assertEqual(len(aliases),PHASES*len(DFI_FIELDS)+BANKS*len(BANK_FIELDS))
        for p in range(PHASES):
            for name in DFI_FIELDS:
                key=f"dfi_obs_p{p}_{name}"
                self.assertEqual(rtl.count(key),1)
                self.assertIn(f"u_controller.soc_ddrphy_dfi_p{p}_{name}",rtl)
        for b in range(BANKS):
            for name in BANK_FIELDS:
                key=f"dfi_obs_bank{b}_{name}"
                self.assertEqual(rtl.count(key),1)
                self.assertIn(f"u_controller.soc_ddrphy_bankmodel{b}_{name}",rtl)
        self.assertNotIn("public_flat_rw",rtl.replace("--public-flat-rw",""))

    def test_alias_reader_preserves_exact_4phases_16banks(self):
        class Fake:
            pass
        dut=Fake()
        for p in range(PHASES):
            for field in DFI_FIELDS:
                setattr(dut,f"dfi_obs_p{p}_{field}",_Value(p+1))
        for bank in range(BANKS):
            for field in BANK_FIELDS:
                setattr(dut,f"dfi_obs_bank{bank}_{field}",_Value(bank+1))
        phases,banks=get_internal_pins(dut,fullchip_aliases=True)
        self.assertEqual(len(phases),4)
        self.assertEqual(len(banks),16)
        self.assertEqual(phases[3]["address"],4)
        self.assertEqual(banks[15]["write_port_we"],16)

    def test_fullchip_probe_events_export_to_original_protocol_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            trace=ProtocolTrace(path/"protocol-events.jsonl",{
                DFI:{"protocol":"dfi","clock_domain":"ddr_source_clk"},
                BANK:{"protocol":"dfi","clock_domain":"ddr_source_clk"}
            })
            probe=DFIProbe(path,scope="fullchip_litedram_dfi_sim")
            defaults=[dict(cs_n=1,act_n=1,ras_n=1,cas_n=1,we_n=1,
                           bank=0,address=0,rddata_en=0,rddata_valid=0,
                           wrdata_en=0) for _ in range(4)]
            storage=[dict(read=0,write_port_we=0) for _ in range(16)]
            p=[dict(v) for v in defaults]
            p[0].update(cs_n=0,ras_n=1,cas_n=0,we_n=1,bank=2,address=0x120)
            probe.record(5000,p,storage,"run",10000)
            p=[dict(v) for v in defaults]
            p[1].update(cs_n=0,ras_n=1,cas_n=0,we_n=0,bank=2,address=0x120)
            storage[2]["write_port_we"]=0xff
            probe.record(15000,p,storage,"run",10000)
            probe.finish("pass")
            counts=export_fullchip_probe(path,trace)
            trace.close("pass")
            self.assertEqual(counts["dfi_read"],1)
            self.assertEqual(counts["dfi_write"],1)
            output=[json.loads(line) for line in
                    (path/"protocol-events.jsonl").read_text().splitlines()]
            names=[row["name"] for row in output if row["type"]=="event"]
            self.assertEqual(names,["rd","wr","storage_write"])
            self.assertTrue(all(row["type"]!="transaction" for row in output))
            self.assertEqual(output[-1]["status"],"pass")

    def test_export_rejects_standalone_scope_in_fullchip_context(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            probe=DFIProbe(path)
            probe.record(5000,[dict(cs_n=1,act_n=1,ras_n=1,cas_n=1,we_n=1,
                                    bank=0,address=0,rddata_en=0,
                                    rddata_valid=0,wrdata_en=0) for _ in range(4)],
                         [dict(read=0,write_port_we=0) for _ in range(16)],
                         "init",10000)
            probe.finish("pass")
            trace=ProtocolTrace(path/"protocol-events.jsonl",{
                DFI:{"protocol":"dfi"},BANK:{"protocol":"dfi"}})
            with self.assertRaisesRegex(ValueError,"wrong full-chip"):
                export_fullchip_probe(path,trace)
            trace.close("fail","intentional negative contract test")


if __name__=="__main__":
    unittest.main()
