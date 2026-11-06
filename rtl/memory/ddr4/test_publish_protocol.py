"""Source-verified DFI command bridge regression tests (no simulator required)."""
from pathlib import Path
import json
import tempfile
import unittest

from publish_protocol import validate_and_adapt,publish


def fixture(directory, *,mutate=None):
    output=Path(directory)
    events=[
        {"kind":"probe_start","scope":"standalone_litedram_dfi_sim",
         "physical_phy":"not_modeled","physical_dram":"not_modeled"},
        {"kind":"dfi_activate","time_ps":10000,"cycle":1,
         "dfi_phase":0,"bank":2,"address":55,"test_phase":"traffic"},
        {"kind":"dfi_precharge","time_ps":10000,"cycle":1,
         "dfi_phase":1,"bank":2,"test_phase":"traffic"},
        {"kind":"dfi_read","time_ps":20000,"cycle":2,
         "dfi_phase":0,"bank":2,"address":7,"test_phase":"traffic"},
        {"kind":"dfi_write","time_ps":20000,"cycle":2,
         "dfi_phase":1,"bank":3,"address":8,"test_phase":"traffic"},
        {"kind":"dfi_refresh","time_ps":30000,"cycle":3,
         "dfi_phase":0,"test_phase":"traffic"},
        {"kind":"bankmodel_storage_write","time_ps":30000,"cycle":3,
         "bank":3,"enabled_bytes":8,"test_phase":"traffic"},
        {"kind":"probe_end","status":"pass","sampled_cycles":3},
    ]
    if mutate:
        mutate(events)
    from collections import Counter
    counts=dict(Counter(e["kind"] for e in events[1:-1]))
    (output/"ddr4_dfi_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events)+"\n")
    (output/"ddr4_dfi_summary.json").write_text(json.dumps({
        "status":"pass","sampled_cycles":3,
        "period_source":"configured_and_observed_standalone_clk",
        "models":{"full_chip":"not_connected"},
        "counters":counts
    }))
    (output/"ddr4_functional_result.json").write_text(
        json.dumps({"status":"pass","scope":"isolated LiteDRAM"}))


class DDRDFIProtocolPublicationTests(unittest.TestCase):
    def test_actual_stream_generates_exact_command_and_bank_model_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            fixture(output)
            catalog,records,commands,samples=validate_and_adapt(output)
            self.assertEqual(commands,{"act":1,"pre":1,"rd":1,"wr":1,"ref":1})
            self.assertEqual(samples,3)
            self.assertEqual([r["operation"] for r in records],
                             ["act","pre","rd","wr","ref","model_storage_write"])
            self.assertEqual(records[0]["fields"]["address"],55)
            self.assertEqual(records[0]["source"],"memory0.ddr0.dfi.phase0")
            self.assertEqual(records[-1]["source"],"memory0.ddr0.bankmodel.bank3")
            self.assertEqual(set(s["protocol"] for s in catalog),{"dfi","ddr_model"})

    def test_provenance_preserved_in_common_protocol_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"source";output.mkdir()
            fixture(output)
            sha="a"*40
            stats=publish(output,Path(tmp)/"published",commit=sha,run_id="123",attempt="2")
            protocol=json.loads((Path(tmp)/"published"/"protocol-transactions.json").read_text())
            result=json.loads((Path(tmp)/"published"/"result.json").read_text())
            self.assertEqual(stats["records"],6)
            self.assertEqual(protocol["run"]["commit"],sha)
            self.assertEqual(protocol["run"]["workflow_run_id"],"123")
            self.assertEqual(protocol["run"]["workflow_attempt"],"2")
            self.assertTrue(protocol["capture_complete"])
            self.assertTrue(result["passed"])
            self.assertIn("ddr4-standalone",result["target"])
            self.assertTrue((Path(tmp)/"published"/"protocols.html").is_file())

    def test_rejects_missing_terminal_and_corrupt_command_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            fixture(output,mutate=lambda events:events.pop())
            with self.assertRaisesRegex(ValueError,"terminate"):
                validate_and_adapt(output)
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);fixture(output)
            summary=output/"ddr4_dfi_summary.json"
            data=json.loads(summary.read_text());data["counters"]["dfi_read"]=7
            summary.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"counts disagree"):
                validate_and_adapt(output)

    def test_rejects_non_monotonic_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            fixture(output,mutate=lambda events:events[3].update(time_ps=1))
            with self.assertRaisesRegex(ValueError,"non-monotonic"):
                validate_and_adapt(output)


if __name__=="__main__":
    unittest.main()
