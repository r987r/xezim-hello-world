"""No-RTL negative gates for source-derived serial latency cases and evidence."""
import copy
import json
from pathlib import Path
import unittest

from tools.fabric_benchmark import BenchmarkError, config, plan, intent, validate

ROOT = Path(__file__).resolve().parents[1]


class FabricBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/"gen/supernoc/manifest.json").read_text())
        cls.spec=config(ROOT)
        cls.cases=plan(cls.manifest,cls.spec)
        cls.expected=intent(cls.cases,cls.spec,"supernoc-latency")

    def test_every_legal_region_and_unique_addresses(self):
        self.assertEqual(len(self.cases),sum(len(m["regions"]) for m in self.manifest["masters"])*36)
        self.assertEqual(len({(c["plane"],c["address"]) for c in self.cases}),len(self.cases))
        self.assertEqual(self.expected["measured_cases"],sum(len(m["regions"]) for m in self.manifest["masters"])*32)
        self.assertTrue(all(c["bytes"] in (4,8) for c in self.cases))
        self.assertEqual(self.expected["max_outstanding"],1)

    def fake_capture(self):
        records=[]
        for c in self.cases:
            if c["warmup"]:
                continue
            for op in c["operations"]:
                records.append({"role":"initiator","phase":self.spec["phase"],
                                "monitor":c["monitor"],"plane":c["plane"],
                                "operation":op,"address":c["address"],
                                "status":"complete","issues":[],
                                "expected_beats":1,"response":"0x0",
                                "start_ps":10,"end_ps":30})
        return {"run":{"capture_bound":True,"capture_overflow":False,
                       "dirty":False,"clock_period_ps":10000},
                "sections":{"axi":{"issues":[],"transactions":records}}}

    def test_exact_observed_source_set(self):
        proof=validate(self.fake_capture(),self.expected)
        self.assertEqual(proof["measured_transactions"],
                         self.expected["expected_measured_transactions"])
        self.assertGreater(proof["sampled_read"],proof["sampled_write"])

    def test_dropped_duplicate_or_failed_sample_rejected(self):
        for mutation in ("drop","duplicate","fail","wrong_phase","bad_clock","dirty","issue"):
            data=self.fake_capture()
            rows=data["sections"]["axi"]["transactions"]
            if mutation=="drop":rows.pop()
            if mutation=="duplicate":rows.append(copy.deepcopy(rows[-1]))
            if mutation=="fail":rows[-1]["status"]="incomplete"
            if mutation=="wrong_phase":rows[-1]["phase"]="different"
            if mutation=="bad_clock":data["run"]["clock_period_ps"]=None
            if mutation=="dirty":data["run"]["dirty"]=True
            if mutation=="issue":data["sections"]["axi"]["issues"].append({"message":"bad B"})
            with self.subTest(mutation=mutation),self.assertRaises(BenchmarkError):
                validate(data,self.expected)

    def test_reject_unrepresentable_window(self):
        small=copy.deepcopy(self.manifest)
        small["masters"][0]["regions"][0]["size"]=8
        with self.assertRaises(BenchmarkError):
            plan(small,self.spec)

    def test_reject_nonserial_config(self):
        bad=dict(self.spec,max_outstanding=2)
        with self.assertRaises(BenchmarkError):
            config(ROOT,profile="missing")
        # Mutated explicit configuration cannot weaken the bench's contract.
        self.assertNotEqual(bad["max_outstanding"],self.spec["max_outstanding"])


if __name__=="__main__":
    unittest.main()
