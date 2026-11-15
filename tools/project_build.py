#!/usr/bin/env python3
"""Project-isolated boot/memory RTL generation using the shared SoC emitters.

No shadow copies of RTL producers, test framework, or source configuration.
This command generates the independently supported *unit* hardware slices;
it never claims full-chip direct-link RTL or a passing simulation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import yaml

import bootgen
import project_catalog
import socgen

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = ".project-build-owned"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(folder: Path) -> dict[str, str]:
    return {
        f.relative_to(folder).as_posix(): sha(f.read_bytes())
        for f in sorted(folder.rglob("*")) if f.is_file() and f.name != "manifest.json"
    }


def generate_one(root: Path, project: dict, output: Path) -> dict:
    """Only a project's own selected source enters the common emitters."""
    config = root / project["config"]
    if sha(config.read_bytes()) != project["config_sha256"]:
        raise ValueError("project config SHA changed since catalog validation")
    soc = yaml.safe_load(config.read_text())
    if soc.get("name") != project["id"]:
        raise ValueError("source does not belong to requested project")
    output.mkdir(parents=True, exist_ok=True)
    (output / SENTINEL).write_text(project["id"] + "\n")
    socgen.run(config, output / "memory")
    bootgen.emit(soc, output / "boot")
    # No full-chip RTL entry in the manifest until it is actually emitted
    # and verified. Memory-only and boot firmware are separately labelled.
    record = {
        "schema_version": 1,
        "project_id": project["id"],
        "source_config": project["config"],
        "source_config_sha256": project["config_sha256"],
        "artifacts": {"memory_unit": "memory/memory_tb.sv",
                      "boot_firmware": "boot/bootrom.hex"},
        "generated_full_chip": False,
        "routed_axi_test_passed": False,
        "evidence": "source_selected_unit_generation_not_simulation",
        "files": tree_digest(output),
    }
    (output / "manifest.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n")
    return record


def build(project_id: str, *, root: Path = ROOT,
          output_root: Path | None = None, check: bool = False) -> dict:
    root = root.resolve()
    known = {p["id"]: p for p in project_catalog.projects(root)}
    if project_id not in known:
        raise ValueError("unknown project id")
    dest_root = (output_root or root / ".tools/projects").resolve()
    dest = dest_root / project_id
    if not dest.is_relative_to(dest_root):
        raise ValueError("project build escaped output root")
    if dest.exists():
        if dest.is_symlink() or not (dest / SENTINEL).is_file():
            raise ValueError("refusing to delete non-owned project output")
        if (dest / SENTINEL).read_text() != project_id + "\n":
            raise ValueError("project build output belongs to another project")
    with tempfile.TemporaryDirectory(prefix="soc-project-") as temp:
        generated = Path(temp) / project_id
        record = generate_one(root, known[project_id], generated)
        if check:
            if not dest.is_dir() or {
                    f.relative_to(generated).as_posix(): f.read_bytes()
                    for f in generated.rglob("*") if f.is_file()
            } != {
                    f.relative_to(dest).as_posix(): f.read_bytes()
                    for f in dest.rglob("*") if f.is_file()
            }:
                raise ValueError("selected project build differs from generated sources")
        else:
            if dest.exists():
                shutil.rmtree(dest)
            dest_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(generated, dest)
        return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=ROOT / ".tools/projects")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = build(args.project, root=args.root, output_root=args.out,
                   check=args.check)
    print("PASS project source-selected unit generation "
          + record["project_id"] + " (not full-chip RTL)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
