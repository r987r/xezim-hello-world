#!/usr/bin/env python3
"""DV-EVENTS: validate action claims against existing passive protocol artifacts.

AXI/other VIP correlation stays owned by axi_report.py/protocol_report.py.
Driver logs alone are NEVER hardware proof. This is a separate opt-in
report, not another INIT/RUN/CHECK scheduler or source of fake RTL PASS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from dv.common.action_events import ActionEvidenceError, parse_plan, validate_event


def num(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    raise ActionEvidenceError(f"invalid measured numeric field {value!r}")


def passive_rows(axi=None, protocols=None):
    rows = {"axi": {}, "protocol": {}}
    if axi is not None:
        run, section = axi.get("run", {}), axi.get("sections", {}).get("axi", {})
        if (run.get("capture_bound") is not True or
                run.get("capture_overflow") is not False or section.get("issues") or
                not isinstance(section.get("transactions"), list)):
            raise ActionEvidenceError("AXI capture incomplete, overflowed or failed")
        for row in section["transactions"]:
            uid, monitor = row.get("uid"), row.get("monitor")
            if (not isinstance(uid, str) or not isinstance(monitor, str)
                    or not uid.startswith(monitor + ":") or uid in rows["axi"]):
                raise ActionEvidenceError("AXI scoped transaction UID missing or duplicate")
            rows["axi"][uid] = row
    if protocols is not None:
        if protocols.get("capture_complete") is not True or protocols.get("issues"):
            raise ActionEvidenceError("protocol VIP capture incomplete or failed")
        records = protocols.get("records")
        if not isinstance(records, list):
            raise ActionEvidenceError("protocol records missing")
        for i, row in enumerate(records):
            # AXI projection cannot replace authoritative scoped AXI rows.
            if row.get("protocol") != "axi4":
                rows["protocol"][f"record:{i}"] = row
    return rows


def observed_time(capture, stage, row):
    if capture == "axi":
        if row.get("status") != "complete" or row.get("issues") or row.get("end_ps") is None:
            raise ActionEvidenceError("passive AXI transaction not fully correlated")
        if num(row.get("response")) != 0:
            raise ActionEvidenceError("passive AXI transaction has non-OKAY response")
        if stage == "observed":
            raise ActionEvidenceError("AXI requires accepted/completed proof")
        return num(row["start_ps"] if stage == "accepted" else row["end_ps"])
    if capture == "protocol":
        if stage == "observed":
            if row.get("kind") != "event" or row.get("status") != "observed":
                raise ActionEvidenceError("VIP observation must be an observed event")
            return num(row["start_ps"])
        if (row.get("kind") != "transaction" or row.get("status") != "complete"
                or row.get("end_ps") is None):
            raise ActionEvidenceError("VIP transaction needs independently observed completion")
        return num(row["start_ps"] if stage == "accepted" else row["end_ps"])
    raise ActionEvidenceError("unknown passive source")


def independent_check(check, plan, sha, aid, completed):
    if (not isinstance(check, dict) or check.get("scenario_id") != plan["scenario_id"]
            or check.get("plan_sha256") != sha or check.get("action_instance_id") != aid
            or check.get("origin") != "independent_checker" or check.get("verdict") != "pass"):
        raise ActionEvidenceError("independent checker identity/verdict mismatch")
    expected, actual = check.get("expected_hex"), check.get("observed_hex")
    if (not isinstance(expected, str) or not expected or expected != actual
            or len(expected) % 2 or len(expected) > 131072):
        raise ActionEvidenceError("missing or mismatched independently checked bytes")
    try:
        bytes.fromhex(expected)
    except ValueError as exc:
        raise ActionEvidenceError("invalid independent hex data") from exc
    refs = check.get("observed_refs")
    if not isinstance(refs, list) or not refs:
        raise ActionEvidenceError("checker needs completed passive evidence references")
    tokens = []
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"capture", "ref"}:
            raise ActionEvidenceError("invalid checker provenance reference")
        token = (ref["capture"], ref["ref"])
        if token not in completed or token in tokens:
            raise ActionEvidenceError("checker provenance not independently completed")
        tokens.append(token)
    return num(check.get("time_ps"))


def summarize(raw_plan, lines, *, axi=None, protocols=None, scoreboard=None, require_all=False):
    plan, sha, actions = parse_plan(raw_plan)
    sources = passive_rows(axi, protocols)
    checks = {}
    if scoreboard is not None:
        if (scoreboard.get("kind") != "independent_action_scoreboard" or
                scoreboard.get("capture_complete") is not True or
                not isinstance(scoreboard.get("checks"), list)):
            raise ActionEvidenceError("invalid independent scoreboard artifact")
        for c in scoreboard["checks"]:
            if not isinstance(c, dict) or not isinstance(c.get("uid"), str) or c["uid"] in checks:
                raise ActionEvidenceError("duplicate/invalid checker UID")
            checks[c["uid"]] = c
    state = {aid: {"issued": None, "done": None, "driver": None,
                   "accepted": {}, "completed": {}, "observed": {}, "checked": None}
             for aid in actions}
    claims = {}
    issues = []
    prior_time = -1
    for index, raw in enumerate(lines):
        try:
            item = validate_event(json.loads(raw), plan=plan, sha=sha, actions=actions)
        except (ValueError, KeyError, TypeError) as exc:
            issues.append(f"malformed event line {index+1}: {exc}")
            continue
        aid, stage, now = item["action_instance_id"], item["stage"], item["time_ps"]
        st = state[aid]
        if item["seq"] != index or now < prior_time:
            issues.append(f"sequence/timestamp regression at {index+1}")
        prior_time = now
        if stage == "issued":
            if st["issued"] is not None:
                issues.append(f"duplicate issued action {aid}")
            for dep in actions[aid]["depends_on"]:
                if state[dep]["done"] is None:
                    issues.append(f"{aid}: dependency {dep} not driver-completed")
            st["issued"], st["driver"] = now, item["origin"]
        elif st["issued"] is None:
            issues.append(f"{aid}: {stage} before issue")
        if stage == "driver_done":
            if st["done"] is not None or item["origin"] != st["driver"]:
                issues.append(f"{aid}: duplicate/wrong-origin driver_done")
            st["done"] = now
        if stage in ("accepted", "completed", "observed"):
            capture, ref = item["evidence"]["capture"], item["evidence"]["ref"]
            key = (capture, ref)
            row = sources.get(capture, {}).get(ref)
            if row is None:
                issues.append(f"{aid}: absent passive {capture}/{ref}")
            else:
                try:
                    if observed_time(capture, stage, row) != now:
                        raise ActionEvidenceError("claimed event time differs from passive capture")
                except (ActionEvidenceError, KeyError, ValueError) as exc:
                    issues.append(f"{aid}: invalid {stage} evidence {ref}: {exc}")
            if stage == "completed" and key not in st["accepted"]:
                issues.append(f"{aid}: completion without same accepted UID")
            if stage in ("accepted", "observed"):
                if key in claims and claims[key] != aid:
                    issues.append(f"{aid}: capture {key} already claimed by {claims[key]}")
                claims[key] = aid
            if key in st[stage]:
                issues.append(f"{aid}: duplicate {stage} reference")
            st[stage][key] = now
        if stage == "checked":
            if st["checked"] is not None:
                issues.append(f"{aid}: duplicate independent checker verdict")
            if not st["completed"] or set(st["accepted"]) != set(st["completed"]):
                issues.append(f"{aid}: checked before all accepted operations completed")
            try:
                ref = item["evidence"]["ref"]
                if ref not in checks:
                    raise ActionEvidenceError("missing independent scoreboard record")
                if independent_check(checks[ref], plan, sha, aid, set(st["completed"])) != now:
                    raise ActionEvidenceError("checker timestamp differs from check artifact")
            except (ValueError, TypeError, KeyError) as exc:
                issues.append(f"{aid}: checked evidence rejected: {exc}")
            st["checked"] = now
    rows = []
    for aid, action in actions.items():
        st = state[aid]
        if set(st["accepted"]) != set(st["completed"]):
            issues.append(f"{aid}: accepted transactions not all completed")
        if st["issued"] is not None and st["done"] is None:
            issues.append(f"{aid}: issued driver unfinished")
        if require_all and st["issued"] is None:
            issues.append(f"{aid}: required action not issued")
        status = ("independently_checked" if st["checked"] is not None and
                  st["completed"] and set(st["accepted"]) == set(st["completed"]) else
                  "protocol_completed_unchecked" if st["completed"] else
                  "protocol_observed_unchecked" if st["observed"] or st["accepted"] else
                  "driver_only_unverified" if st["done"] is not None else
                  "issued_unverified" if st["issued"] is not None else "unmeasured")
        rows.append({"action_instance_id": aid, "actor": action["actor"],
                     "phase": action["phase"], "kind": action["kind"],
                     "depends_on": action["depends_on"],
                     "issued_ps": st["issued"], "driver_done_ps": st["done"],
                     "accepted_refs": [{"capture": c, "ref": r} for c, r in sorted(st["accepted"])],
                     "completed_refs": [{"capture": c, "ref": r} for c, r in sorted(st["completed"])],
                     "checked_ps": st["checked"], "status": status})
    complete = bool(rows) and all(r["status"] == "independently_checked" for r in rows)
    return {"schema_version": 2, "kind": "soc_action_instance_evidence",
            "scenario_id": plan["scenario_id"], "plan_sha256": sha,
            "status": "invalid_capture" if issues else
                      "fully_independently_checked" if complete else
                      "partially_verified_unmeasured" if lines else "unmeasured",
            "passed": complete and not issues, "issues": issues,
            "event_count": len(lines), "actions": rows,
            "summary": {"planned": len(rows), "issued": sum(r["issued_ps"] is not None for r in rows),
                        "completed": sum(bool(r["completed_refs"]) for r in rows),
                        "checked": sum(r["checked_ps"] is not None for r in rows)},
            "modeling": "never infer acceptance, completion or checking from driver events"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--axi", type=Path)
    parser.add_argument("--protocols", type=Path)
    parser.add_argument("--scoreboard", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()
    try:
        def read(path):
            return json.loads(path.read_text()) if path is not None else None
        result = summarize(args.plan.read_bytes(), args.events.read_text().splitlines(),
                           axi=read(args.axi), protocols=read(args.protocols),
                           scoreboard=read(args.scoreboard), require_all=args.require_all)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"DV-ACTIONS: {result['status']}; {len(result['issues'])} issues; "
          "independent RTL evidence required for pass")
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
