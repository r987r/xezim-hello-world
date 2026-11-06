"""Test event ABI and fail-closed report independent of Cocotb or simulators."""
import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT), str(ROOT/"tools")]
from dv.common.test_flow import StepRecorder, validate_event
from test_flow_report import summarize, write_report
import regress


EXPECTED = {
    "init":["host0.enumerate","cpu0.init_complete"],
    "run":["host0.bar_roundtrip","cpu0.run_complete"],
    "check":["host0.check_ack","cpu0.check_complete"],
}


def capture_events(base, *, stop=None):
    tick=[0]
    def clock():
        tick[0]+=100
        return tick[0]
    out=Path(base)/"test-flow-events.jsonl"
    recorder=StepRecorder(out,clock)
    for phase,steps in EXPECTED.items():
        for item in steps:
            actor,step=item.split(".",1)
            if (phase,item)==stop:
                continue
            with recorder.step(phase,actor,step,
                               origin="checker" if actor=="cpu0" else "stimulus"):
                pass
    recorder.close()
    return [json.loads(line) for line in out.read_text().splitlines()]


class TestFlowContract(unittest.TestCase):
    def test_all_phase_steps_reported_and_linked_into_existing_html(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)
            capture_events(p)
            (p/"report.html").write_text("<main><p>Existing AXI explorer</p></main>")
            result=write_report(p,{"report":{"flow":{"required_steps":EXPECTED}}})
            self.assertTrue(result["passed"],result["issues"])
            self.assertEqual(len(result["rows"]),6)
            self.assertIn("test-flow.html",(p/"report.html").read_text())
            self.assertIn("Existing AXI explorer",(p/"report.html").read_text())
            self.assertIn("host0",(p/"test-flow.html").read_text())

    def test_missing_and_failed_event_cannot_be_green(self):
        with TemporaryDirectory() as tmp:
            events=capture_events(tmp,stop=("check","host0.check_ack"))
            summary=summarize(events,EXPECTED)
            self.assertFalse(summary["passed"])
            self.assertTrue(any("missing required" in e for e in summary["issues"]))
            events[-1]["status"]="fail"
            self.assertFalse(summarize(events,EXPECTED)["passed"])

    def test_truncation_duplicates_and_unknown_actor_fail_closed(self):
        with TemporaryDirectory() as tmp:
            events=capture_events(tmp)
            examples=[
                events[:-1],
                [*events,events[0]],
                [{**events[0],"actor":"unexpected"},*events[1:]],
                [{**events[0],"seq":5},*events[1:]],
            ]
            for e in examples:
                with self.subTest(length=len(e)):
                    self.assertFalse(summarize(e,EXPECTED)["passed"])

    def test_phase_regression_and_origin_spoofing_fail_closed(self):
        with TemporaryDirectory() as tmp:
            events=capture_events(tmp)
            # Same six legitimate steps; a RUN action after CHECK is forbidden.
            reordered=[*events[:4],*events[8:],*events[4:8]]
            for i,event in enumerate(reordered):
                event["seq"]=i
                event["time_ps"]=i*100
            result=summarize(reordered,EXPECTED)
            self.assertFalse(result["passed"])
            self.assertTrue(any("phase order" in issue for issue in result["issues"]))
            clean=capture_events(tmp)
            required={"init":{"host0.enumerate":"rtl_observed"}}
            result=summarize(clean,EXPECTED,required)
            self.assertFalse(result["passed"])
            self.assertTrue(any("origin mismatch" in issue for issue in result["issues"]))
            result=summarize(clean,EXPECTED,{"init":{"host0.enumerate":"stimulus"}})
            self.assertTrue(result["passed"],result["issues"])

    def test_sync_exception_generates_failure_and_rejects_open_actions(self):
        with TemporaryDirectory() as tmp:
            recorder=StepRecorder(Path(tmp)/"events.jsonl",lambda:100)
            with self.assertRaisesRegex(RuntimeError,"failed"):
                with recorder.step("init","host0","enumerate"):
                    raise RuntimeError("failed")
            recorder.close()
            e=[json.loads(line) for line in (Path(tmp)/"events.jsonl").read_text().splitlines()]
            self.assertEqual([x["status"] for x in e],["start","fail"])
            bad=StepRecorder(Path(tmp)/"broken.jsonl",lambda:100)
            bad.emit("run","cpu0","x","start","checker")
            with self.assertRaisesRegex(AssertionError,"incomplete"):
                bad.close()

    def test_invalid_schema_and_unsafe_values(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)
            recorder=StepRecorder(p/"no",lambda:0)
            try:
                with self.assertRaises(ValueError):
                    recorder.emit("setup","host0","phase","start","stimulus")
            finally:
                recorder.close()
            bad={"schema_version":1,"seq":0,"time_ps":0,"phase":"init",
                 "actor":"host0","step":"x","status":"pass","origin":"stimulus",
                 "details":{"bad":"<script>"}}
            self.assertEqual(validate_event(bad),bad)
            for key,val in [("time_ps",-1),("actor","evil.actor!"),
                            ("details",{"x":[]}),("origin","made_up")]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    validate_event({**bad,key:val})

    def test_yaml_requires_exact_phases_and_declared_unique_steps(self):
        cfg=regress.load_config(ROOT/"config/regression.yaml")
        self.assertIn("host0.enumerate",
                      cfg["tests"]["chip-pcie-host"]["report"]["flow"]["required_steps"]["init"])
        for value in ({"init":[],"run":["host0.x"],"check":["host0.x"]},
                      {"init":["host0.a","host0.a"],"run":["host0.x"],"check":["host0.x"]},
                      {"init":["host0.a"],"run":["bad!"],"check":["host0.x"]}):
            changed=copy.deepcopy(cfg)
            changed["tests"]["chip-pcie-host"]["report"]["flow"]["required_steps"]=value
            out=Path(self.id().split(".")[-1]+".yaml")
            with TemporaryDirectory() as tmp:
                out=Path(tmp)/"regression.yaml"
                import yaml
                out.write_text(yaml.safe_dump(changed))
                with self.assertRaisesRegex(ValueError,"test-flow"):
                    regress.load_config(out)


if __name__=="__main__":
    unittest.main()
