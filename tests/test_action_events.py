"""DV-EVENTS v2: no fake pass without independently accepted hardware evidence."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv.common.action_events import ActionEventRecorder, ActionEvidenceError, parse_plan
from tools.action_evidence import summarize


def fixture(count=2):
    plan = {"schema_version": 1, "scenario_id": "repeatable",
            "kind": "soc_scenario_intent_only", "execution_evidence": None,
            "actors": ["dma0", "dma1"], "seed": 72,
            "actions": [
                {"action_instance_id": f"copy{i}", "actor": f"dma{i%2}",
                 "phase": "run", "kind": "dma.copy", "depends_on": [],
                 "expected_result_id": f"expected.copy{i}",
                 "args": {"length": 64}}
                for i in range(count)]}
    raw = (json.dumps(plan, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True) + "\n").encode("ascii")
    return raw, hashlib.sha256(raw).hexdigest()


def axi():
    return {"run": {"capture_bound": True, "capture_overflow": False},
            "sections": {"axi": {"issues": [], "transactions": [
                {"uid": "dma.out:0:0", "monitor": "dma.out", "operation": "write",
                 "status": "complete", "start_ps": 20, "end_ps": 30,
                 "response": "0x0", "address": "0x140000100", "issues": []},
            ]}}}


def checker(sha):
    return {"kind": "independent_action_scoreboard", "capture_complete": True,
            "checks": [{"uid": "check0", "scenario_id": "repeatable",
                        "plan_sha256": sha, "action_instance_id": "copy0",
                        "origin": "independent_checker", "verdict": "pass",
                        "expected_hex": "5a5b", "observed_hex": "5a5b",
                        "observed_refs": [{"capture": "axi", "ref": "dma.out:0:0"}],
                        "time_ps": 50}]}


class ActionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.sha = fixture()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.events = Path(self.tmp.name) / "action-events.jsonl"
        self.time = 0
        self.writer = ActionEventRecorder(self.raw, self.events, lambda: self.time)

    def emit(self, stage, *, aid="copy0", origin="python_driver",
             ref=None, capture="axi", time=None):
        if time is not None:
            self.time = time
        return self.writer.emit(aid, stage, origin,
                                evidence=({"capture": capture, "ref": ref}
                                          if ref else None))

    def lines(self):
        self.writer.close()
        return self.events.read_text().splitlines()

    def test_selected_plan_rejects_cycles_and_backwards_phases(self):
        raw, _ = fixture()
        plan = json.loads(raw)
        plan["actions"][0]["depends_on"] = ["copy1"]
        plan["actions"][1]["depends_on"] = ["copy0"]
        encoded = (json.dumps(plan, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True) + "\n").encode("ascii")
        with self.assertRaisesRegex(ActionEvidenceError, "cyclic"):
            parse_plan(encoded)

        plan["actions"][0]["depends_on"] = []
        plan["actions"][1]["depends_on"] = ["copy0"]
        plan["actions"][0]["phase"] = "check"
        encoded = (json.dumps(plan, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True) + "\n").encode("ascii")
        with self.assertRaisesRegex(ActionEvidenceError, "backwards"):
            parse_plan(encoded)

    def test_runtime_dependency_requires_completed_driver_not_just_issuance(self):
        self.writer.close()
        plan = json.loads(fixture()[0])
        plan["actions"][1]["depends_on"] = ["copy0"]
        raw = (json.dumps(plan, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True) + "\n").encode("ascii")
        writer = ActionEventRecorder(raw, self.events, lambda: self.time)
        writer.emit("copy0", "issued", "python_driver")
        with self.assertRaisesRegex(ActionEvidenceError, "not driver-completed"):
            writer.emit("copy1", "issued", "python_driver")
        writer.emit("copy0", "driver_done", "python_driver")
        writer.emit("copy1", "issued", "python_driver")
        writer.emit("copy1", "driver_done", "python_driver")
        writer.close()

    def test_driver_only_never_passes(self):
        self.emit("issued", time=10)
        self.emit("driver_done", time=20)
        report = summarize(self.raw, self.lines())
        self.assertFalse(report["passed"])
        self.assertEqual(report["status"], "partially_verified_unmeasured")
        self.assertEqual(report["actions"][0]["status"], "driver_only_unverified")

    def test_actual_accepted_complete_and_independently_checked_one_action(self):
        self.emit("issued", time=10)
        self.emit("accepted", origin="passive_axi", ref="dma.out:0:0", time=20)
        self.emit("completed", origin="passive_axi", ref="dma.out:0:0", time=30)
        self.emit("driver_done", time=31)
        self.emit("checked", origin="independent_checker", capture="scoreboard",
                  ref="check0", time=50)
        report = summarize(self.raw, self.lines(), axi=axi(), scoreboard=checker(self.sha))
        self.assertEqual(report["issues"], [])
        self.assertFalse(report["passed"])  # second unobserved action
        self.assertEqual(report["actions"][0]["status"], "independently_checked")
        self.assertEqual(report["actions"][1]["status"], "unmeasured")
        self.assertEqual(report["summary"]["checked"], 1)

    def test_absent_uid_not_upgraded_to_observed(self):
        self.emit("issued", time=10)
        self.emit("accepted", origin="passive_axi", ref="invented:0:0", time=20)
        self.emit("driver_done", time=25)
        result = summarize(self.raw, self.lines(), axi=axi())
        self.assertFalse(result["passed"])
        self.assertTrue(any("absent passive" in m for m in result["issues"]))

    def test_driver_provenance_rejects_hardware_claims(self):
        self.emit("issued", time=10)
        with self.assertRaisesRegex(ActionEvidenceError, "provenance"):
            self.emit("accepted", origin="python_driver", ref="dma.out:0:0")
        with self.assertRaisesRegex(ActionEvidenceError, "hardware evidence"):
            self.writer.emit("copy0", "driver_done", "python_driver",
                             evidence={"capture": "axi", "ref": "dma.out:0:0"})
        self.emit("driver_done", time=11)
        self.lines()

    def test_wrong_time_and_slverr_rejected(self):
        self.emit("issued", time=10)
        self.emit("accepted", origin="passive_axi", ref="dma.out:0:0", time=21)
        self.emit("driver_done", time=25)
        lines = self.lines()
        report = summarize(self.raw, lines, axi=axi())
        self.assertTrue(any("time differs" in m for m in report["issues"]))
        bad = axi()
        bad["sections"]["axi"]["transactions"][0]["response"] = "0x2"
        report = summarize(self.raw, lines, axi=bad)
        self.assertTrue(any("non-OKAY" in m for m in report["issues"]))

    def test_invalid_axi_capture_is_not_proof(self):
        self.emit("issued", time=10)
        self.emit("driver_done", time=11)
        lines = self.lines()
        bad = axi()
        bad["run"]["capture_overflow"] = True
        with self.assertRaisesRegex(ActionEvidenceError, "incomplete"):
            summarize(self.raw, lines, axi=bad)
        bad = axi()
        bad["sections"]["axi"]["issues"] = ["incomplete burst"]
        with self.assertRaisesRegex(ActionEvidenceError, "failed"):
            summarize(self.raw, lines, axi=bad)

    def test_1000_plus_interleaved_independent_action_instances(self):
        self.writer.close()
        raw, _ = fixture(1200)
        now = [0]
        path = Path(self.tmp.name) / "large.jsonl"
        writer = ActionEventRecorder(raw, path, lambda: now[0])
        for i in range(1200):
            now[0] += 1
            writer.emit(f"copy{i}", "issued", "python_driver")
        for i in reversed(range(1200)):
            now[0] += 1
            writer.emit(f"copy{i}", "driver_done", "python_driver")
        writer.close()
        report = summarize(raw, path.read_text().splitlines(), require_all=True)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["summary"]["issued"], 1200)
        self.assertEqual(report["event_count"], 2400)
        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["completed"], 0)

    def test_protocol_frame_event_observed_not_completed(self):
        self.emit("issued", time=10)
        self.emit("observed", origin="passive_protocol", capture="protocol",
                  ref="record:0", time=20)
        self.emit("driver_done", time=25)
        protocols = {"capture_complete": True, "issues": [], "records": [{
            "kind": "event", "protocol": "ethernet", "source": "ethernet0.gmii_tx",
            "status": "observed", "start_ps": 20, "end_ps": 20,
            "operation": "frame_tx"}]}
        result = summarize(self.raw, self.lines(), protocols=protocols)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["actions"][0]["status"], "protocol_observed_unchecked")
        self.assertFalse(result["passed"])

    def test_duplicate_accepted_ref_cannot_claim_two_actions(self):
        self.emit("issued", time=10)
        self.emit("issued", aid="copy1", time=11)
        self.emit("accepted", origin="passive_axi", ref="dma.out:0:0", time=20)
        self.emit("accepted", aid="copy1", origin="passive_axi",
                  ref="dma.out:0:0", time=20)
        self.emit("driver_done", time=25)
        self.emit("driver_done", aid="copy1", time=26)
        report = summarize(self.raw, self.lines(), axi=axi())
        self.assertTrue(any("already claimed" in m for m in report["issues"]))

    def test_duplicate_or_truncated_driver_fails(self):
        self.emit("issued", time=10)
        with self.assertRaisesRegex(ActionEvidenceError, "duplicate"):
            self.emit("issued", time=11)
        with self.assertRaisesRegex(ActionEvidenceError, "unfinished"):
            self.writer.close()
        raw = self.events.read_text().splitlines()
        result = summarize(self.raw, raw, require_all=True)
        self.assertTrue(any("required action not issued" in x for x in result["issues"]))
        self.assertFalse(result["passed"])

    def test_tampering_and_noncanonical_plan_fail(self):
        self.emit("issued", time=10)
        self.emit("driver_done", time=20)
        lines = self.lines()
        corrupt = json.loads(lines[0])
        corrupt["plan_sha256"] = "0" * 64
        result = summarize(self.raw, [json.dumps(corrupt), lines[1]])
        self.assertEqual(result["status"], "invalid_capture")
        with self.assertRaisesRegex(ActionEvidenceError, "canonical"):
            parse_plan(json.dumps(json.loads(self.raw), indent=2).encode())
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
