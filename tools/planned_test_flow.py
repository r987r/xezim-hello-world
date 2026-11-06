"""Plan-only INIT/RUN/CHECK view for every declared regression target.

Expected phase milestones and canonical scenario actions are *intent*, not
simulator evidence. Do not infer unseen testbench operations from source names.
"""
from __future__ import annotations

from html import escape
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHASES = ("init", "run", "check")
TARGET = re.compile(r"^[a-z][a-z0-9-]*$")
STEP = re.compile(r"^[a-z][a-z0-9_.-]*\.[a-z][a-z0-9_.-]*$")
MAX_ACTIONS = 4096
MAX_TEXT = 4096


class PlannedFlowError(ValueError):
    """Unsafe or contradictory declared test plan."""


def _scenario_source(root: Path, text: str) -> Path:
    if not isinstance(text, str) or not text or "\\" in text:
        raise PlannedFlowError("flow_plan must be a checked-in scenario JSON path")
    path = PurePosixPath(text)
    if (path.is_absolute() or ".." in path.parts or
            path.parts[:2] != ("config", "scenarios") or
            path.suffix != ".json" or len(path.parts) != 3):
        raise PlannedFlowError("flow_plan must be config/scenarios/<name>.json")
    resolved = (root / text).resolve()
    if not resolved.is_relative_to((root / "config" / "scenarios").resolve()):
        raise PlannedFlowError("flow_plan leaves the canonical scenario directory")
    if not resolved.is_file():
        raise PlannedFlowError("missing declared scenario file")
    return resolved


def compile_flow(target: str, test: dict, *, root: Path = ROOT,
                 include_actions: bool = True, source: str = "current_config") -> dict:
    """Compile a view from checked-in YAML, not a fabricated simulation trace.

    include_actions=False is for older CI artifacts without an actual
    planned-flow snapshot: keep archived required_steps but never mix them
    with possibly newer checked-in scenario definitions.
    """
    if not isinstance(target, str) or not TARGET.fullmatch(target):
        raise PlannedFlowError("invalid regression target")
    if not isinstance(test, dict) or not isinstance(test.get("engine"), str):
        raise PlannedFlowError("missing test runner/engine declaration")
    if source not in ("current_config", "run_snapshot", "archived_runner_plan"):
        raise PlannedFlowError("invalid flow source provenance")
    report = test.get("report") or {}
    if not isinstance(report, dict):
        raise PlannedFlowError("invalid report definition")
    flow = report.get("flow") or {}
    if not isinstance(flow, dict):
        raise PlannedFlowError("invalid phase flow declaration")
    declared = flow.get("required_steps")
    if declared is not None and (
            not isinstance(declared, dict) or set(declared) != set(PHASES)):
        raise PlannedFlowError("phase milestones must include INIT, RUN and CHECK")
    origins = flow.get("required_origins", {})
    if not isinstance(origins, dict):
        raise PlannedFlowError("invalid milestone origin map")
    result = {"schema_version": 1, "target": target, "intent_only": True,
              "source": source, "engine": test["engine"],
              "top": str(test.get("top", ""))[:MAX_TEXT],
              "module": str(test.get("module", ""))[:MAX_TEXT],
              "context": str(report.get("context", ""))[:MAX_TEXT],
              "scenario": None, "phase_detail": "runner_outline",
              "acceptance": {"pass_marker": str(test.get("pass", ""))[:MAX_TEXT],
                             "expected_failure": str(test.get("expect_failure", ""))[:MAX_TEXT]},
              "phases": {}}
    for phase in PHASES:
        listed = (declared or {}).get(phase, [])
        if (not isinstance(listed, list) or len(listed) > MAX_ACTIONS or
                len(set(listed)) != len(listed) or
                any(not isinstance(s, str) or not STEP.fullmatch(s) for s in listed)):
            raise PlannedFlowError(f"{phase}: invalid or duplicate expected milestones")
        listed_origins = origins.get(phase, {})
        if not isinstance(listed_origins, dict):
            raise PlannedFlowError(f"{phase}: invalid required origins")
        if any(k not in listed for k in listed_origins):
            raise PlannedFlowError(f"{phase}: origin references undeclared milestone")
        steps = [{"id": step, "actor": step.split(".", 1)[0],
                  "expected_origin": listed_origins.get(step),
                  "source": "required_step_contract"}
                 for step in listed]
        result["phases"][phase] = {"milestones": steps, "actions": [],
                                   "detail_declared": bool(steps),
                                   "runner_outline": None}
    if declared is not None:
        result["phase_detail"] = "expected_milestones_only"
    name = test.get("flow_plan")
    if name is not None:
        _scenario_source(root, name)  # validates path, even for old runs
    if name and include_actions:
        from dv.common.scenario import canonical_json, resolve_scenario
        spec = json.loads(_scenario_source(root, name).read_text(encoding="utf-8"))
        soc = yaml.safe_load((root / "config/soc.yaml").read_text(encoding="utf-8"))
        plan = resolve_scenario(spec, soc)
        raw = canonical_json(plan).encode("ascii")
        actions = plan.get("actions", [])
        if not 1 <= len(actions) <= MAX_ACTIONS:
            raise PlannedFlowError("unbounded or empty scenario actions")
        result["scenario"] = {"scenario_id": plan["scenario_id"],
                              "seed": plan["seed"],
                              "source_file": name,
                              "resolved_sha256": hashlib.sha256(raw).hexdigest(),
                              "modeling": "resolved_intent_not_execution"}
        for action in actions:
            phase = action["phase"]
            if phase not in PHASES:
                raise PlannedFlowError("scenario references an unknown phase")
            result["phases"][phase]["actions"].append({
                "id": action["action_instance_id"], "actor": action["actor"],
                "kind": action["kind"], "depends_on": action.get("depends_on", []),
                "args": action.get("args", {}),
                "expected_result_id": action.get("expected_result_id"),
                "allocation": action.get("allocation"),
                "source": "resolved_scenario_intent"})
            result["phases"][phase]["detail_declared"] = True
        result["phase_detail"] = "scenario_actions_and_milestones"
    for phase, row in result["phases"].items():
        if row["detail_declared"]:
            continue
        # Explicitly a runner outline, NOT a claim that the testbench uses
        # this exact sequence. The actual internal stimulus was not declared.
        detail = {
            "init": "Runner prepares the configured files, top and test environment; internal test INIT is not declared",
            "run": "Runner invokes the configured testbench/module; detailed stimulus actions are not declared",
            "check": "Runner checks the configured pass marker or required negative outcome; internal CHECK is not declared",
        }[phase]
        row["runner_outline"] = detail
    return result


def validate_snapshot(plan: dict, target: str, archived_test: dict) -> dict:
    """Accept only bounded intent snapshots, never HTML/code from CI."""
    if (not isinstance(plan, dict) or plan.get("schema_version") != 1 or
            plan.get("target") != target or plan.get("intent_only") is not True or
            plan.get("engine") != archived_test.get("engine") or
            plan.get("source") not in ("run_snapshot", "current_config") or
            not isinstance(plan.get("phases"), dict) or
            set(plan["phases"]) != set(PHASES)):
        raise PlannedFlowError("invalid or mismatched archived planned-flow snapshot")
    if len(json.dumps(plan)) > 500000:
        raise PlannedFlowError("unbounded archived planned-flow payload")
    expected = compile_flow(target, archived_test, include_actions=False,
                            source="archived_runner_plan")
    for phase in PHASES:
        row = plan["phases"][phase]
        if (not isinstance(row, dict) or not isinstance(row.get("actions"), list)
                or len(row["actions"]) > MAX_ACTIONS or
                not isinstance(row.get("milestones"), list) or
                row["milestones"] != expected["phases"][phase]["milestones"]):
            raise PlannedFlowError("planned-flow snapshot disagrees with archived required milestones")
        for action in row["actions"]:
            if (not isinstance(action, dict) or not isinstance(action.get("id"), str)
                    or not isinstance(action.get("actor"), str)
                    or action.get("source") != "resolved_scenario_intent"):
                raise PlannedFlowError("invalid archived scenario action")
    if plan.get("acceptance") != expected["acceptance"]:
        raise PlannedFlowError("planned-flow snapshot disagrees with archived acceptance rule")
    return plan


def render_fragment(plan: dict) -> str:
    """Safe static plan section for the existing per-run report.html."""
    def clean(value):
        return escape(str(value), quote=True)
    out = ['<section id="planned-test-flow" class="card">',
           '<h2>Planned INIT → RUN → CHECK and stimulus</h2>',
           '<p><strong>Declared intent, not RTL evidence.</strong> '
           'Actual observed phase/transaction details remain in their separate report links.</p>',
           '<p>Flow source: '+clean(plan["source"])+' · Detail: '+clean(plan["phase_detail"])+'</p>']
    if plan.get("context"):
        out.append('<p>'+clean(plan["context"])+'</p>')
    scenario = plan.get("scenario")
    if scenario:
        out.append('<p>Scenario: '+clean(scenario["scenario_id"])+' · seed '
                   +clean(scenario["seed"])+'</p>')
    for phase in PHASES:
        stage = plan["phases"][phase]
        out.append('<details open><summary><strong>'+phase.upper()+'</strong> · '
                   +str(len(stage["milestones"]))+' declared milestones / '
                   +str(len(stage["actions"]))+' scenario actions</summary><ul>')
        for step in stage["milestones"]:
            out.append('<li>Milestone <code>'+clean(step["id"])+'</code>'
                       +' · actor '+clean(step["actor"])+'</li>')
        for action in stage["actions"]:
            out.append('<li>Action <code>'+clean(action["id"])+'</code> · '
                       +clean(action["actor"])+' · '+clean(action["kind"])
                       +' · deps '+clean(", ".join(action["depends_on"]) or "none")
                       +'<pre>'+clean(json.dumps(action["args"], sort_keys=True))+'</pre></li>')
        if stage["runner_outline"]:
            out.append('<li>'+clean(stage["runner_outline"])+'</li>')
        out.append('</ul></details>')
    out.append('</section>')
    return "".join(out)
