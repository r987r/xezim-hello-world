"""Contract tests for publication of actual LiteDRAM DFI probe evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from dfi_to_protocol import convert


class DDRUnifiedProtocolTests(unittest.TestCase):
    def inputs(self,root):
        events=[
            {"kind":"probe_start","scope":"standalone_litedram_dfi_sim"},
            {"kind":"dfi_activate","time_ps":10000,"bank":3,"address":128,
             "dfi_phase":0,"test_phase":"traffic","cycle":1},
            {"kind":"dfi_precharge","time_ps":20000,"bank":3,
             "dfi_phase":0,"test_phase":"traffic","cycle":2},
            {"kind":"dfi_refresh","time_ps":30000,
             "dfi_phase":1,"test_phase":"traffic","cycle":3},
            {"kind":"dfi_read","time_ps":40000,"bank":3,"address":128,
             "dfi_phase":0,"test_phase":"traffic","cycle":4},
            {"kind":"dfi_write","time_ps":50000,"bank":3,"address":128,
             "dfi_phase":0,"test_phase":"traffic","cycle":5},
            {"kind":"dfi_rddata_valid","time_ps":60000,
             "dfi_phase":0,"test_phase":"traffic","cycle":6},
            {"kind":"bankmodel_storage_write","time_ps":70000,"bank":3,
             "enabled_bytes":8,"test_phase":"traffic","cycle":7},
            {"kind":"probe_end","status":"pass","sampled_cycles":7},
        ]
        (root/"ddr4_dfi_events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)+"\n")
        counts={}
        for e in events[1:-1]:
            counts[e["kind"]]=counts.get(e["kind"],0)+1
        (root/"ddr4_dfi_summary.json").write_text(
            json.dumps({"status":"pass","sampled_cycles":7,
                        "counters":counts}))
        (root/"ddr4_functional_result.json").write_text(
            json.dumps({"status":"pass"}))
        return events

    def test_actual_commands_and_behavioral_bank_event_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.inputs(root)
            report=convert(root,root/"report")
            ops=[e["operation"] for e in report["records"]]
            self.assertEqual(ops,["act","pre","ref","rd","wr",
                                  "rddata_valid","storage_write"])
            self.assertTrue(report["capture_complete"])
            self.assertEqual({e["source"] for e in report["records"]},
                             {"memory0.ddr0.dfi","memory0.ddr0.bankmodel"})
            for row in report["records"]:
                self.assertEqual(row["kind"],"event")
                self.assertEqual(row["status"],"observed")
                self.assertIsNone(row["id"])
            self.assertEqual(report["records"][0]["fields"]["address"],128)
            self.assertEqual(report["records"][-1]["fields"]["model_boundary"],
                             "behavioral_storage")
            result=json.loads((root/"report/result.json").read_text())
            self.assertEqual(result["target"],"ddr4-standalone")
            self.assertTrue(result["passed"])

    def test_incomplete_and_inconsistent_dfi_capture_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            events=self.inputs(root)
            events[-1]["status"]="fail"
            (root/"ddr4_dfi_events.jsonl").write_text(
                "\n".join(json.dumps(e) for e in events)+"\n")
            with self.assertRaisesRegex(ValueError,"start/end"):
                convert(root,root/"report")
            events[-1]["status"]="pass"
            (root/"ddr4_dfi_events.jsonl").write_text(
                "\n".join(json.dumps(e) for e in events)+"\n")
            summary=json.loads((root/"ddr4_dfi_summary.json").read_text())
            summary["counters"]["dfi_read"]=2
            (root/"ddr4_dfi_summary.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError,"count mismatch"):
                convert(root,root/"report2")


if __name__=="__main__":
    unittest.main()
