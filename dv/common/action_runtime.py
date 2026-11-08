"""Execute the existing SCN-1 resolved action DAG through typed Python handlers.

This is the dispatch layer, not a second scenario compiler or a second
INIT/RUN/CHECK reporter. Driver events do NOT prove accepted hardware traffic.
The existing passive AXI/protocol collectors and independent checkers own that.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from dv.common.action_events import ActionEvidenceError, parse_plan

PHASES = ("init", "run", "check")
Handler = Callable[[dict, Any], Awaitable[None]]


class ActionDispatchError(ActionEvidenceError):
    """A selected source action could not be dispatched as specified."""


class ActionDispatcher:
    """Deterministically dispatch one canonical plan, with no opaque fallback.

    Handlers receive the full resolved action (including typed args); their
    implementation must use those args to drive the genuine C/SV/Cocotb path.
    Dependencies are driver-order constraints; hardware completion is proven
    separately by passive monitors and independent checkers.
    """

    def __init__(self, plan_bytes: bytes, handlers: dict[str, Handler], *,
                 recorder=None, expected_sha: str | None = None):
        self.plan, self.sha, self.by_id = parse_plan(plan_bytes)
        if expected_sha is not None and self.sha != expected_sha:
            raise ActionDispatchError("selected plan SHA disagrees with runtime adapter")
        if not isinstance(handlers, dict) or any(
                not isinstance(key, str) or not callable(fn)
                for key, fn in handlers.items()):
            raise ActionDispatchError("invalid typed handler registry")
        missing = set(a["kind"] for a in self.by_id.values()) - set(handlers)
        if missing:
            raise ActionDispatchError(f"no registered handler for {sorted(missing)}")
        self.handlers = handlers
        self.recorder = recorder
        if recorder is not None and (recorder.sha != self.sha or
                                     set(recorder.actions) != set(self.by_id)):
            raise ActionDispatchError("recorder does not belong to selected plan")
        self.completed: set[str] = set()
        self.started = False

    async def run(self, context: Any = None) -> list[str]:
        if self.started:
            raise ActionDispatchError("one runtime plan can only be dispatched once")
        self.started = True
        # Honor source order for independent actions; a dependency can move
        # its child later. Never infer execution from phase labels alone.
        for phase in PHASES:
            remaining = [a for a in self.plan["actions"] if a["phase"] == phase]
            while remaining:
                ready = next((a for a in remaining if
                              set(a["depends_on"]).issubset(self.completed)), None)
                if ready is None:
                    raise ActionDispatchError(
                        f"{phase}: no ready action; dependency not driver-completed")
                aid = ready["action_instance_id"]
                if self.recorder is not None:
                    self.recorder.emit(aid, "issued", "python_driver")
                # An exception intentionally leaves the action issued but
                # unfinished. The partial original log is never promoted.
                await self.handlers[ready["kind"]](ready, context)
                if self.recorder is not None:
                    self.recorder.emit(aid, "driver_done", "python_driver")
                self.completed.add(aid)
                remaining.remove(ready)
        if len(self.completed) != len(self.by_id):
            raise ActionDispatchError("runtime plan omitted source-selected actions")
        return list(self.completed)
