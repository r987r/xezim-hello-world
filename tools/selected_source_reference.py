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
SHA = re.compile(r"[0-9a-f]{64}")
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
    git_sha = lock.get("verified_pr_head")
    if (not isinstance(git_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", git_sha)
            or type(lock.get("source_count")) is not int or lock["source_count"] <= 0):
        raise ReferenceError("missing original accepted PR SHA or source count")
    for name in ("required_generated_sha256", "required_source_sha256",
                 "historical_volatile_source_sha256"):
        hashes = lock.get(name)
        if not isinstance(hashes, dict) or (name != "required_source_sha256" and not hashes):
            raise ReferenceError("missing mandatory source lock entries: " + name)
        for path, digest in hashes.items():
            if (not isinstance(path, str) or not path.startswith(".tools/")
                    or "/../" in path or not _sha(digest)):
                raise ReferenceError("malformed selected reference source/hash")
    variable = lock.get("volatile_source_paths")
    if (variable != sorted(lock["historical_volatile_source_sha256"])
            or len(variable) != 1
            or variable[0] in lock["required_source_sha256"]
            or not _sha(lock.get("stable_compiler_inputs_sha256"))
            or not _sha(lock.get("historical_compiler_input_sha256"))):
        raise ReferenceError("invalid/non-audited variable generated DDR source")
    if lock["required_generated_sha256"].get(TOP) is None:
        raise ReferenceError("missing real combined generated top SHA")
    if not _sha(lock.get("filelist_sha256")):
        raise ReferenceError("invalid qualified compiler filelist reference")


def _stable_compiler_inputs(actual: dict, volatile: list[str]) -> str:
    """Fingerprint stable compiler inputs, explicitly excluding generated DDR Verilog.

    This is not a qualification of the variable source; its actual SHA remains
    visible in the report and must be separately reviewed before #184 closure.
    """
    import hashlib
    fields = ("filelist_sha256", "config_sha256", "definition_sha256",
              "include_headers_sha256", "network_filelists", "defines",
              "includes", "args", "compiled_top", "selected_soc_top")
    source = actual.get("source_sha256")
    if not isinstance(source, dict) or not isinstance(volatile, list):
        raise ReferenceError("missing compiler source inventory")
    if len(source) != 312 or set(volatile) - set(source):
        raise ReferenceError("selected compiler source inventory changed")
    obj = {key: actual.get(key) for key in fields}
    obj["source_sha256"] = {k: v for k, v in source.items() if k not in volatile}
    if any(obj.get(key) is None for key in fields):
        raise ReferenceError("missing compiler selection metadata")
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
            # Verilog in the compiler closure must match its generated copy.
            # Firmware/boot images are runtime-loaded, not SV source-list inputs.
            if (key == "required_generated_sha256" and path.endswith(".sv")
                    and actual.get("source_sha256", {}).get(path) != expected):
                raise ReferenceError("generated RTL missing from compiled closure: " + path)
    stable = _stable_compiler_inputs(actual, lock["volatile_source_paths"])
    if stable != lock["stable_compiler_inputs_sha256"]:
        raise ReferenceError("stable 311-source compiler closure changed")
    if actual.get("filelist_sha256") != lock["filelist_sha256"]:
        raise ReferenceError("full selected source closure changed: filelist_sha256")
    for path in lock["volatile_source_paths"]:
        if not _sha(actual.get("source_sha256", {}).get(path)):
            raise ReferenceError("variable generated DDR source missing from compiler closure")
    return {
        "schema_version": 1,
        "profile": lock["profile"],
        "selected_soc_top": lock["selected_soc_top"],
        "selected_top_sha256": lock["required_generated_sha256"][TOP],
        "compiler_input_sha256": actual["compiler_input_sha256"],
        "filelist_sha256": actual["filelist_sha256"],
        "checked_generated_sources": len(lock["required_generated_sha256"]),
        "checked_other_sources": len(lock["required_source_sha256"]),
        "stable_compiler_inputs_sha256": stable,
        "variable_generated_ddr_sha256": {
            path: actual["source_sha256"][path] for path in lock["volatile_source_paths"]
        },
        "evidence": "stable_selected_source_match_variable_ddr_unqualified_not_elaboration_or_simulation",
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
