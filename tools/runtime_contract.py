"""Canonical *selected* per-run plan, dispatch envelope and source provenance.

Every configured YAML target uses this one runner boundary. The adapter
distinction is intentional: two SCN-2 targets execute source-resolved scenario
actions; other RTL tests still delegate opaque internal stimulus to existing
Python/C/SV/Xezim entry points. Recording a command is not proof that every
internal stimulus action was dispatched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from test_intent import plan as source_intent

SCHEMA = 1
PHASES = ("init", "run", "check")
SCENARIOS = {"cpu_dma_scenario", "scenario_bfm"}
NON_RUNTIME = {"xezim-compile", "verilator-lint"}


class RunContractError(ValueError):
    pass


def encoded(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(data: dict) -> str:
    return hashlib.sha256(encoded(data)).hexdigest()


def _scenario(directory: Path, mode: str | None):
    if mode not in SCENARIOS:
        return None, None
    path = directory / ("variant" if mode == "cpu_dma_scenario" else "") / "scenario-plan.json"
    if not path.is_file() or path.is_symlink():
        raise RunContractError("selected executable scenario plan absent")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise RunContractError("selected scenario plan invalid") from exc
    if (value.get("schema_version") != 1
            or value.get("kind") != "soc_scenario_intent_only"
            or not isinstance(value.get("actions"), list)
            or len(value["actions"]) == 0):
        raise RunContractError("invalid selected executable scenario definition")
    return value, hashlib.sha256(raw).hexdigest()


def selection(target: str, plan: dict, directory: Path,
              *, commands: list[tuple[str,list[str]]]) -> dict:
    if not isinstance(target, str) or not isinstance(plan, dict):
        raise RunContractError("invalid runner selection")
    mode = plan.get("firmware_mode")
    selected_scenario, scenario_sha = _scenario(directory, mode)
    intent = source_intent(target, plan, scenario=selected_scenario)
    adapter = ("non_runtime" if plan.get("mode") == "compile"
               or plan["engine"] in NON_RUNTIME else
               "scenario_dispatch_adapter" if mode in SCENARIOS else
               "legacy_entrypoint_adapter")
    if adapter == "non_runtime":
        # Don't imply lint/build have CPU INIT/RUN/CHECK stimulus.
        intent["phases"] = {p: [] for p in PHASES}
        intent["detail_status"] = "not_applicable_to_nonruntime_target"
        intent["declared_actions"] = 0
    if not isinstance(commands,list) or not all(
        isinstance(label,str) and isinstance(command,list)
        and all(isinstance(part,str) for part in command)
        for label,command in commands):
        raise RunContractError("commands must be selected argv arrays")
    source = subprocess.check_output(["git","rev-parse","HEAD"],
                                     cwd=Path(__file__).resolve().parents[1],
                                     text=True).strip()
    if len(source) != 40 or any(c not in "0123456789abcdef" for c in source):
        raise RunContractError("selected source revision unavailable")
    content = {
        "schema_version": SCHEMA,
        "target": target,
        "source_revision": source,
        "stage": plan.get("stage"),
        "engine": plan["engine"],
        "adapter": adapter,
        "adapter_scope": ("compiler_or_lint_no_stimulus" if adapter == "non_runtime"
                          else "resolved_scenario_actions" if adapter == "scenario_dispatch_adapter"
                          else "legacy_internal_stimulus_opaque"),
        "selected_firmware_mode": mode,
        "seed": plan.get("seed"),
        "command_argv": [{"label":label,"argv":command}
                         for label,command in commands],
        "scenario_plan_sha256": scenario_sha,
        "intent": intent,
        "evidence_kind": "selected_definition_not_runtime_execution",
    }
    return {**content, "plan_sha256": digest(content)}


def validate(snapshot: dict, *, target: str | None = None) -> dict:
    if not isinstance(snapshot,dict):
        raise RunContractError("run selection snapshot must be object")
    expected = snapshot.get("plan_sha256")
    payload = {key:value for key,value in snapshot.items() if key!="plan_sha256"}
    if (not isinstance(expected,str) or len(expected)!=64
            or expected!=digest(payload)):
        raise RunContractError("selected plan hash mismatch")
    if snapshot.get("schema_version")!=SCHEMA or (
            target is not None and snapshot.get("target")!=target):
        raise RunContractError("selected plan schema or target mismatch")
    if snapshot.get("evidence_kind")!="selected_definition_not_runtime_execution":
        raise RunContractError("source intent cannot assert execution evidence")
    intent = snapshot.get("intent",{})
    if (intent.get("target")!=snapshot.get("target")
            or set(intent.get("phases",{}))!=set(PHASES)):
        raise RunContractError("selected INIT/RUN/CHECK phases not source-qualified")
    adapter=snapshot.get("adapter")
    if adapter not in {"non_runtime","scenario_dispatch_adapter","legacy_entrypoint_adapter"}:
        raise RunContractError("unknown runner adapter")
    if adapter=="non_runtime" and (intent.get("detail_status") !=
            "not_applicable_to_nonruntime_target"):
        raise RunContractError("nonruntime target claims stimulus")
    if adapter=="scenario_dispatch_adapter" and (
            not snapshot.get("scenario_plan_sha256")
            or intent.get("declared_actions",0)<1):
        raise RunContractError("selected scenario contains no executable actions")
    if adapter=="legacy_entrypoint_adapter" and snapshot.get("scenario_plan_sha256"):
        raise RunContractError("legacy adapter must not claim a scenario")
    return snapshot


def save(path:Path,snapshot:dict) -> None:
    validate(snapshot)
    if path.is_symlink():
        raise RunContractError("unsafe selected plan path")
    path.write_text(json.dumps(snapshot,indent=2,sort_keys=True)+"\n")


def load(path:Path,target:str|None=None) -> dict:
    if not path.is_file() or path.is_symlink():
        raise RunContractError("selected plan missing or unsafe")
    return validate(json.loads(path.read_text()),target=target)


def dispatch_event(snapshot:dict, label:str, *, status:str,
                   duration_s:float|None=None, passed:bool|None=None,
                   reason:str|None=None) -> dict:
    validate(snapshot)
    commands={c["label"] for c in snapshot.get("command_argv",[])}
    if label not in commands or status not in ("started","completed"):
        raise RunContractError("event does not match selected command")
    if status=="started" and (passed is not None or duration_s is not None):
        raise RunContractError("started event cannot claim success")
    if status=="completed" and (type(passed) is not bool
                                 or not isinstance(duration_s,(int,float))
                                 or duration_s<0):
        raise RunContractError("completed event needs an actual checked outcome")
    return {
        "schema_version":SCHEMA, "plan_sha256":snapshot["plan_sha256"],
        "target":snapshot["target"], "label":label, "status":status,
        "duration_s":duration_s, "passed":passed,"reason":reason,
        "evidence_kind":"runner_command_status_not_internal_action_dispatch"
    }


def check_events(snapshot:dict,events:list[dict]) -> None:
    validate(snapshot)
    expected=[c["label"] for c in snapshot["command_argv"]]
    if len(events)!=len(expected)*2:
        raise RunContractError("runner command event count mismatch")
    for n,label in enumerate(expected):
        a,b=events[2*n:2*n+2]
        for v,stat in ((a,"started"),(b,"completed")):
            if (v.get("target")!=snapshot["target"]
                    or v.get("label")!=label
                    or v.get("status")!=stat
                    or v.get("plan_sha256")!=snapshot["plan_sha256"]
                    or v.get("evidence_kind")!="runner_command_status_not_internal_action_dispatch"):
                raise RunContractError("runner event disagrees with selected plan")
        if a.get("passed") is not None or type(b.get("passed")) is not bool:
            raise RunContractError("runner event status missing or invented")
