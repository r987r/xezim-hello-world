#!/usr/bin/env python3
"""Rebuild a named hardware variant using the EXISTING selected RTL generator.

No second SoC generator: the real regression source-selection path owns the
DDR NoCs, CPU firmware, PCIe/Ethernet RTL and Bender source closure. Copies
are review-only under .tools, not checked-in gen/ or an RTL simulator PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
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


def _source_equivalent_stage(value: dict) -> dict:
    """Compare all selected compiler bytes, not run-specific evidence identity.

    selected-rtl-manifest.json attests identity_sha256, which includes the
    individual regression invocation/run ID; its document SHA consequently
    changes when the same exact RTL/filelist is prepared twice. Both stage
    manifests are fully verified *before* this comparison; only their two
    provenance/document self-hashes can differ. Every source file/hash, config,
    compiler_input_sha256, selected top and stage inventory must still match.
    """
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise VariantBuildError("invalid selected build review stage")
    return {k: v for k, v in value.items()
            if k not in ("source_manifest_sha256", "manifest_sha256")}


CPU_DMA = "chip-cpu-dma"
CPU_DMA_TRACKED = Path("config/selected-rtl-reference/cpu-dma")
CPU_DMA_IMAGES = {
    "variant/soc_top.sv": ("flash.hex", "bootrom.hex"),
    "variant/full_chip_tb.sv": ("compute0.hex", "compute1.hex"),
    "variant/manifest.json": ("flash.hex",),
}


def _cpu_dma_reference(root: Path, directory: Path, manifest: dict, plan: dict, *, read, review_files=None):
    """Compare a verified CPU/iDMA source closure without rewriting the run."""
    from selected_rtl_provenance import _canonical_sha
    from test_identity import relative_path, validate

    identity = validate(plan["identity"], target=CPU_DMA)
    if (directory != root / ".tools/runs" / relative_path(identity)
            or manifest.get("profile") != CPU_DMA or plan.get("firmware_mode") != "cpu_dma"
            or manifest.get("compiled_top") != "full_chip_tb"
            or manifest.get("network_filelists") != {}
            or manifest.get("identity_sha256") != identity["identity_sha256"]
            or manifest.get("config_sha256") != identity["config_sha256"]
            or manifest.get("filelist_sha256") != identity["selection"]["filelist_sha256"]):
        raise VariantBuildError("foreign CPU/iDMA source selection")
    current = directory.relative_to(root).as_posix() + "/"
    stable = "@selected-cpu-dma/"
    def coordinate(name):
        if name.startswith(current):
            return stable + name.removeprefix(current)
        if name.startswith((".tools/runs/", ".tools/regression/", stable)):
            raise VariantBuildError("foreign CPU/iDMA run path in source closure")
        return name

    top = current + "variant/soc_top.sv"
    if manifest["selected_soc_top"] != top:
        raise VariantBuildError("CPU/iDMA selected top not owned by replay")
    generated = manifest["generated_sha256"]
    relocated = {}
    for suffix, images in CPU_DMA_IMAGES.items():
        name = current + suffix
        if name not in generated:
            raise VariantBuildError("missing CPU/iDMA relocation source")
        data = read(name, generated[name])
        for image in images:
            expected = current + "variant/" + image
            literal = b'"' + expected.encode() + b'"'
            if expected not in generated or data.count(literal) != 1:
                raise VariantBuildError("missing or ambiguous CPU/iDMA image reference: " + image)
            data = data.replace(literal, b'"' + coordinate(expected).encode() + b'"')
        if b".tools/runs/" in data or b".tools/regression/" in data:
            raise VariantBuildError("unreviewed run path in CPU/iDMA source")
        relocated[name] = hashlib.sha256(data).hexdigest()
        if review_files is not None:
            review_files[suffix] = data

    def inventory(values):
        return {coordinate(name): relocated.get(name, digest) for name, digest in values.items()}

    raw = read(current + "sources.f", manifest["filelist_sha256"])
    tokens = shlex.split(raw.decode())
    includes, defines, sources = plan["includes"], plan["defines"], plan["sources"]
    if tokens != (["+incdir+" + p for p in includes] + ["+define+" + p for p in defines] + sources):
        raise VariantBuildError("CPU/iDMA ordered compiler filelist disagrees with plan")
    def input_coordinate(name):
        path = Path(name)
        if not path.is_absolute() or not path.is_relative_to(root) or ".." in path.parts:
            raise VariantBuildError("foreign CPU/iDMA compiler input")
        return coordinate(path.relative_to(root).as_posix())

    source_order = [input_coordinate(name) for name in sources]
    normalized = raw.replace(current.encode(), stable.encode())
    if b".tools/runs/" in normalized or b".tools/regression/" in normalized:
        raise VariantBuildError("unreviewed compiler path in CPU/iDMA filelist")
    if review_files is not None:
        # Only parsed include/source path arguments are rebased; flag order
        # and every input digest remain intact. Not a runnable compiler list.
        include_order = [input_coordinate(name) for name in includes]
        portable_inputs = ["+incdir+" + p for p in include_order]
        portable_inputs += ["+define+" + d for d in defines] + source_order
        normalized = (json.dumps(portable_inputs, indent=2) + "\n").encode()
        review_files["compiler-input-order.json"] = normalized
    list_sha = hashlib.sha256(normalized).hexdigest()
    ref = {k: manifest[k] for k in ("definition_sha256", "compiled_top", "source_count",
                                    "defines", "includes", "args")}
    ref.update(
        source_sha256=inventory(manifest["source_sha256"]),
        generated_sha256=inventory(generated),
        include_headers_sha256=inventory(manifest["include_headers_sha256"]),
        selected_soc_top=coordinate(top), filelist_sha256=list_sha,
        config_sha256=_canonical_sha({**identity["selection"], "filelist_sha256": list_sha}))
    if review_files is not None:
        ref.update(includes=include_order, schema_version=1, profile=CPU_DMA,
                   evidence="review_only_not_compiler_input_or_simulation_result")
        review_files["reference.json"] = (json.dumps(ref, indent=2, sort_keys=True) + "\n").encode()
    return ref


def _validate_cpu_dma_tracked(root, review_files):
    directory = root / CPU_DMA_TRACKED
    if any(p.is_symlink() for p in (*directory.parents, directory) if p.is_relative_to(root)):
        raise VariantBuildError("unsafe CPU/iDMA tracked reference path")
    actual = list(directory.rglob("*"))
    if any(p.is_symlink() for p in actual):
        raise VariantBuildError("unsafe CPU/iDMA tracked reference member")
    if {p.relative_to(directory).as_posix() for p in actual if p.is_file()} != set(review_files):
        raise VariantBuildError("CPU/iDMA tracked reference inventory differs")
    for relative, expected in review_files.items():
        if (directory / relative).read_bytes() != expected:
            raise VariantBuildError("CPU/iDMA tracked reference changed: " + relative)


def _verified_cpu_dma_reference(root, folder, definition, *, staged=None, review_files=None):
    from selected_rtl_provenance import verify_selected_archive

    m = verify_selected_archive(root, CPU_DMA, definition, directory=folder)
    if staged is not None and (
            staged["source_manifest_sha256"] != m["manifest_sha256"]
            or staged["selected_top"] != m["selected_soc_top"]
            or staged["selected_top_sha256"] != m["generated_sha256"][m["selected_soc_top"]]
            or staged["compiler_input_sha256"] != m["compiler_input_sha256"]
            or staged["filelist_sha256"] != m["filelist_sha256"]):
        raise VariantBuildError("CPU/iDMA review stage and source archive disagree")
    plan = json.loads((folder / "plan.json").read_text())
    if plan.get("stage") != "files":
        raise VariantBuildError("CPU/iDMA review needs an exact files-only invocation")
    def read(name, digest):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise VariantBuildError("unsafe CPU/iDMA source path")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise VariantBuildError("CPU/iDMA source changed after verification")
        return data
    return _cpu_dma_reference(root, folder, m, plan, read=read, review_files=review_files)


def rebuild(root: Path, profile: str, output: Path, *, check: bool = False,
            runner=None, canonical_combined_files=False, check_tracked=False) -> dict:
    """Recreate actual selected RTL, then check the full staged-source digest.

    This executes real Bender/FlooGen/clang source preparation, not the RTL
    simulator; a completed source build does not imply elaboration or PASS.
    """
    root = Path(root).resolve()
    if check_tracked and (profile != CPU_DMA or check):
        raise VariantBuildError("tracked reference check is only a fresh CPU/iDMA source selection")
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
    def prepare():
        completed = runner(command, cwd=root)
        if completed.returncode:
            raise VariantBuildError(
                "selected variant source generation failed: " +
                str(completed.stderr)[-1500:])

    directory = None
    if canonical_combined_files:
        from combined_source_projection import PROFILE as COMBINED, prepared_workspace, verified_inputs
        if profile != COMBINED:
            raise VariantBuildError("canonical combined files require the combined profile")
        command.append("--canonical-combined-files")
        directory = prepared_workspace(root, definition, prepare)
    elif profile == CPU_DMA:
        from run_workspace import selected_run_folder, snapshot_run_ids
        earlier = snapshot_run_ids(root, profile, definition, stage="files")
        prepare()
        directory = selected_run_folder(root, profile, definition, stage="files", prior_run_ids=earlier)
        if directory is None:
            raise VariantBuildError("no new exact CPU/iDMA files-only workspace")
    else:
        prepare()
    if check:
        (root / ".tools").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="variant-rebuild-", dir=root / ".tools") as tmp:
            draft = Path(tmp)
            stage_args = {"directory": directory} if directory is not None else {}
            expected = stage(root, profile, definition, draft, **stage_args)
            fresh_folder = _review_folder(root, draft, variant)
            verified = verify_stage(fresh_folder)
            if expected != verified:
                raise VariantBuildError("freshly regenerated review stage failed self-verification")
            if profile == CPU_DMA:
                baseline_dir = root / Path(baseline["files"]["compiler/sources.f"]["original"]).parent
                if baseline_dir == directory:
                    raise VariantBuildError("CPU/iDMA review reused its prior workspace")
                left = _verified_cpu_dma_reference(root, baseline_dir, definition, staged=baseline)
                right = _verified_cpu_dma_reference(root, directory, definition, staged=verified)
            elif directory is not None:
                # Both stage manifests are actual and verified. Only compare
                # the historical coordinates in memory, never archive them.
                original_filelist = Path(baseline["files"]["compiler/sources.f"]["original"])
                if original_filelist.name != "sources.f":
                    raise VariantBuildError("baseline lacks an owned compiler filelist")
                baseline_dir = root / original_filelist.parent
                if baseline_dir == directory:
                    raise VariantBuildError("combined review reused its prior workspace")
                baseline_inputs = verified_inputs(root, baseline_dir, definition)
                fresh_inputs = verified_inputs(root, directory, definition)
                if (baseline.get("source_manifest_sha256") != baseline_inputs.actual_manifest_sha256
                        or verified.get("source_manifest_sha256") != fresh_inputs.actual_manifest_sha256):
                    raise VariantBuildError("combined review stage and original manifest disagree")
                left, right = baseline_inputs.reference, fresh_inputs.reference
            else:
                left = _source_equivalent_stage(baseline)
                right = _source_equivalent_stage(verified)
            if left != right:
                details = _stage_differences(left, right)
                raise VariantBuildError(
                    "regenerated selected RTL and compiler-input closure differs from review baseline; "
                    "changed paths (bounded): " + ", ".join(details))
            return {"profile": profile, "variant": variant,
                    "selected_soc_top_sha256": baseline["selected_top_sha256"],
                    "compiler_input_sha256": baseline["compiler_input_sha256"],
                    "review_stage": str(output_folder.relative_to(root)),
                    **({"files_workspace": directory.relative_to(root).as_posix()} if directory else {}),
                    "status": "selected_sources_rebuilt_exactly_not_simulated"}
    if profile == CPU_DMA:
        review_files = {} if check_tracked else None
        _verified_cpu_dma_reference(root, directory, definition, review_files=review_files)
        if check_tracked:
            _validate_cpu_dma_tracked(root, review_files)
    elif directory is not None:
        verified_inputs(root, directory, definition)
    generated = stage(root, profile, definition, output,
                      **({"directory": directory} if directory is not None else {}))
    if verify_stage(output_folder) != generated:
        raise VariantBuildError("freshly staged variant does not verify")
    return {"profile": profile, "variant": variant,
            "selected_soc_top_sha256": generated["selected_top_sha256"],
            "compiler_input_sha256": generated["compiler_input_sha256"],
            "review_stage": str(output_folder.relative_to(root)),
            **({"files_workspace": directory.relative_to(root).as_posix()} if directory else {}),
            "status": "selected_sources_generated_not_simulated",
            **({"tracked_reference_verified": CPU_DMA_TRACKED.as_posix()} if check_tracked else {})}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--profile", default="chip-ethernet-ddr-pcie")
    cli.add_argument("--out", type=Path,
                     default=ROOT / ".tools/rtl-review-staging")
    cli.add_argument("--check", action="store_true",
                     help="regenerate and compare exact selected RTL/source closure")
    cli.add_argument("--canonical-combined-files", action="store_true")
    cli.add_argument("--check-tracked", action="store_true",
                     help="verify checked-in CPU/iDMA review bytes from fresh source selection")
    args = cli.parse_args()
    result = rebuild(ROOT, args.profile, args.out, check=args.check, check_tracked=args.check_tracked,
                     canonical_combined_files=(args.canonical_combined_files or
                                               args.profile == "chip-ethernet-ddr-pcie"))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
