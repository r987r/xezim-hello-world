#!/usr/bin/env python3
"""C firmware *metadata* adapter from the same immutable SCN-1 JSON as SV/Python.

No second planner or test phase engine: this generates a C11 header exposing
resolved action IDs, parameters, dependencies and plan SHA. Actual hardware
drivers, protocol acceptance and independent checker evidence are separate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.scenario_sv import load_plan, _flatten
from dv.common.action_events import parse_plan


def quoted(value: str) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) > 126
                                         for c in value):
        raise ValueError("C contract string must be printable ASCII")
    return json.dumps(value, ensure_ascii=True)


def render_header(raw: bytes) -> str:
    """Fail closed if C, SV and Python would select different source bytes."""
    plan, sha = load_plan(raw)
    selected, checked_sha, by_id = parse_plan(raw)
    if checked_sha != sha or selected != plan:
        raise ValueError("C and source scenario parsers disagree on canonical plan")
    actions = plan["actions"]
    if not 1 <= len(actions) <= 4096:
        raise ValueError("C firmware contract supports 1..4096 actions")
    dependencies = []
    arguments = []
    records = []
    for action in actions:
        dep_first = len(dependencies)
        dependencies.extend(action["depends_on"])
        arg_first = len(arguments)
        arguments.extend(_flatten(action["args"]))
        records.append((action, dep_first, len(action["depends_on"]),
                        arg_first, len(arguments) - arg_first))
    lines = [
        "/* GENERATED FROM CANONICAL scenario-plan.json; DO NOT EDIT. */",
        "/* Action metadata is NOT hardware-issued, completed or checked evidence. */",
        "#ifndef SOC_SCENARIO_CONTRACT_V1_H",
        "#define SOC_SCENARIO_CONTRACT_V1_H",
        "#include <stdint.h>",
        "#include <stddef.h>",
        "#define SOC_SCN_CONTRACT_VERSION 1",
        "#define SOC_SCN_ACTION_COUNT " + str(len(actions)),
        "#define SOC_SCN_DEPENDENCY_COUNT " + str(len(dependencies)),
        "#define SOC_SCN_ARGUMENT_COUNT " + str(len(arguments)),
        "#define SOC_SCN_SCENARIO_ID " + quoted(plan["scenario_id"]),
        "#define SOC_SCN_PLAN_SHA256 " + quoted(sha),
        "#define SOC_SCN_SELECTED_SEED UINT64_C(" + str(plan.get("seed", 0)) + ")",
        "typedef struct {",
        "  const char *key;",
        "  uint64_t uint_value;",
        "  const char *text_value;",
        "  uint8_t is_text;",
        "} soc_scn_argument_t;",
        "typedef struct {",
        "  const char *action_instance_id;",
        "  const char *actor;",
        "  const char *kind;",
        "  const char *phase;",
        "  const char *expected_result_id;",
        "  uint32_t first_dependency;",
        "  uint32_t dependency_count;",
        "  uint32_t first_argument;",
        "  uint32_t argument_count;",
        "} soc_scn_action_t;",
        "static const char *const soc_scn_dependencies[] = {",
    ]
    lines.extend("  " + quoted(dep) + "," for dep in dependencies)
    if not dependencies:
        lines.append('  "", /* sentinel only; count is zero */')
    lines.extend(["};", "static const soc_scn_argument_t soc_scn_arguments[] = {"])
    for key, kind, value in arguments:
        if kind == "text":
            lines.append("  {" + quoted(key) + ", UINT64_C(0), " +
                         quoted(value) + ", UINT8_C(1)},")
        else:
            lines.append("  {" + quoted(key) + ", UINT64_C(" +
                         str(value) + "), NULL, UINT8_C(0)},")
    if not arguments:
        lines.append('  {"", UINT64_C(0), NULL, UINT8_C(0)}, /* sentinel */')
    lines.extend(["};", "static const soc_scn_action_t soc_scn_actions[] = {"])
    for action, di, dn, ai, an in records:
        fields = [
            quoted(action["action_instance_id"]), quoted(action["actor"]),
            quoted(action["kind"]), quoted(action["phase"]),
            quoted(action["expected_result_id"]),
            str(di), str(dn), str(ai), str(an),
        ]
        lines.append("  {" + ", ".join(fields) + "},")
    lines.extend([
        "};",
        "static inline const soc_scn_action_t *soc_scn_action_at(uint32_t index) {",
        "  return index < SOC_SCN_ACTION_COUNT ? &soc_scn_actions[index] : NULL;",
        "}",
        "static inline const soc_scn_argument_t *soc_scn_argument_at(uint32_t index) {",
        "  return index < SOC_SCN_ARGUMENT_COUNT ? &soc_scn_arguments[index] : NULL;",
        "}",
        "static inline const char *soc_scn_dependency_at(uint32_t index) {",
        "  return index < SOC_SCN_DEPENDENCY_COUNT ? soc_scn_dependencies[index] : NULL;",
        "}",
        "#endif /* SOC_SCENARIO_CONTRACT_V1_H */",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        header = render_header(args.plan.read_bytes())
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(header, encoding="ascii")
    print("SCN-C generated: " + str(args.out) +
          " (source action metadata only; NO hardware proof)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
