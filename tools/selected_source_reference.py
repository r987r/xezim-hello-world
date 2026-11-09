#!/usr/bin/env python3
"""Fail-closed review of a real selected RTL build against qualified source SHA.

This is a historical exact-source acceptance lock, not an RTL generator, an
elaborated bit graph or a claim that firmware/PHY hardware is production-ready.
The existing selected-RTL archive verifier remains the source of truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import yaml

from selected_rtl_provenance import verify_selected_archive

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{64}\\Z")
PROFILE = "chip-ethernet-ddr-pcie"
TOP = ".tools/regression/chip-ethernet-ddr-pcie/variant/soc_top.sv"


class ReferenceError(ValueError):
    pass


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def validate_lock(lock: dict) -> None:
    if not isinstance(lock, dict) or lock.get("schema_version") != 1:
        raise ReferenceError("unknown selected-source reference schema")
    if lock.get("project") != "xezim_soc_dv" or lock.get("profile") != PROFILE:
        raise ReferenceError("foreign selected-source project/profile")
    if lock.get("compiled_top") != "full_chip_tb" or lock.get("selected_soc_top") != TOP:
        raise ReferenceError("foreign selected RTL compilation or top")
    if not _sha(lock.get("verified_pr_head")) or lock.get("source_count", 0) <= 0:
        raise ReferenceError("missing original accepted PR SHA or source count")
    for name in ("required_generated_sha256", "required_source_sha256"):
        hashes = lock.get(name)
        if not isinstance(hashes, dict) or not hashes:
            raise ReferenceError("missing mandatory source lock entries: " + name)
        for path, digest in hashes.items():
            if (not isinstance(path, str) or not path.startswith(".tools/")
                    or "/../" in path or not _sha(digest)):
                raise ReferenceError("malformed selected reference source/hash")
    if lock["required_generated_sha256"].get(TOP) is None:
        raise ReferenceError("missing real combined generated top SHA")
    if not set(lock["required_generated_sha256"]).issubset(
            set(lock["required_generated_sha256"]) | set(lock["required_source_sha256"])):
        raise ReferenceError("invalid generated source closure")


def compare(lock: dict, actual: dict) -> dict:
    """Compare SHA-pinned paths without treating run IDs as source identity."""
    validate_lock(lock)
    if not isinstance(actual, dict) or actual.get("schema_version") != 1:
        raise ReferenceError("unverified or unsupported selected-source manifest")
    for key in ("profile", "compiled_top", "selected_soc_top", "source_count"):
        if actual.get(key) != lock.get(key):
            raise ReferenceError(f"selected build differs in {key}")
    for key in ("required_generated_sha256", "required_source_sha256"):
        actual_key = "generated_sha256" if key == "required_generated_sha256" else "source_sha256"
        hashes = actual.get(actual_key)
        if not isinstance(hashes, dict):
            raise ReferenceError("missing selected build SHA inventory: " + actual_key)
        for path, expected in sorted(lock[key].items()):
            if hashes.get(path) != expected:
                raise ReferenceError("qualified selected RTL changed: " + path)
            # Generated RTL must also be part of the original compiler closure,
            # not just a separately produced file.
            if key == "required_generated_sha256" and actual.get("source_sha256", {}).get(path) != expected:
                raise ReferenceError("generated source missing from compiled closure: " + path)
    if not _sha(actual.get("compiler_input_sha256")) or not _sha(actual.get("filelist_sha256")):
        raise ReferenceError("missing actual compiler input/filelist fingerprints")
    return {
        "schema_version": 1,
        "profile": lock["profile"],
        "selected_soc_top": lock["selected_soc_top"],
        "selected_top_sha256": lock["required_generated_sha256"][TOP],
        "compiler_input_sha256": actual["compiler_input_sha256"],
        "filelist_sha256": actual["filelist_sha256"],
        "checked_generated_sources": len(lock["required_generated_sha256"]),
        "checked_other_sources": len(lock["required_source_sha256"]),
        "evidence": "qualified_historical_source_digest_match_not_bit_elaboration_or_simulation",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--reference", type=Path,
                   default=ROOT / "config/selected-rtl-reference/ethernet-ddr-pcie.json")
    p.add_argument("--profile", default=PROFILE)
    args = p.parse_args()
    root = args.root.resolve()
    if args.profile != PROFILE:
        raise ReferenceError("unqualified selected profile")
    ref = args.reference.resolve()
    if not ref.is_relative_to(root) or ref.is_symlink() or not ref.is_file():
        raise ReferenceError("reference must be a real checkout-owned file")
    lock = json.loads(ref.read_text())
    tests = yaml.safe_load((root / "config/regression.yaml").read_text())["tests"]
    if args.profile not in tests:
        raise ReferenceError("missing selected regression profile")
    actual = verify_selected_archive(root, args.profile, tests[args.profile])
    report = compare(lock, actual)
    print("PASS: selected combined RTL matches qualified historical source digests")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
