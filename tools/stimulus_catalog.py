#!/usr/bin/env python3
"""Validate versioned, reviewable stimulus intent for every regression target.

Every declaration is derived from the one checked-in config/stimulus/tests.yaml.
This catalog does not dispatch legacy C/SV/Python stimulus, claim observed
hardware activity or redefine simulator/firmware/Bender selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "config/stimulus/tests.yaml"
PHASES = ("init", "run", "check")
KINDS = {"scenario_native", "observed_milestones", "legacy_opaque", "non_runtime"}
SCENARIOS = {"cpu_dma_scenario", "scenario_bfm"}
NON_RUNTIME = {"verilator-lint", "xezim-compile"}
SLUG = re.compile(r"^[a-z][a-z0-9-]*$")


class StimulusCatalogError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently overwriting a test."""


def _unique_mapping(loader, node):
    result = {}
    for key_node, val_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise StimulusCatalogError(f"invalid/duplicate stimulus YAML key: {key!r}")
        result[key] = loader.construct_object(val_node, deep=True)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _type_for(test: dict) -> str:
    engine, mode = test.get("engine"), test.get("firmware_mode")
    if test.get("mode") == "compile" or engine in NON_RUNTIME:
        return "non_runtime"
    if mode in SCENARIOS:
        return "scenario_native"
    if (test.get("report") or {}).get("flow", {}).get("required_steps"):
        return "observed_milestones"
    return "legacy_opaque"


def load(config: dict, *, root: Path = ROOT) -> dict:
    """Return all 28 selected targets from one readable source; fail closed."""
    root = Path(root).resolve()
    path = root / SOURCE
    try:
        raw = path.read_bytes()
        data = yaml.load(raw, Loader=_UniqueLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise StimulusCatalogError("unreadable/invalid checked-in stimulus YAML") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "tests"} or data["schema_version"] != 1:
        raise StimulusCatalogError("unsupported stimulus catalog schema")
    items = data["tests"]
    registered = config.get("tests")
    if not isinstance(items, list) or not isinstance(registered, dict) or not registered:
        raise StimulusCatalogError("stimulus/regression catalog missing tests")
    result, logical_names = {}, set()
    for item in items:
        allowed = {"logical_test", "targets", "execution", "purpose", "phases", "scenario_source"}
        if not isinstance(item, dict) or set(item) - allowed or allowed - {"scenario_source"} - set(item):
            raise StimulusCatalogError("invalid stimulus test entry/schema")
        logical = item["logical_test"]
        targets, mode = item["targets"], item["execution"]
        if not isinstance(logical, str) or not SLUG.fullmatch(logical) or logical in logical_names:
            raise StimulusCatalogError(f"duplicate/invalid canonical logical test {logical!r}")
        logical_names.add(logical)
        if mode not in KINDS or not isinstance(targets, list) or not targets:
            raise StimulusCatalogError(f"{logical}: missing targets or invalid execution type")
        purpose = item["purpose"]
        if not isinstance(purpose, str) or not 10 <= len(purpose) <= 512:
            raise StimulusCatalogError(f"{logical}: missing/invalid test purpose")
        phases = item["phases"]
        if not isinstance(phases, dict) or set(phases) != set(PHASES):
            raise StimulusCatalogError(f"{logical}: INIT/RUN/CHECK must be explicit")
        for phase in PHASES:
            lines = phases[phase]
            if not isinstance(lines, list) or len(lines) > 12 or (
                mode != "non_runtime" and not lines) or (
                mode == "non_runtime" and lines):
                raise StimulusCatalogError(f"{logical}: invalid {phase} outline")
            if any(not isinstance(line, str) or not 8 <= len(line) <= 512 for line in lines):
                raise StimulusCatalogError(f"{logical}: invalid {phase} description")
        scenario = item.get("scenario_source")
        if (mode == "scenario_native") != (scenario is not None):
            raise StimulusCatalogError(f"{logical}: only scenario-native tests may reference executable plan")
        if scenario is not None:
            if (not isinstance(scenario, str) or not re.fullmatch(
                    r"config/scenarios/[A-Za-z0-9_-]+\.json", scenario)
                    or not (root / scenario).is_file()):
                raise StimulusCatalogError(f"{logical}: unsafe/absent executable scenario source")
        encoded = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        fingerprint = hashlib.sha256(encoded).hexdigest()
        for target in targets:
            if not isinstance(target, str) or not SLUG.fullmatch(target) or target in result:
                raise StimulusCatalogError(f"{logical}: duplicate/invalid regression target: {target!r}")
            test = registered.get(target)
            if not isinstance(test, dict):
                raise StimulusCatalogError(f"{logical}: unknown configured target {target}")
            if test.get("logical_test", logical) != logical:
                raise StimulusCatalogError(f"{target}: stimulus logical_test differs from regression naming authority")
            if _type_for(test) != mode:
                raise StimulusCatalogError(f"{target}: claimed stimulus execution differs from actual runner adapter")
            if mode == "scenario_native" and test.get("flow_plan") != scenario:
                raise StimulusCatalogError(f"{target}: scenario source differs from executable plan")
            result[target] = {"source": SOURCE, "sha256": fingerprint,
                              "logical_test": logical, "execution": mode,
                              "purpose": purpose, "phases": phases,
                              "scenario_source": scenario}
    missing, orphan = set(registered) - set(result), set(result) - set(registered)
    if missing or orphan:
        raise StimulusCatalogError(f"stimulus YAML coverage mismatch: missing={sorted(missing)}, unknown={sorted(orphan)}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--list", action="store_true", help="list human-readable tests and execution status")
    parser.add_argument("--show", metavar="TARGET", help="display selected target's stimulus definition as JSON")
    args = parser.parse_args()
    cfg = yaml.safe_load((args.root / "config/regression.yaml").read_text())
    items = load(cfg, root=args.root)
    if args.show:
        if args.show not in items:
            parser.error("unknown regression target")
        print(json.dumps(items[args.show], indent=2))
    elif args.list:
        for target, v in items.items():
            print(f"{v['logical_test']:35} {target:24} {v['execution']}")
    else:
        counts = {k: sum(v["execution"] == k for v in items.values()) for k in sorted(KINDS)}
        print(f"PASS: {len(items)} configured test targets have checked-in stimulus specifications: {counts}")


if __name__ == "__main__":
    main()
