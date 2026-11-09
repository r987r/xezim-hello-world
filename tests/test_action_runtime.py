"""Typed action execution uses source order/deps and never fabricates RTL proof."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv.common.action_runtime import ActionDispatcher, ActionDispatchError
from dv.common.action_events import ActionEventRecorder


def plan(actions):
    document = {
        "schema_version": 1, "kind": "soc_scenario_intent_only",
        "scenario_id": "test_dispatch", "execution_evidence": None,
        "actors": ["dma0", "checker0"], "actions": actions,
    }
    return (json.dumps(document, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("ascii")


def action(aid, kind="dma.copy", phase="run", parents=()):
    return {"action_instance_id": aid, "kind": kind, "phase": phase,
            "actor": "dma0", "args": {"target": aid},
            "depends_on": list(parents)}


class RuntimeActionTests(unittest.TestCase):

    def test_event_mailbox_actions_use_same_dispatcher_not_hardware_proof(self):
        raw = plan([
            {"action_instance_id": "emit", "kind": "event.emit",
             "phase": "run", "actor": "dma0",
             "args": {"queue": "mailbox", "token": "transfer_done"},
             "depends_on": []},
            {"action_instance_id": "wait", "kind": "event.wait",
             "phase": "check", "actor": "checker0",
             "args": {"queue": "mailbox", "token": "transfer_done"},
             "depends_on": ["emit"]},
        ])
        called = []
        async def drive(item, ctx):
            called.append((item["kind"], item["args"]["token"]))
        with TemporaryDirectory() as temp:
            events = Path(temp) / "events.jsonl"
            recorder = ActionEventRecorder(raw, events, lambda: 0)
            d = ActionDispatcher(raw, {"event.emit": drive, "event.wait": drive},
                                 recorder=recorder, max_inflight=2, task_backend="asyncio")
            asyncio.run(d.run())
            recorder.close()
            data = [json.loads(x) for x in events.read_text().splitlines()]
            self.assertEqual([x["stage"] for x in data],
                             ["issued", "driver_done", "issued", "driver_done"])
            self.assertTrue(all(x["origin"] == "python_driver"
                                and not x["evidence"] for x in data))
            self.assertEqual(called, [("event.emit", "transfer_done"),
                                      ("event.wait", "transfer_done")])

    def test_raw_event_plan_cannot_bypass_causal_validation(self):
        emit = {"action_instance_id": "emit", "kind": "event.emit",
                "phase": "run", "actor": "dma0",
                "args": {"queue": "mailbox", "token": "one"},
                "depends_on": []}
        wait = {"action_instance_id": "wait", "kind": "event.wait",
                "phase": "check", "actor": "checker0",
                "args": {"queue": "mailbox", "token": "one"},
                "depends_on": []}
        with self.assertRaisesRegex(ActionDispatchError, "causal emit"):
            ActionDispatcher(plan([emit, wait]), {
                "event.emit": lambda *_: None, "event.wait": lambda *_: None})
        wait["depends_on"] = ["emit"]
        wait["args"]["token"] = "wrong"
        with self.assertRaisesRegex(ActionDispatchError, "no matching producer"):
            ActionDispatcher(plan([emit, wait]), {
                "event.emit": lambda *_: None, "event.wait": lambda *_: None})

    def test_selected_actions_dispatch_through_real_registered_handlers(self):
        # Independent actions preserve selected order; deferred prerequisites
        # are respected, and both typed argument and phase are passed through.
        raw = plan([
            action("a", "dma.configure", "init"),
            action("c", "dma.copy", "run", ("b",)),
            action("b", "dma.copy", "run", ("a",)),
            action("d", "memory.check", "check", ("c",)),
        ])
        visited = []
        def handler(kind):
            async def drive(item, context):
                self.assertEqual(item["kind"], kind)
                self.assertEqual(item["args"]["target"], item["action_instance_id"])
                context.append((kind, item["action_instance_id"]))
                visited.append(item["action_instance_id"])
            return drive
        handlers = {k: handler(k) for k in
                    ("dma.configure", "dma.copy", "memory.check")}
        with TemporaryDirectory() as tmp:
            now = [0]
            events = Path(tmp) / "action-events.jsonl"
            recorder = ActionEventRecorder(raw, events, lambda: now[0])
            dispatch = ActionDispatcher(
                raw, handlers, recorder=recorder,
                expected_sha=hashlib.sha256(raw).hexdigest())
            context = []
            asyncio.run(dispatch.run(context))
            recorder.close()
            self.assertEqual(visited, ["a", "b", "c", "d"])
            self.assertEqual([x[1] for x in context], visited)
            data = [json.loads(x) for x in events.read_text().splitlines()]
            self.assertEqual(len(data), 8)
            self.assertTrue(all(x["origin"] == "python_driver" for x in data))
            self.assertEqual([x["stage"] for x in data], 
                             ["issued", "driver_done"] * 4)
            self.assertTrue(all(not x["evidence"] for x in data))
            with self.assertRaisesRegex(ActionDispatchError, "only be dispatched once"):
                asyncio.run(dispatch.run())

    def test_missing_adapter_wrong_hash_and_recorder_rejected_before_dispatch(self):
        raw = plan([action("a")])
        with self.assertRaisesRegex(ActionDispatchError, "no registered handler"):
            ActionDispatcher(raw, {})
        with self.assertRaisesRegex(ActionDispatchError, "SHA"):
            ActionDispatcher(raw, {"dma.copy": lambda *_: None},
                             expected_sha="0" * 64)
        different = plan([action("other")])
        with TemporaryDirectory() as tmp:
            rec = ActionEventRecorder(
                different, Path(tmp) / "wrong.jsonl", lambda: 0)
            with self.assertRaisesRegex(ActionDispatchError, "selected plan"):
                ActionDispatcher(raw, {"dma.copy": lambda *_: None}, recorder=rec)
            rec.close()

    def test_failed_handler_remains_unfinished_not_claimed_as_pass(self):
        raw = plan([action("fail")])
        async def broken(item, context):
            raise RuntimeError("real driver error")
        with TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            rec = ActionEventRecorder(raw, events, lambda: 0)
            dispatcher = ActionDispatcher(raw, {"dma.copy": broken}, recorder=rec)
            with self.assertRaisesRegex(RuntimeError, "real driver error"):
                asyncio.run(dispatcher.run())
            self.assertEqual(list(dispatcher.completed), [])
            with self.assertRaisesRegex(Exception, "unfinished"):
                rec.close()
            data = [json.loads(s) for s in events.read_text().splitlines()]
            self.assertEqual([x["stage"] for x in data], ["issued"])

    def test_backward_phase_and_cycles_fail_before_any_handler(self):
        with self.assertRaisesRegex(Exception, "backwards"):
            ActionDispatcher(plan([
                action("a", "dma.copy", "check"),
                action("b", "dma.copy", "init", ("a",)),
            ]), {"dma.copy": lambda *_: None})
        with self.assertRaisesRegex(Exception, "cyclic"):
            ActionDispatcher(plan([
                action("a", parents=("b",)),
                action("b", parents=("a",)),
            ]), {"dma.copy": lambda *_: None})


if __name__ == "__main__":
    unittest.main()
