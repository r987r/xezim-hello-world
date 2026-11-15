#!/usr/bin/env python3
"""Project-isolated boot, memory and optional full-chip selected RTL.

Uses shared emitters and pinned IP without copying the verification engine.
--full-chip emits actual selected NoC/SoC RTL; compilation and functional
qualification are separate explicit gates.
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


def generate_one(root: Path, project: dict, output: Path, *,
                 full_chip: bool = False, image_prefix: str | None = None) -> dict:
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
    if full_chip:
        import floonoc_gen
        import full_chip_gen
        import supernoc_gen
        if image_prefix is None:
            raise ValueError("full-chip selected output requires final image path")
        knobs = yaml.safe_load(
            (root / "config/interface_contracts.yaml").read_text())
        noc_root = output / "noc/floonoc"
        floonoc_gen.generate_all(soc, knobs, noc_root)
        noc_manifest = supernoc_gen.emit(
            soc, noc_root, output / "supernoc/supernoc_tb.sv")
        full_chip_gen.emit(
            soc, noc_manifest, noc_root, output / "chip",
            image_prefix=image_prefix)
    # Hardware generation alone cannot imply a simulation or traffic PASS.
    record = {
        "schema_version": 1,
        "project_id": project["id"],
        "source_config": project["config"],
        "source_config_sha256": project["config_sha256"],
        "artifacts": {"memory_unit": "memory/memory_tb.sv",
                      "boot_firmware": "boot/bootrom.hex"},
        "generated_full_chip": full_chip,
        "routed_axi_test_passed": False,
        "evidence": ("source_selected_chip_RTL_not_elaborated_or_simulated"
                     if full_chip else
                     "source_selected_unit_generation_not_simulation"),
        "files": tree_digest(output),
    }
    (output / "manifest.json").write_text(
        json.dumps(record, sort_keys=True, indent=2) + "\n")
    return record


def build(project_id: str, *, root: Path = ROOT,
          output_root: Path | None = None, check: bool = False,
          full_chip: bool = False) -> dict:
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
        # Generated SV references its FINAL run-specific boot image path,
        # never the temporary generation staging root.
        prefix = (dest / "chip").relative_to(root).as_posix() if (
            full_chip and dest.is_relative_to(root)) else None
        if full_chip and prefix is None:
            raise ValueError("full-chip output must reside inside checkout")
        record = generate_one(root, known[project_id], generated,
                              full_chip=full_chip, image_prefix=prefix)
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
    parser.add_argument("--full-chip", action="store_true",
                        help="emit selected FlooNoC and SoC RTL (no compile or PASS)")
    args = parser.parse_args()
    record = build(args.project, root=args.root, output_root=args.out,
                   check=args.check, full_chip=args.full_chip)
    print("PASS project source-selected generation "
          + record["project_id"] + " (no compile, elaboration or traffic PASS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
