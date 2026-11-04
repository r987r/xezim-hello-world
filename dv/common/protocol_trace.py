"""Protocol-neutral event exporter for EXISTING cocotb/VIP monitors.

This module does not sample pins, interpret bus handshakes or implement a VIP.
A testbench calls it with observations received from its upstream AXI, DFI,
APB, AXI-Stream, Ethernet, PCIe or other library. The protocol reporter is
responsible only for evidence, not for asserting protocol correctness.

One test-run JSONL stream can have multiple source monitors and clock domains.
Call open_from_plan() before starting DUT clocks; always close() in finally.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

SOURCE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
SAFE_INT = 2**53 - 1


def json_fields(value, depth=0):
    """Preserve >53-bit RTL values losslessly for JSON and JavaScript."""
    if depth > 5:
        raise ValueError("protocol fields nesting too deep")
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) is int:
        return value if -SAFE_INT <= value <= SAFE_INT else hex(value)
    if isinstance(value, dict):
        if len(value) > 128 or any(not isinstance(k, str) or len(k) > 100 for k in value):
            raise ValueError("invalid protocol fields keys")
        return {k: json_fields(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)) and len(value) <= 256:
        return [json_fields(v, depth + 1) for v in value]
    raise ValueError("protocol field must be JSON-safe scalar/list/dict; floating-point bus data is unsupported")


def _slug(label, kind):
    if not isinstance(label, str) or not SOURCE_RE.fullmatch(label):
        raise ValueError(f"invalid {kind} name {label!r}")
    return label


def _time(value, kind):
    if type(value) is not int or not 0 <= value <= SAFE_INT:
        raise ValueError(f"{kind} must be nonnegative integral picoseconds <= 2^53-1")
    return value


class ProtocolTrace:
    """Line-flushed, fail-closed capture lifecycle; never a bus driver."""
    def __init__(self, output: Path, sources: dict[str, str], max_events=100000):
        if not isinstance(sources, dict) or not sources:
            raise ValueError("nonempty protocol monitor catalog required")
        if type(max_events) is not int or max_events < 1:
            raise ValueError("invalid max protocol events")
        self.output = Path(output)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if self.output.is_symlink():
            raise ValueError("refusing symlinked protocol capture")
        self.stream = self.output.open("w", encoding="utf-8", buffering=1)
        self.sources = {_slug(k, "source"): _slug(v, "protocol") for k, v in sources.items()}
        self.limit = max_events
        self.counts = {k: 0 for k in self.sources}
        self.times = {k: 0 for k in self.sources}
        self.closed = False
        for name, protocol in self.sources.items():
            self._write({"version": 1, "type": "start", "source": name,
                         "protocol": protocol, "time_ps": 0})

    def _write(self, record):
        if self.closed:
            raise AssertionError("protocol capture ended before all observations")
        self.stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")

    def _accept(self, source, time_ps):
        if source not in self.sources:
            raise ValueError(f"protocol observation from uncataloged monitor: {source}")
        if self.counts[source] >= self.limit:
            raise AssertionError("protocol capture overflow: incomplete evidence")
        t = _time(time_ps, "time_ps")
        if t < self.times[source]:
            raise AssertionError("out-of-order protocol timestamp")
        self.times[source] = t
        self.counts[source] += 1

    def event(self, source, name, time_ps, fields=None):
        """An observed event, e.g. Ethernet frame RX, DFI command, APB setup."""
        _slug(name, "event")
        self._accept(source, time_ps)
        self._write({"version": 1, "type": "event", "source": source,
                     "name": name, "time_ps": time_ps,
                     "fields": json_fields(fields or {})})

    def transaction(self, source, operation, start_ps, end_ps=None, *,
                    identifier=None, fields=None, status=None):
        """Start/end timestamps MUST come from actual captured VIP events."""
        _slug(operation, "operation")
        _time(start_ps, "start_ps")
        if end_ps is not None:
            _time(end_ps, "end_ps")
            if end_ps < start_ps:
                raise ValueError("observed transaction end precedes start")
        if status is None:
            status = "complete" if end_ps is not None else "incomplete"
        if status not in ("complete", "incomplete", "reset_aborted", "error"):
            raise ValueError("unsupported transaction capture state")
        if status == "complete" and end_ps is None:
            raise ValueError("completed transaction missing observed end")
        self._accept(source, max(start_ps, end_ps or start_ps))
        self._write({"version": 1, "type": "transaction", "source": source,
                     "operation": operation, "start_ps": start_ps, "end_ps": end_ps,
                     "id": json_fields(identifier), "status": status,
                     "fields": json_fields(fields or {})})

    def close(self, status="pass", error=None):
        if self.closed:
            raise AssertionError("protocol trace already finalized")
        if status not in ("pass", "fail"):
            raise ValueError("invalid protocol trace result")
        for name in self.sources:
            self._write({"version": 1, "type": "end", "source": name,
                         "time_ps": self.times[name], "status": status,
                         "count": self.counts[name], "error": str(error) if error else None})
        self.stream.close()
        self.closed = True


def open_from_plan(path=None):
    """Opt-in for any TB with SOC_RUN_PLAN; no implicit active pin monitor."""
    path = Path(path or os.environ["SOC_RUN_PLAN"])
    plan = json.loads(path.read_text())
    cfg = plan.get("report", {}).get("protocols")
    if cfg is None:
        return None
    return ProtocolTrace(path.parent / "protocol-events.jsonl",
                         cfg["sources"], cfg.get("max_events", 100000))
