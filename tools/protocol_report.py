"""Schema-v1 protocol-neutral transaction/event reports from EXISTING monitors.

AXI stays owned by the pinned cocotbext-axi channels + axi_report correlator.
All other buses are opt-in: a verified VIP/testbench adapter emits events
using dv/common/protocol_trace.py. No protocol parsing/decoding is performed
here, and unknown protocols are not represented as AXI transactions.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import re
import sys
# Script entrypoints under tools/ must resolve the shared DV schema from repo root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from dv.common.protocol_trace import normalize_sources

PROTOCOL = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
SAFE_INT = 2**53 - 1
CAPTURE_NAME = "protocol-events.jsonl"
REPORT_NAME = "protocol-transactions.json"


def _integer(value, label):
    if type(value) is not int or not 0 <= value <= SAFE_INT:
        raise ValueError(f"{label}: invalid timestamp")
    return value


def _source(value):
    if not isinstance(value, str) or not PROTOCOL.fullmatch(value):
        raise ValueError(f"invalid monitor/source: {value!r}")
    return value


def _payload(value, depth=0):
    if depth > 5:
        raise ValueError("nested protocol fields too deep")
    if isinstance(value, (str, bool)) or value is None:
        return value
    if type(value) is int:
        if abs(value) > SAFE_INT:
            raise ValueError("integer field above JS safe range must be hex string")
        return value
    if isinstance(value, list) and len(value) <= 256:
        return [_payload(v, depth+1) for v in value]
    if isinstance(value, dict) and len(value) <= 128:
        if any(not isinstance(k, str) or len(k) > 100 for k in value):
            raise ValueError("invalid protocol fields")
        return {k: _payload(v, depth+1) for k,v in value.items()}
    raise ValueError("unsupported protocol field type")


def _record_source(entry):
    return {"id": _source(entry["id"]),
            "protocol": _source(entry["protocol"]),
            "role": entry.get("role", "unspecified"),
            "clock_domain": entry.get("clock_domain", "unknown"),
            "implementation": entry.get("implementation", "unrecorded")}


def adapt_axi(payload):
    """Project a *completed AXI correlator result* into generic transaction rows.

    Keep AXI evidence unchanged; this is a read-only view, not another
    monitor, protocol VIP, or in-flight reconstruction.
    """
    catalog = payload["sections"]["axi"]["monitors"]
    monitors = {
        m["id"]: {"id": m["id"], "protocol": "axi4",
                  "role": m["role"], "clock_domain": "soc_single_clock",
                  "implementation": m.get("actor", {}).get("kind", "unknown")}
        for m in catalog
    }
    records = []
    for txn in payload["sections"]["axi"]["transactions"]:
        source = txn["monitor"]
        if source not in monitors:
            raise ValueError(f"uncataloged AXI monitor in generic view: {source}")
        records.append({
            "kind": "transaction", "source": source, "protocol": "axi4",
            "operation": txn["operation"],
            "id": txn.get("axi_id"), "start_ps": txn["start_ps"],
            "end_ps": txn["end_ps"], "status": txn["status"],
            "fields": {
                "address": txn["address"], "region": txn["region"],
                "response": txn.get("response"),
                "beats": len(txn["beats"]),
                "expected_beats": txn["expected_beats"],
                "error_intent": txn.get("error_intent", "none"),
                "role": txn["role"], "plane": txn["plane"],
                "actor": txn.get("actor", {}).get("label", ""),
                "issues": txn.get("issues", []),
            }
        })
    return {"sources": list(monitors.values()), "records": records}


def parse_capture(path: Path, configured_sources: dict):
    """Require start/end provenance and exact monitor inventory on PASS.

    Partial failed simulations may still produce useful rows and diagnostics;
    never turn an incomplete capture into a successful measurement.
    """
    if not path.is_file():
        raise ValueError("configured protocol capture missing")
    sources = normalize_sources(configured_sources)
    if not sources:
        raise ValueError("empty protocol capture catalog")
    lines = path.read_text().splitlines()
    if not lines:
        raise ValueError("empty protocol capture")
    starts, ends, counts = set(), set(), {name: 0 for name in sources}
    failed_sources = set()
    last_times = {name: 0 for name in sources}
    records = []
    for line_no,line in enumerate(lines, 1):
        try:
            event=json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed protocol event line {line_no}") from exc
        if not isinstance(event, dict) or event.get("version") != 1:
            raise ValueError(f"unsupported protocol event version at line {line_no}")
        source = _source(event.get("source"))
        if source not in sources:
            raise ValueError(f"uncataloged protocol monitor {source}")
        kind = event.get("type")
        if kind not in ("start", "end", "event", "transaction"):
            raise ValueError(f"unsupported event kind {kind}")
        if kind == "start":
            if source in starts or counts[source] or source in ends or event.get("protocol") != sources[source]["protocol"]:
                raise ValueError("invalid or duplicate capture_start")
            for attr in ("clock_domain", "role", "implementation", "modeling"):
                if event.get(attr) != sources[source][attr]:
                    raise ValueError(f"protocol source metadata changed: {source}.{attr}")
            starts.add(source)
            continue
        if source not in starts or source in ends:
            raise ValueError("events outside source start/end interval")
        if kind == "end":
            if event.get("count") != counts[source] or event.get("status") not in ("pass","fail"):
                raise ValueError("incomplete or invalid capture_end")
            ends.add(source)
            if event['status'] != 'pass':
                failed_sources.add(source)
            continue
        time_ps = _integer(event.get("time_ps"), "time_ps")
        if kind == "transaction":
            start = _integer(event.get("start_ps"), "start_ps")
            end = event.get("end_ps")
            if end is not None:
                _integer(end, "end_ps")
                if end < start:
                    raise ValueError("protocol transaction has negative latency")
            if time_ps != (end if end is not None else start):
                raise ValueError("transaction timestamp differs from observed boundary")
            if event.get("status") == "complete" and end is None:
                raise ValueError("completed protocol transaction has no observed end")
            if event.get("status") not in ("complete","incomplete","reset_aborted","error"):
                raise ValueError("invalid protocol transaction status")
            operation = _source(event.get("operation"))
        else:
            operation = _source(event.get("name"))
        if time_ps < last_times[source]:
            raise ValueError("out-of-order protocol event timestamp")
        last_times[source] = time_ps
        counts[source] += 1
        fields = _payload(event.get("fields", {}))
        records.append({
            "kind": kind, "source": source, "protocol": sources[source]["protocol"],
            "operation": operation, "id": _payload(event.get("id")),
            "start_ps": event.get("start_ps", time_ps),
            "end_ps": event.get("end_ps", time_ps) if kind == "event" else event.get("end_ps"),
            "status": "observed" if kind == "event" else event["status"],
            "fields": fields,
        })
    if starts != set(sources) or ends != set(sources):
        raise ValueError("protocol capture missing one or more required start/end markers")
    if failed_sources:
        raise ValueError('protocol capture ended with failure: ' + ', '.join(sorted(failed_sources)))
    return {"sources": list(sources.values()),
            "records": records, "events": counts}


def build(directory: Path, plan: dict, *, axi_payload=None):
    """Produce one JSON result for AXI + any opt-in external VIP adapters."""
    reported = plan.get("report") or {}
    sources, records, issues = [], [], []
    if axi_payload is not None:
        axi = adapt_axi(axi_payload)
        sources += axi["sources"]
        records += axi["records"]
    configured = reported.get("protocols")
    if configured is not None:
        try:
            captured = parse_capture(directory / CAPTURE_NAME, configured["sources"])
            if set(s["id"] for s in captured["sources"]) & set(s["id"] for s in sources):
                raise ValueError("protocol monitor ID collides with AXI monitor ID")
            sources += captured["sources"]
            records += captured["records"]
        except ValueError as error:
            issues.append(str(error))
    if not sources and configured is None:
        return None
    if axi_payload is None:
        try:
            sha = subprocess.check_output(['git','rev-parse','HEAD'],
                                          cwd=Path(__file__).resolve().parents[1], text=True).strip()
            dirty = bool(subprocess.check_output(['git','status','--porcelain'],
                         cwd=Path(__file__).resolve().parents[1],text=True))
        except (OSError,subprocess.CalledProcessError):
            sha, dirty = 'unknown', True
        run = {"target": plan["target"], "engine": plan["engine"],
               "commit": sha, "dirty": dirty,
               "workflow_run_id": os.environ.get('GITHUB_RUN_ID'),
               "workflow_attempt": os.environ.get('GITHUB_RUN_ATTEMPT')}
    else:
        run = dict(axi_payload['run'])
    result = {"schema_version": 1,
              "run": run,
              "sources": sources, "records": records,
              "capture_complete": not issues,
              "issues": issues,
              "modeling": "observations from existing VIPs/testbenches only; no inferred bus operations"}
    (directory/REPORT_NAME).write_text(json.dumps(result,indent=2)+"\n")
    render(result, directory/"protocols.html")
    return result


def render(data, path):
    # Never let the JSON embedded in HTML terminate the script tag.
    template=(Path(__file__).resolve().parent/"templates/protocol_report.html").read_text()
    value=json.dumps(data,separators=(",",":")).replace("<","\\u003c")
    Path(path).write_text(template.replace("__PROTOCOL_DATA__",value))
