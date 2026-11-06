"""SCN-3 SV driver transcript can enter v2 but can never claim hardware proof."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from dv.common.scenario import canonical_json
from tools.scenario_sv import audit_sv_transcript
from tools.action_sv_import import import_sv_driver
from tools.action_evidence import summarize
from dv.common.action_events import ActionEvidenceError


def mock_plan():
    plan = {
        "schema_version": 1, "kind": "soc_scenario_intent_only",
        "scenario_id": "sv_to_v2", "seed": 7,
        "variant": "boot_live", "actors": ["dma0"],
        "execution_evidence": None,
        "actions": [
            {"action_instance_id": f"copy{i}", "actor": "dma0", "phase": "run",
             "kind": "dma.copy", "args": {"length": 64},
             "depends_on": [], "expected_result_id": f"expected.copy{i}"}
            for i in range(2)]
    }
    raw = canonical_json(plan).encode("ascii")
    return raw, hashlib.sha256(raw).hexdigest()


class SVEventImportTests(unittest.TestCase):
    def setUp(self):
        self.raw, sha = mock_plan()
        lines = [
            f"SOC_SCN_SV_V1|sv_to_v2|{sha}|copy0|run|issued|10",
            f"SOC_SCN_SV_V1|sv_to_v2|{sha}|copy1|run|issued|11",
            f"SOC_SCN_SV_V1|sv_to_v2|{sha}|copy1|run|driver_done|13",
            f"SOC_SCN_SV_V1|sv_to_v2|{sha}|copy0|run|driver_done|14",
        ]
        self.report = audit_sv_transcript(self.raw, "\n".join(lines))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "action-events.jsonl"

    def test_converts_real_sv_parser_output_to_v2_driver_only(self):
        receipt = import_sv_driver(self.raw, self.report, self.out, tick_ps=1000)
        self.assertEqual(receipt["status"], "driver_only_unverified")
        self.assertIsNone(receipt["rtl_evidence"])
        self.assertEqual(receipt["event_count"], 4)
        lines = self.out.read_text().splitlines()
        events = [json.loads(line) for line in lines]
        self.assertEqual([x["time_ps"] for x in events], [10000, 11000, 13000, 14000])
        self.assertTrue(all(e["origin"] == "sv_driver" and e["evidence"] == {}
                            for e in events))
        result = summarize(self.raw, lines, require_all=True)
        self.assertFalse(result["passed"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["summary"]["issued"], 2)
        self.assertEqual(result["summary"]["completed"], 0)

    def test_rejects_false_rtl_observed_claim(self):
        bad = copy.deepcopy(self.report)
        bad["events"][0]["rtl_observed"] = True
        with self.assertRaisesRegex(ActionEvidenceError, "falsely claims"):
            import_sv_driver(self.raw, bad, self.out, tick_ps=1000)
        self.assertFalse(self.out.exists())

    def test_rejects_undocumented_timestamp_scaling(self):
        with self.assertRaisesRegex(ActionEvidenceError, "explicit"):
            import_sv_driver(self.raw, self.report, self.out, tick_ps=0)
        with self.assertRaisesRegex(ActionEvidenceError, "overflows"):
            import_sv_driver(self.raw, self.report, self.out, tick_ps=2**53-1)
        self.assertFalse(self.out.exists())

    def test_rejects_wrong_plan_sha_or_driver_stage(self):
        forged = copy.deepcopy(self.report)
        forged["plan_sha256"] = "0" * 64
        with self.assertRaisesRegex(ActionEvidenceError, "SV report"):
            import_sv_driver(self.raw, forged, self.out, tick_ps=1000)
        forged = copy.deepcopy(self.report)
        forged["events"][0]["event"] = "checked"
        with self.assertRaisesRegex(ActionEvidenceError, "protocol/checker"):
            import_sv_driver(self.raw, forged, self.out, tick_ps=1000)

    def test_rejects_orphan_and_duplicate_sv_actions(self):
        for items in (self.report["events"][1:], self.report["events"] + self.report["events"][-1:]):
            bad = copy.deepcopy(self.report)
            bad["events"] = items
            bad["event_count"] = len(items)
            with self.subTest(count=len(items)), self.assertRaises(ActionEvidenceError):
                import_sv_driver(self.raw, bad, self.out, tick_ps=1000)
            self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
