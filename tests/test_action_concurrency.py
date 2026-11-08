"""#152 M1: typed scheduler semantics; no fabricated hardware evidence."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv.common.action_events import ActionEventRecorder
from dv.common.action_runtime import (
    ActionDispatcher, ActionDispatchError, HandlerSpec, ResourceClaim,
)


def make_plan(*actions):
    return (json.dumps({
        "schema_version": 1, "kind": "soc_scenario_intent_only",
        "scenario_id": "concurrency", "execution_evidence": None,
        "actors": ["cpu0", "dma0", "dma1", "checker0"],
        "actions": list(actions),
    }, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def act(aid, kind="dma.copy", actor="dma0", phase="run", deps=(), **args):
    # Real DMA actions always claim BOTH byte buffers, even when testing
    # engine contention. Missing them must remain a production error.
    if kind == "dma.copy":
        args = {"src": f"{aid}.src", "dst": f"{aid}.dst", **args}
    return {"action_instance_id": aid, "kind": kind, "actor": actor,
            "phase": phase, "depends_on": list(deps), "args": args}


class ActionConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_independent_drivers_run_together_then_dependency(self):
        entered, release = set(), asyncio.Event()
        async def driver(item, _):
            aid = item["action_instance_id"]
            if aid in ("a", "b"):
                entered.add(aid)
                await release.wait()
            else:
                self.assertEqual(entered, {"a", "b"})
                self.assertEqual(len(d.completed), 2)
        raw = make_plan(
            act("a", engine="dma0"),
            act("b", actor="dma1", engine="dma1"),
            act("c", actor="checker0", deps=("a", "b"), engine="dma2"),
        )
        d = ActionDispatcher(raw, {"dma.copy": driver},
                             max_inflight=2, task_backend="asyncio")
        running = asyncio.create_task(d.run())
        for _ in range(20):
            if len(entered) == 2:
                break
            await asyncio.sleep(0)
        self.assertEqual(entered, {"a", "b"})
        self.assertFalse(d.completed)
        release.set()
        self.assertEqual(await running, ["a", "b", "c"])

    async def test_shared_engine_and_shared_actor_are_serial(self):
        for actor, engine in (("dma1", "dma0"), ("dma0", "dma1")):
            active = set()
            peak = [0]
            async def driver(item, _):
                self.assertFalse(active, "same actor or DMA engine overlapped")
                active.add(item["action_instance_id"])
                peak[0] = max(peak[0], len(active))
                await asyncio.sleep(0)
                active.remove(item["action_instance_id"])
            raw = make_plan(act("a", engine="dma0"),
                            act("b", actor=actor, engine=engine))
            await ActionDispatcher(raw, {"dma.copy": driver},
                                   max_inflight=2, task_backend="asyncio").run()
            self.assertEqual(peak, [1])

    async def test_shared_reads_concurrent_writer_serial(self):
        started = set()
        release = asyncio.Event()
        async def reader(item, _):
            started.add(item["action_instance_id"])
            await release.wait()
        async def writer(item, _):
            self.assertEqual(started, {"a", "b"})
            self.assertTrue(release.is_set())
        raw = make_plan(
            act("a", "memory.check", "dma0", buffer="shared"),
            act("b", "memory.check", "dma1", buffer="shared"),
            act("c", "memory.initialize", "checker0", buffer="shared"),
        )
        d = ActionDispatcher(raw, {"memory.check": reader,
                                   "memory.initialize": writer},
                             max_inflight=3, task_backend="asyncio")
        task = asyncio.create_task(d.run())
        for _ in range(20):
            if len(started) == 2:
                break
            await asyncio.sleep(0)
        self.assertEqual(started, {"a", "b"})
        release.set()
        await task

    async def test_driver_failure_does_not_claim_complete(self):
        async def failing(item, _):
            await asyncio.sleep(0)
            raise RuntimeError("real driver failed")
        canceled = [False]
        async def waiting(item, _):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                canceled[0] = True
                raise
        raw = make_plan(act("a", engine="dma0"),
                        act("b", actor="dma1", engine="dma1"))
        with TemporaryDirectory() as d:
            rec = ActionEventRecorder(raw, Path(d)/"action-events.jsonl", lambda: 0)
            dispatcher = ActionDispatcher(
                raw, {"dma.copy": lambda item, context: (
                    failing(item, context) if item["action_instance_id"] == "a"
                    else waiting(item, context))}, recorder=rec,
                max_inflight=2, task_backend="asyncio")
            with self.assertRaisesRegex(RuntimeError, "real driver failed"):
                await dispatcher.run()
            await asyncio.sleep(0)
            self.assertTrue(canceled[0])
            self.assertFalse(dispatcher.completed)
            self.assertEqual([json.loads(e)["stage"] for e in
                              (Path(d)/"action-events.jsonl").read_text().splitlines()],
                             ["issued", "issued"])
            rec.file.close()

    async def test_typed_capability_and_timeout(self):
        raw = make_plan(act("a", engine="dma0"))
        with self.assertRaisesRegex(ActionDispatchError, "rejects actor"):
            ActionDispatcher(raw, {"dma.copy": HandlerSpec(
                lambda *_: None, actors=frozenset({"cpu0"}))})
        with self.assertRaisesRegex(ActionDispatchError, "backend"):
            ActionDispatcher(raw, {"dma.copy": lambda *_: None},
                             max_inflight=2)
        with self.assertRaisesRegex(ActionDispatchError, "finite"):
            HandlerSpec(lambda *_: None, timeout=float("nan"))
        async def stall(item, context):
            await asyncio.Event().wait()
        with self.assertRaisesRegex(ActionDispatchError, "driver timeout"):
            await ActionDispatcher(raw, {"dma.copy": HandlerSpec(stall, timeout=0.001)},
                                   task_backend="asyncio").run()

    async def test_external_handler_requires_claims_and_rejects_unknown_actor(self):
        raw = make_plan(act("x", "ethernet.transmit", "cpu0", queue="tx0"))
        with self.assertRaisesRegex(ActionDispatchError, "resource contract"):
            ActionDispatcher(raw, {"ethernet.transmit": lambda *_: None},
                             max_inflight=2, task_backend="asyncio")
        seen = []
        async def transmit(item, _):
            seen.append(item["args"]["queue"])
        cap = HandlerSpec(transmit, actors=frozenset({"cpu0"}),
                          resources=lambda a: [ResourceClaim("eth_queue", a["args"]["queue"])])
        await ActionDispatcher(raw, {"ethernet.transmit": cap},
                               max_inflight=2, task_backend="asyncio").run()
        self.assertEqual(seen, ["tx0"])
        with self.assertRaisesRegex(ActionDispatchError, "unknown actor"):
            ActionDispatcher(make_plan(act("x", actor="ghost", engine="dma0")),
                             {"dma.copy": lambda *_: None})

    async def test_release_requires_every_consumer_dependency(self):
        raw = make_plan(
            act("allocate", "memory.allocate", buffer="src", region="sram"),
            act("consume", "memory.check", "checker0", deps=("allocate",), buffer="src"),
            act("release", "memory.release", deps=("allocate",),
                buffer="src", consumers_quiesced=True),
        )
        with self.assertRaisesRegex(ActionDispatchError, "early release"):
            ActionDispatcher(raw, {"memory.allocate": lambda *_: None,
                                   "memory.check": lambda *_: None,
                                   "memory.release": lambda *_: None})

    async def test_same_source_plan_serial_original_dispatch(self):
        raw = make_plan(act("first", "dma.configure", phase="init", engine="dma0",
                            descriptor_buffer="desc"),
                        act("second", deps=("first",), engine="dma0"))
        seen = []
        async def driver(item, _):
            seen.append(item["action_instance_id"])
        d = ActionDispatcher(raw, {"dma.configure": driver, "dma.copy": driver},
                             expected_sha=hashlib.sha256(raw).hexdigest())
        self.assertEqual(await d.run(), ["first", "second"])
        self.assertEqual(seen, ["first", "second"])
        with self.assertRaisesRegex(ActionDispatchError, "only be dispatched once"):
            await d.run()


    async def test_physical_alias_across_distinct_handles_serializes(self):
        """Two named buffers may alias one real memory aperture."""
        held = set()
        peak = [0]
        async def copy(item, _):
            held.add(item["action_instance_id"])
            peak[0] = max(peak[0], len(held))
            await asyncio.sleep(0)
            held.remove(item["action_instance_id"])

        raw_doc = json.loads(make_plan(
            act("a", engine="dma0", src="src_a", dst="dst_a"),
            act("b", actor="dma1", engine="dma1", src="src_b", dst="dst_b")))
        raw_doc["allocations"] = [
            {"buffer": "src_a", "region": "sram", "phys": 0x1000, "size": 64},
            {"buffer": "dst_a", "region": "sram", "phys": 0x2000, "size": 64},
            {"buffer": "src_b", "region": "sram", "phys": 0x1020, "size": 64},
            {"buffer": "dst_b", "region": "sram", "phys": 0x3000, "size": 64},
        ]
        raw = (json.dumps(raw_doc, sort_keys=True, separators=(",", ":")) + "\\n").encode()
        await ActionDispatcher(raw, {"dma.copy": copy},
                               max_inflight=2, task_backend="asyncio").run()
        self.assertEqual(peak, [1])

        raw_doc["allocations"][2]["phys"] = 0x1100  # no overlap
        raw = (json.dumps(raw_doc, sort_keys=True, separators=(",", ":")) + "\\n").encode()
        held.clear()
        peak[0] = 0
        await ActionDispatcher(raw, {"dma.copy": copy},
                               max_inflight=2, task_backend="asyncio").run()
        self.assertEqual(peak, [2])

    async def test_retirement_fence_keeps_lock_held(self):
        entered, drain = asyncio.Event(), asyncio.Event()
        seen = []
        async def drive(item, _):
            seen.append("driver_" + item["action_instance_id"])
        async def retire(item, _):
            if item["action_instance_id"] == "a":
                entered.set()
                await drain.wait()
        raw = make_plan(act("a", engine="dma0"),
                        act("b", actor="dma1", engine="dma0"))
        dispatcher = ActionDispatcher(
            raw, {"dma.copy": HandlerSpec(drive, retire=retire, timeout=1)},
            max_inflight=2, task_backend="asyncio")
        task = asyncio.create_task(dispatcher.run())
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        self.assertEqual(seen, ["driver_a"])
        self.assertNotIn("a", dispatcher.completed)
        drain.set()
        await task
        self.assertEqual(seen, ["driver_a", "driver_b"])

    async def test_release_requires_external_quiescence_guard(self):
        raw = make_plan(
            act("allocate", "memory.allocate", actor="cpu0",
                buffer="src", region="sram"),
            act("release", "memory.release", actor="dma0",
                deps=("allocate",), buffer="src", consumers_quiesced=True),
        )
        async def no_op(item, _):
            return None
        handlers = {"memory.allocate": no_op,
                    "memory.release": no_op}
        with self.assertRaisesRegex(ActionDispatchError, "externally observed quiescence"):
            ActionDispatcher(raw, handlers)
        async def not_quiescent(item, _):
            raise ActionDispatchError("outstanding AXI response")
        guarded = ActionDispatcher(
            raw, {"memory.allocate": no_op,
                  "memory.release": HandlerSpec(no_op, precondition=not_quiescent)})
        with self.assertRaisesRegex(ActionDispatchError, "outstanding AXI"):
            await guarded.run()
        self.assertNotIn("release", guarded.completed)

    async def test_missing_allocation_and_bad_byte_intervals_fail_closed(self):
        raw_doc = json.loads(make_plan(act("a", engine="dma0", src="src", dst="dst",
                                            length=16, src_offset=56)))
        raw_doc["allocations"] = [
            {"buffer": "src", "region": "sram", "phys": 0x1000, "size": 64},
            {"buffer": "dst", "region": "sram", "phys": 0x2000, "size": 64},
        ]
        raw = (json.dumps(raw_doc, sort_keys=True, separators=(",", ":")) + "\\n").encode()
        with self.assertRaisesRegex(ActionDispatchError, "invalid physical byte range"):
            ActionDispatcher(raw, {"dma.copy": lambda *_: None},
                             max_inflight=2, task_backend="asyncio")
        raw_doc["actions"][0]["args"]["src_offset"] = 0
        raw_doc["allocations"].pop()
        raw = (json.dumps(raw_doc, sort_keys=True, separators=(",", ":")) + "\\n").encode()
        with self.assertRaisesRegex(ActionDispatchError, "lacks resolved allocation"):
            ActionDispatcher(raw, {"dma.copy": lambda *_: None},
                             max_inflight=2, task_backend="asyncio")


if __name__ == "__main__":
    unittest.main()
