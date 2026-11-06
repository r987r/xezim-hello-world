"""Single run-wide INIT/RUN/CHECK step evidence ABI, independent of VIP.

Drivers (Python, Cocotb, remote host adapters) emit explicit step spans.
RTL/C cannot assert completion via Python: their observed firmware/MMIO
events must be supplied as separate 'rtl_observed' evidence by the checker.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json
import re

ID = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
PHASES = ("init", "run", "check")
STATES = ("start", "pass", "fail")
ORIGINS = ("stimulus", "observed", "rtl_observed", "checker")


def validate_event(e):
    needed = {"schema_version", "seq", "time_ps", "phase", "actor", "step",
              "status", "origin", "details"}
    if not isinstance(e, dict) or set(e) != needed or e["schema_version"] != 1:
        raise ValueError("invalid test-flow record schema")
    if e["phase"] not in PHASES or e["status"] not in STATES or e["origin"] not in ORIGINS:
        raise ValueError("invalid test-flow phase, status, or origin")
    for k in ("actor", "step"):
        if not isinstance(e[k], str) or not ID.fullmatch(e[k]):
            raise ValueError(f"invalid test-flow {k}")
    for k in ("seq", "time_ps"):
        if type(e[k]) is not int or not 0 <= e[k] <= 2**53-1:
            raise ValueError(f"invalid test-flow {k}")
    if type(e["details"]) is not dict or len(e["details"]) > 24:
        raise ValueError("invalid test-flow details")
    for k, v in e["details"].items():
        if not isinstance(k, str) or not ID.fullmatch(k) or type(v) not in (str, int, bool):
            raise ValueError("test-flow details must be named scalars")
        if isinstance(v, str) and len(v) > 512:
            raise ValueError("test-flow detail too long")
    return e


class StepRecorder:
    """No silent closing of uncompleted actions; always flush on every event."""
    def __init__(self, output, clock_ps, *, enabled=True):
        self.output = Path(output)
        self.clock_ps = clock_ps
        self.seq = 0
        self.pending = {}
        self.closed = False
        self.stream = None
        if enabled:
            self.output.parent.mkdir(parents=True, exist_ok=True)
            if self.output.is_symlink():
                raise ValueError("refusing symlink test flow capture")
            self.stream = self.output.open("w", encoding="utf-8", buffering=1)

    def emit(self, phase, actor, step, status, origin, details=None):
        if self.closed:
            raise AssertionError("test-flow recorder already closed")
        event = validate_event({
            "schema_version":1, "seq":self.seq, "time_ps":int(self.clock_ps()),
            "phase":phase, "actor":actor, "step":step, "status":status,
            "origin":origin, "details":details or {},
        })
        key = (phase, actor, step)
        if status == "start":
            if key in self.pending:
                raise AssertionError(f"duplicate in-flight test step: {key}")
            self.pending[key] = event["time_ps"]
        else:
            if key not in self.pending:
                raise AssertionError(f"test step completed without start: {key}")
            if event["time_ps"] < self.pending.pop(key):
                raise AssertionError("test-flow clock went backward")
        self.seq += 1
        if self.stream is not None:
            self.stream.write(json.dumps(event, separators=(",", ":"), sort_keys=True)+"\n")
        return event

    @contextmanager
    def step(self, phase, actor, name, *, origin="stimulus", details=None):
        self.emit(phase, actor, name, "start", origin, details)
        try:
            yield
        except BaseException as exc:
            self.emit(phase, actor, name, "fail", origin, {"error":str(exc)[:512]})
            raise
        else:
            self.emit(phase, actor, name, "pass", origin, details)

    def close(self):
        if self.closed:
            raise AssertionError("double-close of test-flow recorder")
        self.closed = True
        if self.stream:
            self.stream.close()
        if self.pending:
            raise AssertionError(f"incomplete test-flow steps: {sorted(self.pending)}")


_active = None


def attach_from_plan(clock_ps):
    """Call before stimulus; the established regression plan enables it."""
    global _active
    import os
    path = os.environ.get("SOC_RUN_PLAN")
    if not path:
        return None
    plan_path = Path(path)
    plan = json.loads(plan_path.read_text())
    if "flow" not in plan.get("report", {}):
        return None
    if _active is not None:
        raise AssertionError("test-flow recorder attached twice")
    _active = StepRecorder(plan_path.parent/"test-flow-events.jsonl", clock_ps)
    return _active


def active():
    return _active


def close_active():
    global _active
    if _active is not None:
        recorder = _active
        _active = None
        recorder.close()
