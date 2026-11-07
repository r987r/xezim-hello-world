#!/usr/bin/env python3
"""Source-selected provenance for real compiler/elaboration adapters.

This is an attestation of the exact Bender-resolved *inputs*, not evidence
that any port is connected correctly or that a transfer was observed.
Do not create a second IP, topology or interface configuration registry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


def selected(root: Path, profile: str) -> dict:
    root = Path(root).resolve()
    if not isinstance(profile, str) or not profile or "/" in profile or ".." in profile:
        raise ValueError("invalid regression profile")
    config = yaml.safe_load((root / "config/regression.yaml").read_text())
    test = config.get("tests", {}).get(profile)
    if not isinstance(test, dict) or not isinstance(test.get("top"), str):
        raise ValueError(f"unknown or non-elaboratable profile: {profile}")
    folder = root / ".tools/regression" / profile
    source_list, plan_file = folder / "sources.f", folder / "plan.json"
    if not source_list.is_file() or not plan_file.is_file():
        raise ValueError(f"{profile}: missing original resolved filelist/plan")
    plan = json.loads(plan_file.read_text())
    if (plan.get("target") != profile or plan.get("top") != test["top"]
            or not isinstance(plan.get("sources"), list) or not plan["sources"]
            or plan.get("source_target") != test.get("sources")):
        raise ValueError(f"{profile}: selected plan disagrees with registered source/top")
    seen = set()
    sources = {}
    for raw in plan["sources"]:
        if not isinstance(raw, str) or not raw:
            raise ValueError("invalid resolved RTL source")
        path = Path(raw)
        path = (path if path.is_absolute() else root / path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"{profile}: selected source missing or outside repository: {raw}")
        rel = path.relative_to(root).as_posix()
        if rel in seen:
            raise ValueError(f"{profile}: duplicate selected RTL source: {rel}")
        seen.add(rel)
        sources[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    filelist_sha = hashlib.sha256(source_list.read_bytes()).hexdigest()
    identity_path = folder / "identity.json"
    if identity_path.is_file():
        identity = json.loads(identity_path.read_text())
        selection = identity.get("selection", {})
        if selection.get("filelist_sha256") != filelist_sha:
            raise ValueError(f"{profile}: selected identity/filelist SHA mismatch")
        if identity.get("legacy_target") != profile:
            raise ValueError(f"{profile}: canonical identity references different selected target")
    return {
        "schema_version": 1,
        "profile": profile,
        "top": test["top"],
        "filelist_sha256": filelist_sha,
        "plan_sha256": hashlib.sha256(plan_file.read_bytes()).hexdigest(),
        "selected_source_sha256": sources,
        "source_count": len(sources),
        "evidence": "original_selected_sources_not_elaborated_or_wired",
        "source_list": source_list,
    }


def public_fields(attestation: dict) -> dict:
    return {key:value for key,value in attestation.items() if key != "source_list"}
