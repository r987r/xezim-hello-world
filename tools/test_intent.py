"""Source-defined test intent, independent of simulation evidence or PASS/FAIL.

For every configured regression expose known INIT/RUN/CHECK milestones and
scenario actions. Never infer unlisted stimulus from a module name or log.
"""
from __future__ import annotations

from html import escape
import hashlib
import json
from pathlib import Path
import re

PHASES=("init","run","check")


def plan(name: str, test: dict, *, scenario: dict | None = None,
         stimulus: dict | None = None) -> dict:
    if not isinstance(test, dict):
        raise ValueError("invalid regression test")
    flow=(test.get("report") or {}).get("flow") or {}
    required=flow.get("required_steps") or {}
    if required and (not isinstance(required,dict) or set(required)!=set(PHASES)):
        raise ValueError(f"{name}: invalid required flow phases")
    phases={p:[] for p in PHASES}
    if scenario is not None:
        if scenario.get("schema_version")!=1 or not isinstance(scenario.get("actions"),list):
            raise ValueError(f"{name}: invalid scenario definition")
        identifiers=set()
        for action in scenario["actions"]:
            phase=action.get("phase")
            aid=action.get("action_instance_id")
            if phase not in phases or not isinstance(aid,str) or aid in identifiers:
                raise ValueError(f"{name}: invalid scenario action")
            identifiers.add(aid)
            phases[phase].append({
                "label":aid, "actor":action.get("actor"), "kind":action.get("kind"),
                "depends_on":action.get("depends_on") or [],
                "args":action.get("args") or {}, "source":"scenario_definition",
                "expectation":action.get("expected_result_id"),
            })
    for phase in PHASES:
        items=required.get(phase, [])
        if not isinstance(items,list):
            raise ValueError(f"{name}: invalid {phase} milestones")
        for item in items:
            if not isinstance(item,str) or "." not in item:
                raise ValueError(f"{name}: invalid {phase} milestone")
            actor,step=item.split(".",1)
            phases[phase].append({
                "label":step,"actor":actor,"kind":"required_milestone",
                "depends_on":[],"args":{},"source":"regression_flow_contract",
                "expectation":None,
            })
    known=sum(len(v) for v in phases.values())
    engine=test.get("engine")
    is_compile=test.get("mode")=="compile" or engine in ("verilator-lint","xezim-compile")
    execution_status=(
        "not_applicable_compile_or_lint" if is_compile else
        "canonical_resolved_scenario" if scenario is not None else
        "source_selected_benchmark" if (test.get("report") or {}).get("fabric_benchmark") else
        "instrumented_legacy_flow" if required else
        "legacy_runtime_without_action_contract"
    )
    result = {
        "schema_version":1,"target":name,"engine":test.get("engine"),
        "top":test.get("top"),"module":test.get("module"),
        "seed":test.get("seed"),"variant":test.get("firmware_mode"),
        "selected_args":list(test.get("args") or []),
        "context":(test.get("report") or {}).get("context"),
        "acceptance":test.get("expect_failure") or test.get("pass"),
        "acceptance_kind":"expected_failure" if test.get("expect_failure") else "success_or_compile",
        "scenario_id":scenario.get("scenario_id") if scenario else None,
        "scenario_source":test.get("flow_plan") if scenario else None,
        "phases":phases,
        "declared_actions":known,
        "detail_status":"declared_steps" if known else "no_detailed_phase_steps_declared",
        "execution_adoption":execution_status,
        "runtime_phases_applicable":not is_compile,
        "provenance":"configured_test_definition_not_execution",
        "evidence_required_for_display":False,
    }
    return attach_stimulus(result, stimulus)


def attach_stimulus(intent: dict, stimulus: dict | None) -> dict:
    """Keep reviewable YAML separate from executable/observed action claims."""
    if stimulus is None:
        return intent
    if stimulus["execution"] == "scenario_native" and (
            intent.get("scenario_source") != stimulus.get("scenario_source")):
        raise ValueError("authored stimulus disagrees with selected executable source")
    intent.update({
        "stimulus_source":stimulus["source"],
        "stimulus_sha256":stimulus["sha256"],
        "stimulus_logical_test":stimulus["logical_test"],
        "stimulus_purpose":stimulus["purpose"],
        "stimulus_execution":stimulus["execution"],
        "stimulus_driver_source":stimulus["driver_source"],
        "stimulus_rtl_top":stimulus["rtl_top"],
        "stimulus_bender_source_target":stimulus["bender_source_target"],
        "stimulus_outline":stimulus["phases"],
        "stimulus_outline_is_not_dispatch_evidence":True,
    })
    return intent


def snapshot(name: str, test: dict, *, scenario: dict | None = None,
             stimulus: dict | None = None) -> dict:
    """Immutable declaration snapshot, not evidence that any action ran.

    Hash the exact source-defined flow independently of wall clock, log text,
    simulator result and publisher revision. Old runs must retain their own
    archived snapshot rather than borrowing a newer mainline scenario.
    """
    intent = plan(name, test, scenario=scenario, stimulus=stimulus)
    canonical = json.dumps(intent, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return {
        "schema_version": 1,
        "kind": "source_declared_plan_not_execution",
        "intent": intent,
        "plan_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def validate_snapshot(data: dict, *, target: str | None = None) -> dict:
    """Reject missing, tampered or mislabeled archived plan snapshots."""
    if not isinstance(data, dict) or set(data) != {
            "schema_version", "kind", "intent", "plan_sha256"}:
        raise ValueError("invalid declared-plan snapshot envelope")
    if data["schema_version"] != 1 or data["kind"] != "source_declared_plan_not_execution":
        raise ValueError("unsupported declared-plan snapshot schema")
    intent = data["intent"]
    if (not isinstance(intent, dict) or
            (target is not None and intent.get("target") != target) or
            set(intent.get("phases", {})) != set(PHASES) or
            intent.get("provenance") != "configured_test_definition_not_execution"):
        raise ValueError("declared-plan snapshot provenance/target mismatch")
    canonical = json.dumps(intent, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    digest = hashlib.sha256(canonical).hexdigest()
    if digest != data["plan_sha256"]:
        raise ValueError("declared-plan snapshot digest mismatch")
    return intent


def catalog(config: dict, *, scenario: dict | None = None) -> dict:
    """Load each explicitly registered scenario; never infer by test name.

    The optional scenario parameter preserves callers that already loaded
    this same source, but the regression's flow_plan path remains authoritative.
    Only checked-in config/scenarios/<basename>.json may supply executable
    source-defined action definitions.
    """
    tests=config.get("tests")
    if not isinstance(tests,dict) or not tests:
        raise ValueError("no configured regression tests")
    root=Path(__file__).resolve().parents[1]
    result={}
    for name,test in tests.items():
        path=test.get("flow_plan")
        selected=None
        if path is not None:
            if not isinstance(path,str) or not re.fullmatch(
                    r"config/scenarios/[a-zA-Z0-9_-]+\.json",path):
                raise ValueError(f"{name}: unsafe scenario declaration")
            selected=json.loads((root/path).read_text())
            if scenario is not None and scenario != selected:
                raise ValueError(f"{name}: declared scenario differs from caller source")
        result[name]=plan(name,test,scenario=selected)
    # Do not coerce new human-authored descriptions into executable actions.
    # Ensure every selected build target has a readable, reviewable source,
    # even before any CI job has produced a result.
    try:
        from .stimulus_catalog import load as load_stimuli
    except ImportError:
        from stimulus_catalog import load as load_stimuli
    definitions = load_stimuli(config)
    for name in result:
        attach_stimulus(result[name], definitions[name])
    return result


def render(flow: dict) -> str:
    """Trusted static HTML for original per-test reports, no unescaped input."""
    def e(value):
        return escape(str(value),quote=True)
    out=['<section id="test-intended-flow" aria-label="Intended INIT RUN CHECK flow">',
         '<h2>Test execution flow · intended</h2>',
         '<p>Source-defined steps, not claims that hardware executed or passed. ',
         'Evidence links are optional debugging tools.</p>']
    if flow.get("context"):
        out.append('<p>'+e(flow["context"])+'</p>')
    if flow.get("stimulus_source"):
        out.append('<h3>Reviewable stimulus specification</h3>')
        out.append('<p><code>'+e(flow["stimulus_source"])+'</code>'
                   +' · spec SHA-256 <code>'+e(flow["stimulus_sha256"])+'</code>'
                   +' · '+e(flow.get("stimulus_execution"))+'</p>')
        out.append('<p>'+e(flow.get("stimulus_purpose"))+'</p>')
        if flow.get("stimulus_driver_source"):
            out.append('<p>Driver source: <code>'+
                       e(flow["stimulus_driver_source"])+'</code></p>')
        else:
            out.append('<p>SV/compile entrypoint: <code>'+
                       e(flow.get("stimulus_rtl_top") or "build target")+
                       '</code> · Bender target <code>'+
                       e(flow.get("stimulus_bender_source_target"))+'</code></p>')
        out.append('<p><small>INIT/RUN/CHECK outline below is authored intent, '
                   'not proof of internal action dispatch or observed hardware.</small></p>')
        for label in PHASES:
            out.append('<details><summary>Authored '+label.upper()+' intent</summary><ol>')
            for line in flow["stimulus_outline"][label]:
                out.append('<li>'+e(line)+'</li>')
            out.append('</ol></details>')
    out.append('<p><strong>Execution adoption:</strong> '+
               e(flow.get("execution_adoption","legacy_snapshot_missing_mode"))+'</p>')
    if flow.get("runtime_phases_applicable") is False:
        out.append('<p>Compile/lint-only target: INIT/RUN/CHECK stimulus phases '
                   'are not applicable; no runtime actions are claimed.</p>')
    for phase in PHASES:
        out.append('<details open><summary><strong>'+phase.upper()+'</strong></summary>')
        actions=flow["phases"][phase]
        if not actions:
            out.append('<p>Detailed '+phase.upper()+' steps are not declared for this test.</p>')
        else:
            out.append('<ol>')
            for action in actions:
                label=(str(action.get("actor") or "")+"."+str(action["label"])).strip(".")
                out.append('<li><strong>'+e(label)+'</strong> <small>('+e(action["source"])+')</small>')
                if action.get("kind") and action["kind"]!="required_milestone":
                    out.append(' · '+e(action["kind"]))
                if action.get("depends_on"):
                    out.append(' · after '+e(", ".join(action["depends_on"])))
                if action.get("args"):
                    out.append('<details><summary>Configured inputs</summary><pre>'+
                               e(json.dumps(action["args"],sort_keys=True,default=str))+
                               '</pre></details>')
                out.append('</li>')
            out.append('</ol>')
        out.append('</details>')
    out.append('<p><strong>Runner acceptance contract:</strong> '+e(flow.get("acceptance") or "No explicit PASS token configured")+'</p>')
    out.append('<p><small>Entry point: '+e(flow.get("module") or flow.get("top") or "generated check")+
               ' · flow provenance: configured test definition, not simulation evidence.</small></p></section>')
    return "".join(out)
