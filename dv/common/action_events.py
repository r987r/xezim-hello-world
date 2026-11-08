"""Additive DV action-instance event ABI. Does not replace test-flow v1.

Emitting a stimulus event is NEVER evidence of an AXI/TLP/GMII transaction.
Only the offline reporter can validate passive observations and checkers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")
PHASES = ("init", "run", "check")
STAGES = {
    "issued": {"python_driver", "sv_driver", "firmware_request"},
    "driver_done": {"python_driver", "sv_driver", "firmware_request"},
    "observed": {"passive_protocol"},
    "accepted": {"passive_axi", "passive_protocol"},
    "completed": {"passive_axi", "passive_protocol"},
    "checked": {"independent_checker"},
}
EVENT_KEYS = {"schema_version", "seq", "time_ps", "scenario_id", "plan_sha256",
              "action_instance_id", "actor", "phase", "kind", "stage", "origin", "evidence"}
MAX_SAFE = 2**53 - 1


class ActionEvidenceError(ValueError):
    """Reject missing or untrusted action evidence rather than fabricating PASS."""


def _ident(value, label):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ActionEvidenceError(f"{label}: invalid identifier")
    return value


def _time(value, label):
    if type(value) is not int or not 0 <= value <= MAX_SAFE:
        raise ActionEvidenceError(f"{label}: unsigned JS-safe integer required")
    return value


def parse_plan(raw):
    """Check exact resolved SCN-1 canonical bytes and action identities."""
    from dv.common.scenario import canonical_json
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ActionEvidenceError(f"invalid scenario plan: {exc}") from exc
    if not isinstance(doc, dict) or canonical_json(doc).encode("ascii") != raw:
        raise ActionEvidenceError("resolved plan must use exact canonical JSON bytes")
    if (type(doc.get("schema_version")) is not int or doc["schema_version"] != 1
            or doc.get("kind") != "soc_scenario_intent_only"
            or doc.get("execution_evidence") is not None):
        raise ActionEvidenceError("only schema-v1 intent-only plans supported")
    _ident(doc.get("scenario_id"), "scenario_id")
    actions = doc.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 100000:
        raise ActionEvidenceError("expected 1..100000 planned actions")
    by_id = {}
    for action in actions:
        if not isinstance(action, dict):
            raise ActionEvidenceError("invalid action")
        aid = _ident(action.get("action_instance_id"), "action_instance_id")
        if aid in by_id:
            raise ActionEvidenceError(f"duplicate action ID {aid}")
        _ident(action.get("actor"), "actor")
        _ident(action.get("kind"), "kind")
        if action.get("phase") not in PHASES:
            raise ActionEvidenceError(f"{aid}: unknown phase")
        deps = action.get("depends_on")
        if not isinstance(deps, list) or len(deps) != len(set(deps)) or any(
                not isinstance(d, str) for d in deps):
            raise ActionEvidenceError(f"{aid}: invalid dependencies")
        by_id[aid] = action
    for aid, action in by_id.items():
        if aid in action["depends_on"] or any(d not in by_id for d in action["depends_on"]):
            raise ActionEvidenceError(f"{aid}: unknown/self dependency")
    # No runtime adapter may dispatch a cyclic or backward-phase action graph.
    # Checking at plan selection prevents a stalled simulation from being the
    # first place an impossible dependency is discovered.
    colors = {}
    phase_index = {name: index for index, name in enumerate(PHASES)}
    for aid in by_id:
        if colors.get(aid) == 2:
            continue
        # Iterative DFS: a source-declared plan may contain tens of thousands
        # of actions, so recursive checking would overflow Python's stack.
        stack = [(aid, False)]
        while stack:
            current, exiting = stack.pop()
            if exiting:
                colors[current] = 2
                continue
            if colors.get(current) == 2:
                continue
            if colors.get(current) == 1:
                raise ActionEvidenceError(f"{current}: cyclic action dependency")
            colors[current] = 1
            stack.append((current, True))
            for parent in reversed(by_id[current]["depends_on"]):
                if phase_index[by_id[parent]["phase"]] > phase_index[by_id[current]["phase"]]:
                    raise ActionEvidenceError(f"{current}: dependency crosses phases backwards")
                if colors.get(parent) == 1:
                    raise ActionEvidenceError(f"{current}: cyclic action dependency")
                if colors.get(parent) != 2:
                    stack.append((parent, False))
    return doc, hashlib.sha256(raw).hexdigest(), by_id


def validate_event(item, *, plan, sha, actions):
    if not isinstance(item, dict) or set(item) != EVENT_KEYS:
        raise ActionEvidenceError("unexpected action event v2 fields")
    if type(item["schema_version"]) is not int or item["schema_version"] != 2:
        raise ActionEvidenceError("action-event schema version mismatch")
    _time(item["seq"], "seq")
    _time(item["time_ps"], "time_ps")
    if item["scenario_id"] != plan["scenario_id"] or item["plan_sha256"] != sha:
        raise ActionEvidenceError("scenario ID/plan SHA mismatch")
    aid = _ident(item["action_instance_id"], "action_instance_id")
    action = actions.get(aid)
    if action is None:
        raise ActionEvidenceError(f"unknown action {aid}")
    if (item["actor"] != action["actor"] or item["phase"] != action["phase"]
            or item["kind"] != action["kind"]):
        raise ActionEvidenceError(f"{aid}: actor/phase/kind disagrees with plan")
    stage = item["stage"]
    if stage not in STAGES or item["origin"] not in STAGES[stage]:
        raise ActionEvidenceError(f"{aid}: invalid evidence provenance")
    evidence = item["evidence"]
    if not isinstance(evidence, dict):
        raise ActionEvidenceError("evidence must be an object")
    if stage in ("issued", "driver_done"):
        if evidence:
            raise ActionEvidenceError("driver stages cannot claim hardware evidence")
    else:
        if set(evidence) != {"capture", "ref"}:
            raise ActionEvidenceError("passive/checker evidence needs capture/ref")
        if evidence["capture"] not in ("axi", "protocol", "scoreboard"):
            raise ActionEvidenceError("unknown hardware evidence capture")
        if stage == "checked" and evidence["capture"] != "scoreboard":
            raise ActionEvidenceError("independent checker needs scoreboard record")
        if stage != "checked" and evidence["capture"] == "scoreboard":
            raise ActionEvidenceError("scoreboard cannot replace protocol evidence")
        ref = evidence["ref"]
        if not isinstance(ref, str) or not 1 <= len(ref) <= 200 or any(
                ord(c) < 33 or ord(c) > 126 for c in ref):
            raise ActionEvidenceError("invalid monitor evidence reference")
    return item


class ActionEventRecorder:
    """Line-flushed driver/event instrumentation; offline reporter proves refs."""

    def __init__(self, plan_bytes, output, clock_ps, *, max_events=200000):
        self.plan, self.sha, self.actions = parse_plan(plan_bytes)
        self.path = Path(output)
        self.clock_ps = clock_ps
        self.max_events = _time(max_events, "max_events")
        if max_events == 0 or self.path.is_symlink():
            raise ActionEvidenceError("invalid event bound or symlink destination")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", encoding="utf-8", buffering=1)
        self.seq = 0
        self.last = -1
        self.closed = False
        self.states = {}
        self.refs = {}

    def emit(self, action_instance_id, stage, origin, *, evidence=None):
        if self.closed or self.seq >= self.max_events:
            raise ActionEvidenceError("event recorder closed or overflowed")
        action = self.actions.get(action_instance_id)
        if action is None:
            raise ActionEvidenceError("unknown action instance")
        now = _time(self.clock_ps(), "time_ps")
        if now < self.last:
            raise ActionEvidenceError("timestamp rollback")
        item = validate_event({
            "schema_version": 2, "seq": self.seq, "time_ps": now,
            "scenario_id": self.plan["scenario_id"], "plan_sha256": self.sha,
            "action_instance_id": action_instance_id, "actor": action["actor"],
            "phase": action["phase"], "kind": action["kind"],
            "stage": stage, "origin": origin, "evidence": evidence or {},
        }, plan=self.plan, sha=self.sha, actions=self.actions)
        phases = self.states.setdefault(action_instance_id, {})
        if "checked" in phases:
            raise ActionEvidenceError("action already independently checked")
        if stage == "issued":
            for parent in action["depends_on"]:
                parent_stages = self.states.get(parent, {})
                if "driver_done" not in parent_stages:
                    raise ActionEvidenceError(
                        f"{action_instance_id}: dependency {parent} not driver-completed")
        if stage in ("issued", "driver_done", "checked") and stage in phases:
            raise ActionEvidenceError("duplicate action stage")
        if stage != "issued" and "issued" not in phases:
            raise ActionEvidenceError("action not yet issued")
        if stage == "driver_done" and origin != phases["issued"][1]:
            raise ActionEvidenceError("driver origin changed")
        if stage in ("observed", "accepted", "completed"):
            ref = (item["evidence"]["capture"], item["evidence"]["ref"])
            used = self.refs.setdefault((action_instance_id, stage), set())
            if ref in used:
                raise ActionEvidenceError("duplicate passive evidence reference")
            if stage == "completed" and ref not in self.refs.get((action_instance_id, "accepted"), set()):
                raise ActionEvidenceError("completion lacks matching acceptance reference")
            used.add(ref)
        if stage == "checked" and (not self.refs.get((action_instance_id, "completed"))
                or self.refs.get((action_instance_id, "completed")) !=
                   self.refs.get((action_instance_id, "accepted"))):
            raise ActionEvidenceError("not all accepted operations completed")
        phases[stage] = (now, origin)
        self.seq += 1
        self.last = now
        self.file.write(json.dumps(item, separators=(",", ":"), sort_keys=True) + "\n")
        return item

    def close(self):
        if self.closed:
            raise ActionEvidenceError("action recorder double close")
        self.closed = True
        self.file.close()
        incomplete = [aid for aid, st in self.states.items()
                      if "issued" in st and "driver_done" not in st]
        if incomplete:
            raise ActionEvidenceError(f"unfinished issued drivers: {incomplete[:8]}")
