"""Synthetic contract for the real-observation PCIe/AXI/SRAM correlator.

Uses the exact shapes exported by existing VIP/AXI reporters, without
simulating a PCIe bus or inventing a replacement BFM.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from pcie_latency_report import analyze, render_panel


class PcieLatencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.reads=[]
        self.writes=[]
        self.packets=[]
        self.steps=[]
        for i in range(4):
            self.add_read(i,0x12000100+4*i,100000+200000*i)
        self.add_write(0x12000200,900000)
        self.save()

    def add_read(self,i,addr,t0):
        request_id=f"00:00.0:{i}"
        payload=bytes([0xaa,0xbb,0xcc,0xdd])
        self.packets.extend([
            {"kind":"transaction","source":"pcie0.rx_req","protocol":"pcie",
             "operation":"mem_read","id":request_id,"start_ps":t0,
             "end_ps":t0,"fields":{"address":hex(addr),"length_dw":1,
                                   "requested_bytes":4}},
            {"kind":"transaction","source":"pcie0.tx_cpl","protocol":"pcie",
             "operation":"completion","id":request_id,
             "start_ps":t0+130000,"end_ps":t0+130000,
             "fields":{"request_to_completion_ps":130000,
                        "payload_hex":payload.hex()}}],
        )
        for role,start,end in [("host",t0+30000,t0+120000),
                               ("sram",t0+70000,t0+80000)]:
            self.reads.append({
                "monitor":"pcie0_local_data."+role,"uid":f"{role}-r{i}",
                "operation":"read","address":hex(addr),
                "start_ps":start,"end_ps":end,"status":"complete",
                "response":"0x0","request":{"size":"0x3"},
                "beats":[{"data":hex(0xddccbbaa << (8 * (addr & 7)))}],
            })
        self.steps.append({"actor":"host0","step":f"bar_read_{i}",
                           "start_ps":t0-10000,"time_ps":t0+140000,
                           "duration_ps":150000,
                           "details":{"address":hex(addr),"bytes":4}})

    def add_write(self,addr,t0):
        self.packets.append({
            "kind":"transaction","source":"pcie0.rx_req","protocol":"pcie",
            "operation":"mem_write","id":"00:00.0:0","start_ps":t0,
            "end_ps":t0,
            "fields":{"address":hex(addr),"length_dw":1,
                      "first_be":"0xf","last_be":"0x0",
                      "payload_hex":b"abcd".hex()}})
        for role,start,end in [("host",t0+20000,t0+110000),
                               ("sram",t0+60000,t0+70000)]:
            self.writes.append({
                "monitor":"pcie0_local_data."+role,"uid":f"{role}-w",
                "operation":"write","address":hex(addr),
                "start_ps":start,"end_ps":end,"status":"complete",
                "response":"0x0","request":{"size":"0x3"},
                "beats":[{"data":"0x64636261","strb":"0x0f"}],
            })

    def save(self):
        (self.folder/"protocol-transactions.json").write_text(json.dumps(
            {"records":self.packets}))
        (self.folder/"axi-transactions.json").write_text(json.dumps({
            "run":{"clock_period_ps":10000},
            "sections":{"axi":{"transactions":self.reads+self.writes}}}))
        (self.folder/"test-flow.json").write_text(json.dumps({"rows":self.steps}))

    def test_correlates_all_real_boundaries(self):
        data=analyze(self.folder)
        self.assertTrue(data["passed"],data["issues"])
        self.assertEqual(data["coverage"]["correlated_read_paths"],4)
        self.assertEqual(data["coverage"]["correlated_axi_operations"],5)
        self.assertEqual(data["host_vectors"][0]["host_api_ns"],150)
        self.assertEqual(data["host_vectors"][0]["rtl_tlp_ns"],130)
        self.assertEqual(data["stages"][0]["avg_cycles"],3)
        self.assertIn("Link/PHY latency is unmeasured",render_panel(data))
        self.assertTrue((self.folder/"traffic-latency.json").is_file())

    def test_payload_mismatch_rejects_green_report(self):
        self.packets[1]["fields"]["payload_hex"]="ffffeeee"
        self.save()
        data=analyze(self.folder)
        self.assertFalse(data["passed"])
        self.assertTrue(any("data mismatch" in m for m in data["issues"]))

    def test_incomplete_target_write_rejects_green_report(self):
        self.writes[-1]["status"]="incomplete"
        self.save()
        data=analyze(self.folder)
        self.assertFalse(data["passed"])
        self.assertTrue(any("incomplete" in m for m in data["issues"]))


if __name__=="__main__":
    unittest.main()
