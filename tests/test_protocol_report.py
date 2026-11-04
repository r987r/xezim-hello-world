"""Generic protocol capture/export tests; no new bus drivers or monitors."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from dv.common.protocol_trace import ProtocolTrace, json_fields
import protocol_report
import regress


class ProtocolReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def writer(self, max_events=100):
        return ProtocolTrace(self.root / "protocol-events.jsonl",
                             {"mac.rx": "ethernet", "registers": "apb"},
                             max_events=max_events)

    def make(self):
        t = self.writer()
        t.event("mac.rx", "frame_rx", 10000,
                {"ethertype": "0x0800", "size_bytes": 1024, "payload": 2**64+3})
        t.transaction("registers", "read", 10000, 30000,
                      identifier=0, fields={"address": "0x1000000", "data": "0xbace"})
        t.close()
        return t

    def test_external_vip_adapter_and_html(self):
        self.make()
        records = protocol_report.parse_capture(
            self.root / "protocol-events.jsonl",
            {"mac.rx":"ethernet","registers":"apb"})
        self.assertEqual(records["events"], {"mac.rx":1, "registers":1})
        self.assertEqual([x["protocol"] for x in records["records"]],
                         ["ethernet","apb"])
        self.assertEqual(records["records"][0]["fields"]["payload"], hex(2**64+3))
        plan = {"target":"protocol-smoke", "engine":"cocotb-verilator",
                "report":{"protocols":{"sources":{"mac.rx":"ethernet","registers":"apb"}}}}
        result = protocol_report.build(self.root,plan)
        self.assertTrue(result["capture_complete"])
        self.assertEqual(len(result["records"]),2)
        page=(self.root/"protocols.html").read_text()
        self.assertIn("Protocol Run Explorer",page)
        self.assertIn('id="timeline"',page)
        self.assertIn("ethernet",page)
        self.assertIn("apb",page)
        self.assertEqual(json.loads((self.root/"protocol-transactions.json").read_text())["schema_version"],1)

    def test_large_integer_and_html_are_lossless_safe(self):
        fields = json_fields({"address":2**64,"unsafe":"</script><script>alert(1)</script>"})
        self.assertEqual(fields["address"],hex(2**64))
        data = {"run":{"target":"foo"},"sources":[],"issues":[],
                "capture_complete":True,"records":[{"fields":fields}]}
        protocol_report.render(data,self.root/"protocols.html")
        html=(self.root/"protocols.html").read_text()
        self.assertNotIn("</script><script>alert",html)
        self.assertIn("\\u003c/script>",html)

    def test_capture_without_end_marker_rejected(self):
        self.make()
        path=self.root/"protocol-events.jsonl"
        path.write_text("\n".join(path.read_text().splitlines()[:-1])+"\n")
        with self.assertRaisesRegex(ValueError,"missing one or more required"):
            protocol_report.parse_capture(path,{"mac.rx":"ethernet","registers":"apb"})

    def test_capture_with_failure_end_marker_rejected(self):
        t=self.writer()
        t.event("mac.rx","frame_rx",100)
        t.close("fail","timeout")
        with self.assertRaisesRegex(ValueError,"ended with failure"):
            protocol_report.parse_capture(self.root/"protocol-events.jsonl",
                                          {"mac.rx":"ethernet","registers":"apb"})

    def test_uncataloged_protocol_event_rejected(self):
        t=self.writer()
        with self.assertRaisesRegex(ValueError,"uncataloged"):
            t.event("not.registered","write",10)
        t.close("fail")

    def test_overflow_rejected(self):
        t=self.writer(max_events=1)
        t.event("mac.rx","frame_rx",1)
        with self.assertRaisesRegex(AssertionError,"overflow"):
            t.event("mac.rx","frame_rx",2)
        t.close("fail")

    def test_decreasing_timestamp_and_negative_duration_rejected(self):
        t=self.writer()
        t.event("mac.rx","frame_rx",100)
        with self.assertRaisesRegex(AssertionError,"out-of-order"):
            t.event("mac.rx","frame_rx",90)
        with self.assertRaisesRegex(ValueError,"precedes"):
            t.transaction("registers","read",300,200)
        t.close("fail")

    def test_generic_report_fails_closed_on_missing_capture(self):
        plan = {"target":"missing","engine":"cocotb-verilator",
                "report":{"protocols":{"sources":{"mac.rx":"ethernet"}}}}
        result=protocol_report.build(self.root,plan)
        self.assertFalse(result["capture_complete"])
        self.assertIn("missing",result["issues"][0])
        self.assertTrue((self.root/"protocols.html").exists())

    def test_axi_adapter_uses_existing_correlated_rows(self):
        payload={"run":{"target":"axi","engine":"cocotb-verilator","result":{"passed":True}},
                 "sections":{"axi":{"monitors":[{"id":"cpu","role":"initiator",
                       "actor":{"kind":"verification_bfm"}}],
                    "transactions":[{"monitor":"cpu","operation":"read","axi_id":"0x0",
                                     "start_ps":10000,"end_ps":30000,
                                     "status":"complete","address":"0x1000",
                                     "region":"sram","response":"0x0",
                                     "beats":[{"data":"0x21"}],"expected_beats":1,
                                     "role":"initiator","plane":"data",
                                     "actor":{"label":"CPU0"},"issues":[]}]}}}
        plan={"target":"axi","engine":"cocotb-verilator","report":{"axi":{"catalog":"test"}}}
        data=protocol_report.build(self.root,plan,axi_payload=payload)
        self.assertEqual(data["sources"][0]["protocol"],"axi4")
        self.assertEqual(data["records"][0]["start_ps"],10000)
        self.assertEqual(data["records"][0]["end_ps"],30000)
        self.assertEqual(data["records"][0]["fields"]["address"],"0x1000")
        self.assertTrue(data["capture_complete"])

    def test_regression_validates_protocol_catalog_without_axi(self):
        config=regress.load_config(ROOT/"config/regression.yaml")
        import copy, yaml
        new=copy.deepcopy(config)
        new["tests"]["dma-rtl"]["report"]={"protocols":{"sources":{"dma.engine":"axi-stream"}}}
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"regression.yml"
            p.write_text(yaml.safe_dump(new))
            self.assertIn("report",regress.load_config(p)["tests"]["dma-rtl"])
            new["tests"]["dma-rtl"]["report"]["protocols"]["sources"]={"Bad Name":"axi-stream"}
            p.write_text(yaml.safe_dump(new))
            with self.assertRaisesRegex(ValueError,"invalid generic protocol"):
                regress.load_config(p)


if __name__=="__main__":
    unittest.main()
