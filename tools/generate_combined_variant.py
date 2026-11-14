#!/usr/bin/env python3
"""Publish the ACTUAL selected combined RTL into a reproducible review tree.

Uses the existing regress.py source preparation, selected-RTL provenance and
pinned LiteDRAM/FlooGen. No second HDL or firmware emitter is introduced.
This is an opt-in generator-owned source review step, not physical bit proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

from selected_rtl_provenance import verify_selected_archive

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "chip-ethernet-ddr-pcie"
VARIANT = "ethernet-ddr-pcie"
SOURCE_ROOT = f".tools/regression/{PROFILE}/"
DDR_ROOT = ".tools/ddr4/litedram_sim/gateware/"


class CombinedGenerationError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree(folder: Path) -> dict[str, bytes]:
    if any(p.is_symlink() for p in folder.rglob("*")):
        raise CombinedGenerationError("generated variant contains unsafe symbolic links")
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob("*") if p.is_file()}


def source_bytes(root: Path, name: str, expected: str) -> bytes:
    if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
        raise CombinedGenerationError("unsafe selected compiler path")
    path = root / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise CombinedGenerationError("missing or symlink selected compiler source: " + name)
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise CombinedGenerationError("source differs from original selected archive: " + name)
    return raw


def portable_image_paths(source: bytes, project: str, relative: str) -> bytes:
    """Normalize ONLY known firmware references of freshly selected RTL.

    All other compiler text must remain byte-identical. Unknown/extra paths
    fail rather than silently publish a broken stand-alone generated variant.
    """
    old = SOURCE_ROOT + "variant/"
    new = f"gen/projects/{project}/variants/{VARIANT}/rtl/"
    expected = {
        "rtl/soc_top.sv": ("flash.hex", "bootrom.hex"),
        "rtl/full_chip_tb.sv": ("compute0.hex", "compute1.hex"),
        "rtl/manifest.json": ("flash.hex",),
    }
    result = source
    if relative in expected:
        for image in expected[relative]:
            previous = (old + image).encode("ascii")
            if result.count(previous) != 1:
                raise CombinedGenerationError(
                    "selected generated source lacks unique image reference: " +
                    relative + ": " + image)
            result = result.replace(previous, (new + image).encode("ascii"))
    if b".tools/regression/" in result:
        raise CombinedGenerationError(
            "generated variant still references temporary regression paths: " + relative)
    return result


def portable_filelist(root: Path, original: dict, remapped: dict,
                      project: str) -> bytes:
    """Retain the compiler's original ordered 312 sources and pinned include paths.

    Normalize only checkout-absolute paths and replace the verified generated
    source paths. Never silently use a different Bender source or module order.
    The returned -f file is resolved relative to the repository working dir.
    """
    filelist = root / SOURCE_ROOT / "sources.f"
    if not filelist.is_file() or filelist.is_symlink():
        raise CombinedGenerationError("original selected compiler filelist missing")
    raw = filelist.read_bytes()
    if digest(raw) != original["filelist_sha256"]:
        raise CombinedGenerationError("original selected compiler filelist digest changed")
    out = []
    observed = []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("+define+"):
            out.append(line)
            continue
        is_include = line.startswith("+incdir+")
        path = line[len("+incdir+"):] if is_include else line
        if not path or not Path(path).is_absolute():
            raise CombinedGenerationError("unexpected selected compiler filelist syntax")
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
            raise CombinedGenerationError("foreign or symlink compiler source/include")
        if is_include and not candidate.is_dir():
            raise CombinedGenerationError("selected include directory missing")
        if not is_include and not candidate.is_file():
            raise CombinedGenerationError("selected compiler file missing")
        relative = candidate.resolve().relative_to(root).as_posix()
        if is_include:
            out.append("+incdir+" + relative)
        else:
            if relative not in original["source_sha256"]:
                raise CombinedGenerationError("unattested source selected: " + relative)
            observed.append(relative)
            if relative in remapped:
                relative = f"gen/projects/{project}/variants/{VARIANT}/" + remapped[relative]
            out.append(relative)
    if len(observed) != 312 or set(observed) != set(original["source_sha256"]):
        raise CombinedGenerationError("portable compiler source set/ordering changed")
    return ("\n".join(out) + "\n").encode("utf-8")


def emit(root: Path, folder: Path, *, runner=None) -> dict:
    """Regenerate and verify selected sources, then export only actual bytes."""
    root = root.resolve()
    cfg = yaml.safe_load((root / "config/soc.yaml").read_text())
    project = cfg["name"]
    if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", project):
        raise CombinedGenerationError("invalid canonical SoC project name")
    regression = yaml.safe_load((root / "config/regression.yaml").read_text())
    definition = regression["tests"][PROFILE]
    if (definition.get("firmware_mode") != "ethernet_ddr_pcie"
            or definition.get("top") != "full_chip_tb"):
        raise CombinedGenerationError("combined RTL selection changed; source review required")
    command = [sys.executable, str(root / "tools/regress.py"),
               PROFILE, "--stage", "files", "--fail-fast"]
    if runner is None:
        def runner(argv, cwd):
            return subprocess.run(argv, cwd=cwd, text=True,
                                  capture_output=True, timeout=1800, check=False)
    result = runner(command, root)
    if result.returncode:
        raise CombinedGenerationError(
            "actual combined source generation failed: " + str(result.stderr)[-1800:])
    original = verify_selected_archive(root, PROFILE, definition)
    generated = original["generated_sha256"]
    sources = original["source_sha256"]
    if original.get("source_count") != 312 or len(sources) != 312:
        raise CombinedGenerationError("selected combined source count changed; review source contract")
    top = SOURCE_ROOT + "variant/soc_top.sv"
    if top not in generated or generated[top] != sources.get(top):
        raise CombinedGenerationError("original selected combined RTL top not in compiler closure")
    folder.mkdir(parents=True, exist_ok=True)
    copies = {}
    mapped = {}
    for name, sha in sorted(generated.items()):
        if not name.startswith(SOURCE_ROOT):
            raise CombinedGenerationError("unexpected generated source outside selected variant")
        suffix = name[len(SOURCE_ROOT):]
        if suffix.startswith("variant/"):
            rel = "rtl/" + suffix[len("variant/"):]
        elif suffix.startswith("ddr_noc/"):
            rel = suffix
        else:
            raise CombinedGenerationError("unreviewed generated source category: " + suffix)
        raw = source_bytes(root, name, sha)
        if suffix.startswith("variant/"):
            raw = portable_image_paths(raw, project, rel)
        output = folder / rel
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        copies[rel] = {"source": name, "selected_sha256": sha,
                       "generated_sha256": digest(raw)}
        mapped[name] = rel
    for name, sha in sorted(sources.items()):
        if not name.startswith(DDR_ROOT):
            continue
        rel = "controller/gateware/" + name[len(DDR_ROOT):]
        raw = source_bytes(root, name, sha)
        output = folder / rel
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        copies[rel] = {"source": name, "selected_sha256": sha,
                       "generated_sha256": digest(raw)}
        mapped[name] = rel
    for mandatory in ("rtl/soc_top.sv", "rtl/flash.hex", "rtl/bootrom.hex",
                      "controller/gateware/soc_ddr4_sim.v"):
        if mandatory not in copies:
            raise CombinedGenerationError("missing mandatory generated combined source: " + mandatory)
    compiler_sources = portable_filelist(root, original, mapped, project)
    (folder / "compiler").mkdir(parents=True, exist_ok=True)
    (folder / "compiler/sources.f").write_bytes(compiler_sources)
    # Full 312-input provenance from the original selected compiler remains
    # explicit, including external pinned RTL. We do NOT claim the remapped
    # generated output has been independently elaborated yet.
    metadata = {
        "schema_version": 1, "project": project, "variant": VARIANT,
        "source_profile": PROFILE,
        "selected_compiler_input_sha256": original["compiler_input_sha256"],
        "selected_filelist_sha256": original["filelist_sha256"],
        "portable_filelist_sha256": digest(compiler_sources),
        "portable_filelist": "compiler/sources.f",
        "source_config_sha256": original.get("config_sha256"),
        "selection_sha256": original.get("definition_sha256"),
        "include_headers_sha256": original.get("include_headers_sha256"),
        "network_filelists": original.get("network_filelists"),
        "defines": original.get("defines"),
        "includes": original.get("includes"),
        "compiler_args": original.get("args"),
        "source_count": len(sources),
        "selected_source_sha256": dict(sorted(sources.items())),
        "portable_source_map": mapped,
        "files": copies,
        "evidence": "generator_owned_selected_source_review_not_elaborated_or_simulated",
    }
    (folder / "manifest.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    (folder / ".generated-combined").write_text("combined-source-v1\n")
    return metadata


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--check", action="store_true")
    args = cli.parse_args()
    root = args.root.resolve()
    destination = root / "gen/projects" / yaml.safe_load(
        (root / "config/soc.yaml").read_text())["name"] / "variants" / VARIANT
    if destination.is_symlink():
        raise CombinedGenerationError("refusing symlink generated variant")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".combined-", dir=destination.parent) as tmp:
        fresh = Path(tmp) / "generated"
        emit(root, fresh)
        if args.check:
            actual = tree(destination) if destination.is_dir() else {}
            expected = tree(fresh)
            different = [key for key in sorted(set(actual) | set(expected))
                         if actual.get(key) != expected.get(key)]
            if different:
                raise CombinedGenerationError(
                    "generator-owned combined RTL drift (first paths): " +
                    ", ".join(different[:20]))
            print("PASS generator-owned combined variant exact selected source replay")
            return 0
        if destination.exists():
            if not (destination / ".generated-combined").is_file():
                raise CombinedGenerationError("refusing to replace unowned generated variant")
            backup = destination.with_name(destination.name + ".previous-combined")
            if backup.exists():
                raise CombinedGenerationError("previous combined generation backup must be removed first")
            destination.rename(backup)
            try:
                fresh.rename(destination)
            except Exception:
                backup.rename(destination)
                raise
            shutil.rmtree(backup)
        else:
            fresh.rename(destination)
    print("GENERATED real combined RTL at " + str(destination.relative_to(root)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CombinedGenerationError, OSError, ValueError) as exc:
        print("Combined RTL generation error:", exc, file=sys.stderr)
        raise SystemExit(1)
