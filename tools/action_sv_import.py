#!/usr/bin/env python3
"""Import vetted SCN-3 SystemVerilog driver-only events into DV-EVENTS v2.

No driver transcript can manufacture passive AXI/PCIe/GMII/DFI acceptance.
The timestamp conversion factor is REQUIRED, never inferred from DUT clocks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dv.common.action_events import ActionEventRecorder, ActionEvidenceError, parse_plan, MAX_SAFE


def import_sv_driver(plan_bytes: bytes, report: dict, out: Path, *, tick_ps: int):
    plan, sha, actions = parse_plan(plan_bytes)
    if (type(tick_ps) is not int or not 1 <= tick_ps <= MAX_SAFE):
        raise ActionEvidenceError("explicit positive sim-tick-to-picosecond factor required")
    if (not isinstance(report, dict) or report.get("schema_version") != 1
            or report.get("kind") != "soc_scenario_sv_driver_events"
            or report.get("status") != "driver_log_unverified"
            or report.get("rtl_evidence") is not None
            or report.get("scenario_id") != plan["scenario_id"]
            or report.get("plan_sha256") != sha):
        raise ActionEvidenceError("SV report must be validated SCN-3 driver-only evidence")
    items = report.get("events")
    if (not isinstance(items, list) or report.get("event_count") != len(items)
            or len(items) > 200000):
        raise ActionEvidenceError("SV driver records missing or overflowed")
    now = [0]
    emitted = 0
    writer = ActionEventRecorder(plan_bytes, out, lambda: now[0],
                                 max_events=max(1, len(items)))
    try:
        for item in items:
            if not isinstance(item, dict) or item.get("rtl_observed") is not False or (
                    item.get("provenance") != "sv_driver_reported_only"):
                raise ActionEvidenceError("SV driver event falsely claims hardware provenance")
            aid = item.get("action_instance_id")
            action = actions.get(aid)
            if (action is None or item.get("scenario_id") != plan["scenario_id"] or
                    item.get("plan_sha256") != sha or
                    item.get("phase") != action["phase"] or
                    item.get("actor") != action["actor"] or
                    item.get("kind") != action["kind"]):
                raise ActionEvidenceError("SV event action/actor/phase/hash mismatch")
            stage = item.get("event")
            if stage not in ("issued", "driver_done"):
                raise ActionEvidenceError("SV event attempted protocol/checker stage")
            ticks = item.get("sim_ticks")
            if (type(ticks) is not int or not 0 <= ticks <= MAX_SAFE // tick_ps):
                raise ActionEvidenceError("SV timestamp is invalid or overflows JS-safe ps")
            now[0] = ticks * tick_ps
            writer.emit(aid, stage, "sv_driver")
            emitted += 1
        writer.close()
    except BaseException:
        if not writer.closed:
            writer.file.close()
            writer.closed = True
        out.unlink(missing_ok=True)
        raise
    return {"schema_version": 2, "kind": "sv_driver_event_import",
            "event_count": emitted, "plan_sha256": sha,
            "status": "driver_only_unverified", "rtl_evidence": None,
            "tick_ps": tick_ps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--sv-events", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tick-ps", type=int, required=True,
                        help="explicit simulator units: picoseconds per SV sim tick")
    args = parser.parse_args()
    try:
        result = import_sv_driver(args.plan.read_bytes(),
                                  json.loads(args.sv_events.read_text()), args.out,
                                  tick_ps=args.tick_ps)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(f"SCN-SV -> DV-EVENTS v2: {result['event_count']} driver-only actions; "
          "no passive RTL proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
