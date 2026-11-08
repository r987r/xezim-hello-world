"""Execute the existing SCN-1 selected action DAG through typed adapters.

This module is deliberately NOT another planner, allocator, phase owner or
test-flow reporter. Resource locks protect *driver* concurrency only.
'driver_done' MUST NOT be treated as protocol_accepted/device_completed/
independently_checked; passive AXI/TLP/GMII/DFI and the existing independent
scoreboards remain authoritative. Serial behavior is backwards compatible.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
import math
from typing import Any

from dv.common.action_events import ActionEvidenceError, parse_plan

PHASES = ("init", "run", "check")
Handler = Callable[[dict, Any], Awaitable[None]]
ClaimProvider = Callable[[dict], Iterable["ResourceClaim"]]


class ActionDispatchError(ActionEvidenceError):
    """A selected source action cannot safely execute as declared."""


@dataclass(frozen=True)
class ResourceClaim:
    """Version-1 driver resource intent; read/read may overlap, writes exclude."""
    category: str
    name: str
    access: str = "write"

    def __post_init__(self):
        if (not isinstance(self.category, str) or not self.category or
                not isinstance(self.name, str) or not self.name or
                self.access not in ("read", "write")):
            raise ActionDispatchError("invalid typed resource claim")


@dataclass(frozen=True)
class HandlerSpec:
    """Versioned action capability, never an assertion of hardware completion.

    A handler can be the existing Python/C-firmware/SV adapter. Allowed actors
    and supplementary claims are part of its registered runtime capability;
    an unknown action kind must supply its own claim provider for concurrency.
    Timeout is wall seconds for asyncio and simulation nanoseconds for cocotb.
    """
    execute: Handler
    version: int = 1
    actors: frozenset[str] | None = None
    resources: ClaimProvider | None = None
    timeout: float | None = None

    def __post_init__(self):
        if not callable(self.execute) or type(self.version) is not int or self.version != 1:
            raise ActionDispatchError("handler capability must be callable action-v1")
        if (self.actors is not None and
                (not isinstance(self.actors, frozenset) or
                 not self.actors or any(not isinstance(a, str) or not a for a in self.actors))):
            raise ActionDispatchError("handler actors must be nonempty typed set")
        if self.resources is not None and not callable(self.resources):
            raise ActionDispatchError("resource claims must come from a registered callable")
        if self.timeout is not None and (
                type(self.timeout) not in (int, float) or
                not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ActionDispatchError("handler timeout must be finite and positive")


def _field(action: dict, name: str) -> str:
    value = action.get("args", {}).get(name)
    if not isinstance(value, str) or not value:
        raise ActionDispatchError(
            f"{action['action_instance_id']}: missing typed {name} resource")
    return value


def _default_claims(action: dict) -> tuple[ResourceClaim, ...] | None:
    """Only the 7 SCN-v1 kinds have implicit typed resource meanings."""
    kind = action["kind"]
    if kind == "memory.allocate":
        return (ResourceClaim("region", _field(action, "region")),
                ResourceClaim("buffer", _field(action, "buffer")))
    if kind == "memory.initialize":
        return (ResourceClaim("buffer", _field(action, "buffer")),)
    if kind == "memory.check":
        result = [ResourceClaim("buffer", _field(action, "buffer"), "read")]
        if "expected_from" in action.get("args", {}):
            result.append(ResourceClaim("buffer", _field(action, "expected_from"), "read"))
        return tuple(result)
    if kind == "memory.release":
        return (ResourceClaim("buffer", _field(action, "buffer")),)
    if kind == "dma.configure":
        return (ResourceClaim("engine", _field(action, "engine")),
                ResourceClaim("buffer", _field(action, "descriptor_buffer"), "read"))
    if kind == "dma.copy":
        return (ResourceClaim("engine", _field(action, "engine")),
                ResourceClaim("buffer", _field(action, "src"), "read"),
                ResourceClaim("buffer", _field(action, "dst")))
    if kind == "dma.wait_idle":
        return (ResourceClaim("engine", _field(action, "engine")),)
    return None


def _claims(action: dict, registration: HandlerSpec) -> tuple[ResourceClaim, ...]:
    # Same actor has a single command stream unless it declares multiple
    # separately named actors. Do not accidentally issue two DMA commands
    # concurrently to the same CSR/descriptor slot.
    claims = [ResourceClaim("actor", action["actor"])]
    builtin = _default_claims(action)
    if builtin is None and registration.resources is None:
        raise ActionDispatchError(
            f"{action['action_instance_id']}: unknown action requires a resource contract")
    if builtin is not None:
        claims.extend(builtin)
    if registration.resources is not None:
        extra = registration.resources(action)
        if extra is None:
            raise ActionDispatchError("resource contract returned no claims")
        claims.extend(extra)
    if any(not isinstance(c, ResourceClaim) for c in claims):
        raise ActionDispatchError("resource contract returned non-typed claim")
    # Duplicate read/write claims for a resource collapse conservatively to
    # an exclusive write, never discard a write in favor of a shared read.
    merged = {}
    for claim in claims:
        key = claim.category, claim.name
        old = merged.get(key)
        merged[key] = ("write" if claim.access == "write" or old == "write"
                       else "read")
    return tuple(ResourceClaim(kind, name, mode)
                 for (kind, name), mode in sorted(merged.items()))


def _conflict(a: tuple[ResourceClaim, ...],
              b: tuple[ResourceClaim, ...]) -> bool:
    held = {(c.category, c.name): c.access for c in a}
    return any((c.category, c.name) in held and
               (c.access == "write" or held[c.category, c.name] == "write")
               for c in b)


def _validate_release_order(plan: dict, by_id: dict[str, dict]) -> None:
    """Reject a raw canonical plan that frees a still-live driver resource.

    The SCN resolver also validates physical lifetimes. Runtime must not
    trust a hand-authored canonical JSON that skipped that resolver.
    This does not *prove* hardware quiescence: the release adapter must still
    wait for real AXI/TLP/CQ/descriptor retirement before completing.
    """
    for action in plan["actions"]:
        if action["kind"] != "memory.release":
            continue
        args = action.get("args", {})
        aid = action["action_instance_id"]
        buffer = _field(action, "buffer")
        if args.get("consumers_quiesced") is not True:
            raise ActionDispatchError(f"{aid}: release requires quiescence precondition")
        ancestors = set()
        stack = list(action["depends_on"])
        while stack:
            parent = stack.pop()
            if parent not in ancestors:
                ancestors.add(parent)
                stack.extend(by_id[parent]["depends_on"])
        allocations = [a for a in plan["actions"]
                       if a["kind"] == "memory.allocate"
                       and a.get("args", {}).get("buffer") == buffer]
        if len(allocations) != 1 or allocations[0]["action_instance_id"] not in ancestors:
            raise ActionDispatchError(f"{aid}: release lacks one causal allocation")
        for other in plan["actions"]:
            oid = other["action_instance_id"]
            if oid == aid:
                continue
            if buffer in (other.get("args", {}).get(key)
                          for key in ("buffer", "src", "dst", "descriptor_buffer",
                                      "expected_from")) and oid not in ancestors:
                raise ActionDispatchError(
                    f"{aid}: early release before consumer {oid} retired")


class _Tasks:
    """Adapter for either pure Python or cocotb; no new simulation engine."""
    def __init__(self, backend: str):
        if backend not in ("asyncio", "cocotb"):
            raise ActionDispatchError("parallel actions require asyncio or cocotb backend")
        self.backend = backend

    def start(self, coroutine):
        if self.backend == "asyncio":
            return asyncio.create_task(coroutine)
        import cocotb
        return cocotb.start_soon(coroutine)

    async def wait_any(self, tasks):
        if self.backend == "asyncio":
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        else:
            from cocotb.triggers import First
            await First(*tasks)

    def cancel(self, task):
        if not task.done():
            if self.backend == "asyncio":
                task.cancel()
            else:
                task.kill()


class ActionDispatcher:
    """One selected plan, explicit actors, typed adapters and resource fences.

    max_inflight=1 retains the original exact serial semantics and doesn't
    require an event-loop backend. Parallel dispatch is opt-in and must name
    an actual scheduler backend so cocotb Tasks are never confused with
    asyncio Tasks. Phase barriers and dependency edges always remain strict.
    """

    def __init__(self, plan_bytes: bytes,
                 handlers: dict[str, Handler | HandlerSpec], *,
                 recorder=None, expected_sha: str | None = None,
                 max_inflight: int = 1, task_backend: str | None = None):
        self.plan, self.sha, self.by_id = parse_plan(plan_bytes)
        if expected_sha is not None and self.sha != expected_sha:
            raise ActionDispatchError("selected plan SHA disagrees with runtime adapter")
        if type(max_inflight) is not int or not 1 <= max_inflight <= 64:
            raise ActionDispatchError("max_inflight must be integer in [1,64]")
        if max_inflight > 1 and task_backend not in ("asyncio", "cocotb"):
            raise ActionDispatchError("parallel action backend must be explicit")
        if task_backend is not None and task_backend not in ("asyncio", "cocotb"):
            raise ActionDispatchError("unknown action task backend")
        if not isinstance(handlers, dict) or any(
                not isinstance(kind, str) or
                not (callable(fn) or isinstance(fn, HandlerSpec))
                for kind, fn in handlers.items()):
            raise ActionDispatchError("invalid typed handler registry")
        self.registrations = {
            kind: fn if isinstance(fn, HandlerSpec) else HandlerSpec(fn)
            for kind, fn in handlers.items()
        }
        missing = set(a["kind"] for a in self.by_id.values()) - set(handlers)
        if missing:
            raise ActionDispatchError(f"no registered handler for {sorted(missing)}")
        actors = self.plan.get("actors")
        if not isinstance(actors, list) or len(actors) != len(set(actors)):
            raise ActionDispatchError("selected plan has invalid actor declaration")
        for action in self.plan["actions"]:
            actor = action["actor"]
            spec = self.registrations[action["kind"]]
            if actor not in actors:
                raise ActionDispatchError(f"{action['action_instance_id']}: unknown actor {actor}")
            if spec.actors is not None and actor not in spec.actors:
                raise ActionDispatchError(
                    f"{action['action_instance_id']}: handler capability rejects actor {actor}")
            if spec.timeout is not None and task_backend is None:
                raise ActionDispatchError("timed handler needs explicitly selected task backend")
        _validate_release_order(self.plan, self.by_id)
        self.claims = ({
            action["action_instance_id"]: _claims(
                action, self.registrations[action["kind"]])
            for action in self.plan["actions"]
        } if max_inflight > 1 else {})
        self.handlers = {kind: spec.execute for kind, spec in self.registrations.items()}
        self.recorder = recorder
        if recorder is not None and (recorder.sha != self.sha or
                                     set(recorder.actions) != set(self.by_id)):
            raise ActionDispatchError("recorder does not belong to selected plan")
        self.max_inflight = max_inflight
        self.task_backend = task_backend
        self.completed: set[str] = set()
        self.started = False

    async def _execute(self, action: dict, context: Any):
        spec = self.registrations[action["kind"]]
        work = spec.execute(action, context)
        if spec.timeout is None:
            return await work
        try:
            if self.task_backend == "asyncio":
                return await asyncio.wait_for(work, spec.timeout)
            from cocotb.triggers import with_timeout
            return await with_timeout(work, spec.timeout, "ns")
        except (asyncio.TimeoutError,) as exc:
            raise ActionDispatchError(
                f"{action['action_instance_id']}: driver timeout") from exc
        except BaseException as exc:
            if self.task_backend == "cocotb" and type(exc).__name__ == "SimTimeoutError":
                raise ActionDispatchError(
                    f"{action['action_instance_id']}: driver timeout") from exc
            raise

    def _issued(self, action):
        if self.recorder is not None:
            self.recorder.emit(action["action_instance_id"], "issued", "python_driver")

    def _done(self, action):
        if self.recorder is not None:
            self.recorder.emit(action["action_instance_id"], "driver_done", "python_driver")
        self.completed.add(action["action_instance_id"])

    async def run(self, context: Any = None) -> list[str]:
        if self.started:
            raise ActionDispatchError("one runtime plan can only be dispatched once")
        self.started = True
        if self.max_inflight == 1:
            # Preserve shipped SCN-2 C/AXI BFM order and driver event ABI.
            for phase in PHASES:
                remaining = [a for a in self.plan["actions"] if a["phase"] == phase]
                while remaining:
                    ready = next((a for a in remaining if
                                  set(a["depends_on"]).issubset(self.completed)), None)
                    if ready is None:
                        raise ActionDispatchError(
                            f"{phase}: no ready action; dependency not driver-completed")
                    self._issued(ready)
                    await self._execute(ready, context)
                    self._done(ready)
                    remaining.remove(ready)
        else:
            tasks = _Tasks(self.task_backend)
            for phase in PHASES:
                pending = [a for a in self.plan["actions"] if a["phase"] == phase]
                active = {}  # backend Task -> action
                try:
                    while pending or active:
                        for action in list(pending):
                            if len(active) == self.max_inflight:
                                break
                            if not set(action["depends_on"]).issubset(self.completed):
                                continue
                            aid = action["action_instance_id"]
                            if any(_conflict(self.claims[aid],
                                             self.claims[running["action_instance_id"]])
                                   for running in active.values()):
                                continue
                            self._issued(action)
                            task = tasks.start(self._execute(action, context))
                            active[task] = action
                            pending.remove(action)
                        if not active:
                            raise ActionDispatchError(
                                f"{phase}: no ready action; unresolved dependency or resource")
                        await tasks.wait_any(tuple(active))
                        # Same-tick completions use selected source order, so
                        # event ordering is stable for an otherwise equal trace.
                        for task, action in list(active.items()):
                            if not task.done():
                                continue
                            task.result()  # original exception wins; no false driver_done
                            self._done(action)
                            del active[task]
                finally:
                    # Only tasks created by this typed dispatcher are canceled.
                    # Never cancel source/target passive AXI/TLP/DFI observers.
                    for task in active:
                        tasks.cancel(task)
        if len(self.completed) != len(self.by_id):
            raise ActionDispatchError("runtime plan omitted source-selected actions")
        return [a["action_instance_id"] for a in self.plan["actions"]
                if a["action_instance_id"] in self.completed]
