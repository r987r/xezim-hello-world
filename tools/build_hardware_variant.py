#!/usr/bin/env python3
"""Rebuild a named hardware variant using the EXISTING selected RTL generator.

No second SoC generator: the real regression source-selection path owns the
DDR NoCs, CPU firmware, PCIe/Ethernet RTL and Bender source closure. Copies
are review-only under .tools, not checked-in gen/ or an RTL simulator PASS.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

from stage_selected_rtl import stage, verify_stage
from test_identity import config_target

ROOT = Path(__file__).resolve().parents[1]
PROFILE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


class VariantBuildError(ValueError):
    pass


def selected_definition(root: Path, profile: str) -> dict:
    if not PROFILE.fullmatch(profile):
        raise VariantBuildError("invalid hardware source profile name")
    document = yaml.safe_load((root / "config/regression.yaml").read_text())
    from regress import load_config
    # Use one existing regression validator instead of defining another schema.
    if root == ROOT:
        document = load_config(root / "config/regression.yaml")
    if not isinstance(document, dict) or not isinstance(document.get("tests"), dict):
        raise VariantBuildError("missing authoritative regression catalog")
    definition = document["tests"].get(profile)
    if (not isinstance(definition, dict)
            or definition.get("top") not in ("full_chip_tb", "full_chip_dma_tb")
            or definition.get("firmware_mode") is None):
        raise VariantBuildError("requires an explicit selected full-chip hardware variant")
    return definition


def _review_folder(root: Path, output: Path, variant: str) -> Path:
    project = yaml.safe_load((root / "config/soc.yaml").read_text())["name"]
    if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", project):
        raise VariantBuildError("invalid project name")
    if output.is_symlink() or not output.resolve().is_relative_to(root):
        raise VariantBuildError("review output must be inside checkout")
    if output.resolve().is_relative_to(root / "gen"):
        raise VariantBuildError("review output must not modify generator-owned gen/")
    if not output.resolve().is_relative_to(root / ".tools"):
        raise VariantBuildError("hardware variant build outputs must stay in .tools/")
    return output.resolve() / project / variant


def _stage_differences(before: dict, after: dict, *, limit: int = 24) -> list[str]:
    """Show bounded exact hash/path differences; never silently accept drift."""
    changes: list[str] = []

    def walk(path: str, old, new) -> None:
        if len(changes) >= limit:
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(set(old) | set(new)):
                if len(changes) >= limit:
                    return
                name = f"{path}.{key}" if path else str(key)
                if key not in old:
                    changes.append(f"{name}: added")
                elif key not in new:
                    changes.append(f"{name}: removed")
                else:
                    walk(name, old[key], new[key])
        elif old != new:
            # Known digest fields are safe to display in CI; arbitrary path
            # strings or metadata values are not needed for diagnosis.
            changes.append(f"{path}: changed")

    walk("", before, after)
    return changes


def rebuild(root: Path, profile: str, output: Path, *, check: bool = False,
            runner=None) -> dict:
    """Recreate actual selected RTL, then check the full staged-source digest.

    This executes real Bender/FlooGen/clang source preparation, not the RTL
    simulator; a completed source build does not imply elaboration or PASS.
    """
    root = Path(root).resolve()
    definition = selected_definition(root, profile)
    variant = config_target(definition)
    output_folder = _review_folder(root, output, variant)
    baseline = verify_stage(output_folder) if check else None
    command = [sys.executable, str(root / "tools/regress.py"),
               profile, "--stage", "files"]
    if runner is None:
        def runner(cmd, cwd):
            return subprocess.run(cmd, cwd=cwd, text=True,
                                  capture_output=True, check=False, timeout=1800)
    completed = runner(command, cwd=root)
    if completed.returncode:
        raise VariantBuildError(
            "selected variant source generation failed: " +
            str(completed.stderr)[-1500:])
    if check:
        (root / ".tools").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="variant-rebuild-", dir=root / ".tools") as tmp:
            draft = Path(tmp)
            expected = stage(root, profile, definition, draft)
            fresh_folder = _review_folder(root, draft, variant)
            verified = verify_stage(fresh_folder)
            if expected != verified:
                raise VariantBuildError("freshly regenerated review stage failed self-verification")
            if verified != baseline:
                details = _stage_differences(baseline, verified)
                raise VariantBuildError(
                    "regenerated selected RTL and compiler-input closure differs from review baseline; "
                    "changed paths (bounded): " + ", ".join(details))
            return {"profile": profile, "variant": variant,
                    "selected_soc_top_sha256": baseline["selected_top_sha256"],
                    "compiler_input_sha256": baseline["compiler_input_sha256"],
                    "review_stage": str(output_folder.relative_to(root)),
                    "status": "selected_sources_rebuilt_exactly_not_simulated"}
    generated = stage(root, profile, definition, output)
    if verify_stage(output_folder) != generated:
        raise VariantBuildError("freshly staged variant does not verify")
    return {"profile": profile, "variant": variant,
            "selected_soc_top_sha256": generated["selected_top_sha256"],
            "compiler_input_sha256": generated["compiler_input_sha256"],
            "review_stage": str(output_folder.relative_to(root)),
            "status": "selected_sources_generated_not_simulated"}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--profile", default="chip-ethernet-ddr-pcie")
    cli.add_argument("--out", type=Path,
                     default=ROOT / ".tools/rtl-review-staging")
    cli.add_argument("--check", action="store_true",
                     help="regenerate and compare exact selected RTL/source closure")
    args = cli.parse_args()
    result = rebuild(ROOT, args.profile, args.out, check=args.check)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
