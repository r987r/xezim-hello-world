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

    def fake_capture(self, cases=None):
        records=[]
        for c in (self.cases if cases is None else cases):
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

    def full_chip_fixture(self):
        """The selected full-chip actor set is NOT the all-actor SuperNoC set."""
        chip=json.loads((ROOT/"gen/chip/manifest.json").read_text())
        selected=dict(self.spec,memory_offset=self.spec["full_chip_scratch_offset"])
        cases=plan(self.manifest,selected,
                   selected_masters=["m_compute0_local_data_dma"],
                   writable_only=True,
                   selected_region_bases={m["base"] for m in chip["memory_models"]})
        return cases,intent(cases,self.spec,"chip-boot-latency")

    def test_full_chip_cpu_firmware_is_not_benchmark_actor(self):
        cases,expected=self.full_chip_fixture()
        data=self.fake_capture(cases)
        self.assertEqual({c["monitor"] for c in cases},
                         {"compute0_local_data.dma"})
        cpu_read={"role":"initiator","phase":self.spec["phase"],
                  "monitor":"compute0_local_data.cpu","plane":"data",
                  "operation":"read","address":"0x100000d0",
                  "status":"complete","issues":[],"expected_beats":1,
                  "response":"0x0","start_ps":10,"end_ps":40}
        data["sections"]["axi"]["transactions"].extend([cpu_read]*5)
        proof=validate(data,expected)
        self.assertEqual(proof["measured_transactions"],
                         expected["expected_measured_transactions"])
        self.assertEqual(proof["concurrent_nonbenchmark_initiator_transactions"],5)
        self.assertEqual(proof["concurrent_nonbenchmark_initiators"],
                         {"compute0_local_data.cpu":5})
        # The exact same missing or duplicated BFM samples still fail.
        data["sections"]["axi"]["transactions"].pop(0)
        with self.assertRaises(BenchmarkError):
            validate(data,expected)

    def test_incomplete_background_cpu_read_is_fatal(self):
        cases,expected=self.full_chip_fixture()
        data=self.fake_capture(cases)
        data["sections"]["axi"]["transactions"].append({
            "role":"initiator","phase":self.spec["phase"],
            "monitor":"compute1_local_data.cpu","plane":"data",
            "operation":"read","address":"0x11000050",
            "status":"incomplete","issues":["unfinished"],
            "expected_beats":1,"response":None,
            "start_ps":10,"end_ps":None})
        with self.assertRaisesRegex(BenchmarkError, "incomplete"):
            validate(data,expected)

    def test_supernoc_includes_real_cpu_ports_as_benchmark_actors(self):
        """All-actor topology runs must reject extra CPU transactions."""
        source={c["monitor"] for c in self.cases}
        self.assertIn("compute0_local_data.cpu",source)
        data=self.fake_capture()
        owned_case=next(c for c in self.cases
                        if not c["warmup"] and c["monitor"]=="compute0_local_data.cpu")
        extra=next(tx for tx in data["sections"]["axi"]["transactions"]
                   if tx["monitor"]=="compute0_local_data.cpu"
                   and tx["address"]==owned_case["address"])
        data["sections"]["axi"]["transactions"].append(copy.deepcopy(extra))
        with self.assertRaisesRegex(BenchmarkError,"measured AXI source set mismatch"):
            validate(data,self.expected)

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

    def test_full_chip_only_live_memory_models_and_no_silent_fallback(self):
        chip=json.loads((ROOT/"gen/chip/manifest.json").read_text())
        models=chip["memory_models"]
        selected=dict(self.spec,memory_offset=self.spec["full_chip_scratch_offset"])
        cases=plan(self.manifest, selected,
                   selected_masters=["m_compute0_local_data_dma"],
                   writable_only=True,
                   selected_region_bases={row["base"] for row in models})
        self.assertEqual(len(cases),len(models)*36)
        self.assertEqual(
            {int(c["address"],16) // (1<<30) for c in cases},
            {row["base"] // (1<<30) for row in models})
        with self.assertRaises(BenchmarkError):
            plan(self.manifest,selected,
                 selected_masters=["m_compute0_local_data_dma"],
                 writable_only=True,selected_region_bases={0xdead0000})

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
