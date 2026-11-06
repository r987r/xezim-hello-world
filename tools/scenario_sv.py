#!/usr/bin/env python3
"""SCN-3: deterministic SystemVerilog *driver* adapter for scenario-plan.json.

This is NOT an SV-UVM scheduler, AXI monitor, or independent RTL scoreboard.
Generated SV can read a single immutable action contract and emit correlated
driver ISSUE/DONE logs. A driver log is never proof of accepted RTL traffic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dv.common.scenario import canonical_json, KINDS, NAME, PHASES

TRACE_PREFIX = "SOC_SCN_SV_V1|"
EVENT_RE = re.compile(
    r"^SOC_SCN_SV_V1\|([A-Za-z][A-Za-z0-9_.-]{0,95})"
    r"\|([0-9a-f]{64})\|([A-Za-z][A-Za-z0-9_.-]{0,95})"
    r"\|(init|run|check)\|(issued|driver_done)\|([0-9]+)$"
)
MAX_ACTIONS = 4096


class SVContractError(ValueError):
    """Invalid plan or untrustworthy SystemVerilog driver event stream."""


def _valid_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise SVContractError(f"{label}: unsupported identifier {value!r}")
    return value


def _text(value: str) -> str:
    if not isinstance(value, str) or not all(32 <= ord(c) <= 126 for c in value):
        raise SVContractError("SV contract arguments must be printable ASCII")
    return json.dumps(value, ensure_ascii=True)


def load_plan(raw: bytes) -> tuple[dict, str]:
    try:
        plan = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise SVContractError(f"invalid UTF-8 scenario plan: {exc}") from exc
    if not isinstance(plan, dict) or canonical_json(plan).encode("ascii") != raw:
        raise SVContractError("resolved scenario must use exact canonical JSON bytes")
    if (type(plan.get("schema_version")) is not int or plan["schema_version"] != 1 or
            plan.get("kind") != "soc_scenario_intent_only" or
            plan.get("execution_evidence") is not None):
        raise SVContractError("SV compiler requires schema v1 intent-only plan")
    _valid_name(plan.get("scenario_id"), "scenario_id")
    actors = plan.get("actors")
    if not isinstance(actors, list) or len(actors) != len(set(actors)):
        raise SVContractError("invalid unique scenario actor list")
    for actor in actors:
        _valid_name(actor, "actor")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        raise SVContractError(f"expected 1..{MAX_ACTIONS} actions")
    ids: set[str] = set()
    expected: set[str] = set()
    for a in actions:
        if not isinstance(a, dict):
            raise SVContractError("invalid action object")
        aid = _valid_name(a.get("action_instance_id"), "action_instance_id")
        _valid_name(a.get("expected_result_id"), "expected_result_id")
        if aid in ids or a["expected_result_id"] in expected:
            raise SVContractError("duplicate action or expected-result identifier")
        ids.add(aid)
        expected.add(a["expected_result_id"])
        if a.get("phase") not in PHASES or a.get("kind") not in KINDS or a.get("actor") not in actors:
            raise SVContractError(f"{aid}: unsupported phase, kind or undeclared actor")
        if not isinstance(a.get("args"), dict):
            raise SVContractError(f"{aid}: missing resolved action arguments")
        for field in ("depends_on",):
            if not isinstance(a.get(field), list) or any(not isinstance(x, str) for x in a[field]):
                raise SVContractError(f"{aid}: dependency array absent")
        parent = a.get("parent_action_id")
        if parent is not None:
            _valid_name(parent, "parent_action_id")
    for a in actions:
        aid = a["action_instance_id"]
        if aid in a["depends_on"] or any(d not in ids for d in a["depends_on"]):
            raise SVContractError(f"{aid}: self or unknown dependency")
    return plan, hashlib.sha256(raw).hexdigest()


def _flatten(obj: dict, *, prefix: str = "") -> list[tuple[str, str, Any]]:
    fields: list[tuple[str, str, Any]] = []
    for key in sorted(obj):
        if not isinstance(key, str):
            raise SVContractError("argument keys must be strings")
        _text(key)
        name = f"{prefix}.{key}" if prefix else key
        value = obj[key]
        if isinstance(value, dict):
            fields.extend(_flatten(value, prefix=name))
        elif type(value) is str:
            fields.append((name, "text", value))
        elif type(value) is bool:
            fields.append((name, "uint", int(value)))
        elif type(value) is int and 0 <= value < (1 << 64):
            fields.append((name, "uint", value))
        else:
            raise SVContractError(f"{name}: unsupported SV argument type")
    return fields


def render_package(raw_plan: bytes) -> str:
    plan, sha = load_plan(raw_plan)
    actions = plan["actions"]
    output = [
        "// GENERATED from canonical scenario-plan.json. Do not edit.",
        "// Driver logs are NOT independent AXI/PCIe/GMII hardware evidence.",
        "package soc_scenario_contract_pkg;",
        "  localparam int SCN_CONTRACT_VERSION = 1;",
        f"  localparam int SCN_ACTION_COUNT = {len(actions)};",
        f"  localparam string SCN_SCENARIO_ID = {_text(plan['scenario_id'])};",
        f"  localparam string SCN_PLAN_SHA256 = {_text(sha)};",
        "",
    ]
    for name, key in (("scn_action_id", "action_instance_id"),
                      ("scn_action_phase", "phase"),
                      ("scn_action_actor", "actor"),
                      ("scn_action_kind", "kind"),
                      ("scn_expected_id", "expected_result_id")):
        output.extend([
            f"  function automatic string {name}(input int index);",
            "    case (index)",
            *[f"      {i}: return {_text(a[key])};" for i, a in enumerate(actions)],
            '      default: begin $fatal(1, "SV scenario action index outside plan"); return ""; end',
            "    endcase",
            "  endfunction",
            "",
        ])
    for name, scalar_type, return_type in (
        ("scn_text_arg", "text", "string"),
        ("scn_uint_arg", "uint", "longint unsigned"),
    ):
        output.extend([
            f"  function automatic {return_type} {name}(input int index, input string key);",
        ])
        for i, a in enumerate(actions):
            for field, kind, value in _flatten(a["args"]):
                if kind == scalar_type:
                    literal = _text(value) if kind == "text" else f"64'h{value:016x}"
                    output.append(f"    if ((index == {i}) && (key == {_text(field)})) return {literal};")
        output.extend([
            '    $fatal(1, "SV scenario field missing or has incompatible type: action=%0d key=%s", index, key);',
            '    return "";' if scalar_type == "text" else "    return 64\'d0;",
            "  endfunction",
            "",
        ])
    output.extend([
        "  // Driver-only event; NOT a verified transaction or a phase-engine gate.",
        "  task automatic scn_emit_driver(input int index, input string stage,",
        "                                input longint unsigned sim_ticks);",
        "    if ((index < 0) || (index >= SCN_ACTION_COUNT))",
        '      $fatal(1, "SV scenario driver action outside plan");',
        '    if ((stage != "issued") && (stage != "driver_done"))',
        '      $fatal(1, "SV scenario driver stage is not issued/driver_done");',
        '    $display("SOC_SCN_SV_V1|%s|%s|%s|%s|%s|%0d",',
        "             SCN_SCENARIO_ID, SCN_PLAN_SHA256,",
        "             scn_action_id(index), scn_action_phase(index), stage, sim_ticks);",
        "  endtask",
        "endpackage",
        "",
    ])
    return "\n".join(output)


def audit_sv_transcript(raw_plan: bytes, transcript: str) -> dict:
    plan, sha = load_plan(raw_plan)
    indexed = {a["action_instance_id"]: a for a in plan["actions"]}
    recorded: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(transcript.splitlines(), 1):
        if not line.startswith(TRACE_PREFIX):
            continue
        match = EVENT_RE.fullmatch(line)
        if match is None:
            raise SVContractError(f"line {line_number}: malformed SCN-SV event")
        scenario, recorded_sha, aid, phase, stage, tick_string = match.groups()
        if scenario != plan["scenario_id"] or recorded_sha != sha:
            raise SVContractError(f"line {line_number}: wrong scenario/plan SHA")
        action = indexed.get(aid)
        if action is None or action["phase"] != phase:
            raise SVContractError(f"line {line_number}: unknown action or phase mismatch")
        tick = int(tick_string)
        previous = recorded.get(aid)
        if stage == "issued":
            if previous is not None:
                raise SVContractError(f"line {line_number}: duplicate issue for {aid}")
            recorded[aid] = {"issued_tick": tick}
        else:
            if previous is None or "driver_done_tick" in previous or tick < previous["issued_tick"]:
                raise SVContractError(f"line {line_number}: orphan/duplicate/out-of-order DONE for {aid}")
            previous["driver_done_tick"] = tick
        events.append({"scenario_id": scenario, "plan_sha256": sha,
                       "action_instance_id": aid, "phase": phase,
                       "actor": action["actor"], "kind": action["kind"],
                       "event": stage, "sim_ticks": tick,
                       "provenance": "sv_driver_reported_only",
                       "rtl_observed": False})
    return {
        "schema_version": 1, "kind": "soc_scenario_sv_driver_events",
        "scenario_id": plan["scenario_id"], "plan_sha256": sha,
        "status": "driver_log_unverified", "rtl_evidence": None,
        "event_count": len(events), "action_instances_seen": len(recorded),
        "events": events,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    generate = sub.add_parser("generate", help="generate standalone SV package from scenario intent")
    generate.add_argument("--plan", type=Path, required=True)
    generate.add_argument("--out", type=Path, required=True)
    audit = sub.add_parser("audit", help="parse SV driver-only log (not RTL evidence)")
    audit.add_argument("--plan", type=Path, required=True)
    audit.add_argument("--log", type=Path, required=True)
    audit.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = args.plan.read_bytes()
        result = (render_package(raw) if args.cmd == "generate"
                  else canonical_json(audit_sv_transcript(raw, args.log.read_text(encoding="utf-8"))))
    except (OSError, UnicodeError, SVContractError, ValueError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(result, encoding="ascii")
    print(f"SCN-SV {args.cmd}: {args.out} (driver-only, not hardware proof)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
