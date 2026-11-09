#!/usr/bin/env python3
"""Multi-seed replay *selection* through the existing canonical SCN resolver.

One directed and N randomized tests use the identical scenario schema/typed
actions. This tool never dispatches, simulates, or claims protocol PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dv.common.scenario import canonical_json, resolve_scenario, ScenarioError

U32 = (1 << 32) - 1
MAX_CASES = 128
EVIDENCE = "source_selected_intent_only_not_hardware_execution"


class MatrixError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_sources(scenario: Path, soc: Path) -> tuple[dict, dict, bytes, bytes]:
    for path in (scenario, soc):
        if not path.is_file() or path.is_symlink():
            raise MatrixError("missing or symlink scenario/SoC source")
    a, b = scenario.read_bytes(), soc.read_bytes()
    try:
        spec, config = json.loads(a), yaml.safe_load(b)
    except (ValueError, yaml.YAMLError) as exc:
        raise MatrixError(f"invalid source scenario or SoC: {exc}") from exc
    if not isinstance(spec, dict) or not isinstance(config, dict):
        raise MatrixError("scenario and SoC must both be mappings")
    return spec, config, a, b


def choose_seeds(spec: dict, *, seeds: list[int] | None = None,
                 random_runs: int = 0) -> list[int]:
    if type(random_runs) is not int or not 0 <= random_runs <= MAX_CASES:
        raise MatrixError("random-runs outside 0..128")
    if seeds is not None and random_runs:
        raise MatrixError("explicit seeds and random runs are mutually exclusive")
    if seeds is None:
        if random_runs:
            result: list[int] = []
            used: set[int] = set()
            while len(result) < random_runs:
                value = secrets.randbelow(U32 + 1)
                if value not in used:
                    used.add(value)
                    result.append(value)
        else:
            result = [spec.get("seed")]
    else:
        result = seeds
    if (not isinstance(result, list) or not 1 <= len(result) <= MAX_CASES
            or any(type(x) is not int or not 0 <= x <= U32 for x in result)
            or len(set(result)) != len(result)):
        raise MatrixError("seeds must be distinct unsigned 32-bit integers (1..128)")
    return result


def _plan(spec: dict, config: dict, seed: int, source_revision: str | None) -> bytes:
    copied = dict(spec)
    copied["seed"] = seed
    return canonical_json(resolve_scenario(
        copied, config, source_revision=source_revision)).encode("ascii")


def _manifest(spec: dict, config: dict, source_bytes: bytes, soc_bytes: bytes,
              seeds: list[int], source_revision: str | None) -> tuple[dict, dict[str, bytes]]:
    plans: dict[str, bytes] = {}
    entries: list[dict] = []
    for seed in seeds:
        raw = _plan(spec, config, seed, source_revision)
        doc = json.loads(raw)
        name = f"scenario-plan-{seed}.json"
        if doc.get("execution_evidence") is not None or doc.get("kind") != "soc_scenario_intent_only":
            raise MatrixError("resolved scenario asserts unobserved hardware proof")
        plans[name] = raw
        entries.append({
            "seed": seed, "file": name,
            "plan_sha256": _sha(raw),
            "action_count": len(doc["actions"]),
            "scenario_id": doc["scenario_id"],
        })
    return ({
        "schema_version": 1, "evidence": EVIDENCE,
        "scenario_sha256": _sha(source_bytes),
        "soc_sha256": _sha(soc_bytes),
        "source_revision": source_revision,
        "cases": entries,
    }, plans)


def write_matrix(scenario: Path, soc: Path, output: Path, *,
                 seeds: list[int] | None = None, random_runs: int = 0,
                 source_revision: str | None = None) -> dict:
    spec, config, raw, soc_raw = _read_sources(scenario, soc)
    selected = choose_seeds(spec, seeds=seeds, random_runs=random_runs)
    manifest, plans = _manifest(spec, config, raw, soc_raw, selected, source_revision)
    if output.exists() or output.is_symlink():
        raise MatrixError("refusing to overwrite existing seed matrix; use --check")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    for name, blob in plans.items():
        (output / name).write_bytes(blob)
    (output / "matrix.json").write_text(canonical_json(manifest), encoding="ascii")
    return manifest


def check_matrix(scenario: Path, soc: Path, output: Path) -> dict:
    spec, config, raw, soc_raw = _read_sources(scenario, soc)
    if not output.is_dir() or output.is_symlink():
        raise MatrixError("missing or symlink seed matrix directory")
    index = output / "matrix.json"
    if not index.is_file() or index.is_symlink():
        raise MatrixError("missing or unsafe seed matrix index")
    blob = index.read_bytes()
    try:
        doc = json.loads(blob)
    except ValueError as exc:
        raise MatrixError("invalid seed matrix index") from exc
    if canonical_json(doc).encode("ascii") != blob or not isinstance(doc, dict):
        raise MatrixError("noncanonical seed matrix index")
    if doc.get("evidence") != EVIDENCE:
        raise MatrixError("seed matrix falsely claims hardware execution")
    if doc.get("scenario_sha256") != _sha(raw) or doc.get("soc_sha256") != _sha(soc_raw):
        raise MatrixError("scenario/SoC source changed after matrix generation")
    if set(doc) != {"schema_version","evidence","scenario_sha256","soc_sha256","source_revision","cases"} or doc["schema_version"] != 1:
        raise MatrixError("invalid seed matrix schema")
    entries = doc["cases"]
    if not isinstance(entries, list):
        raise MatrixError("missing matrix cases")
    seeds = choose_seeds(spec, seeds=[e.get("seed") for e in entries if isinstance(e, dict)])
    if len(seeds) != len(entries):
        raise MatrixError("invalid matrix entry")
    reference, expected = _manifest(spec, config, raw, soc_raw, seeds, doc["source_revision"])
    if doc != reference:
        raise MatrixError("matrix plan hash/action count/source revision differs")
    files = {p.name for p in output.iterdir()}
    if files != set(expected) | {"matrix.json"}:
        raise MatrixError("missing or extra replay plan artifacts")
    for name, data in expected.items():
        path = output / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != data:
            raise MatrixError("tampered or foreign resolved scenario: " + name)
    return doc


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--scenario", type=Path, required=True)
    cli.add_argument("--soc", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--seeds", type=int, nargs="+")
    cli.add_argument("--random-runs", type=int, default=0)
    cli.add_argument("--source-revision")
    cli.add_argument("--check", action="store_true")
    args = cli.parse_args()
    try:
        if args.check:
            if args.seeds is not None or args.random_runs or args.source_revision is not None:
                raise MatrixError("--check reads original recorded seeds and revision only")
            manifest = check_matrix(args.scenario, args.soc, args.out)
        else:
            manifest = write_matrix(args.scenario, args.soc, args.out,
                                    seeds=args.seeds, random_runs=args.random_runs,
                                    source_revision=args.source_revision)
    except (OSError, ValueError, TypeError) as exc:
        cli.error(str(exc))
    print(f"SCN selected replay matrix: {len(manifest['cases'])} intent-only plans; hardware unmeasured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
