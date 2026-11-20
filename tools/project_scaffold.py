#!/usr/bin/env python3
"""Safely register another independent source-only chip using the shared SoC schema.

This copies a supported hardware *starting point*, not qualified RTL or tests.
Edit the new YAML to describe the actual chip before requesting compilation.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

import yaml

import floonoc_gen
import project_catalog
import socgen


ROOT = Path(__file__).resolve().parents[1]


def create_project(project_id: str, from_project: str, title: str, subtitle: str,
                   *, root: Path = ROOT) -> Path:
    root = root.resolve()
    if not isinstance(project_id, str) or not project_catalog.IDENT.fullmatch(project_id):
        raise ValueError("invalid project identity")
    if not isinstance(title, str) or not title.strip() or not isinstance(subtitle, str) or not subtitle.strip():
        raise ValueError("new project needs a title and subtitle")
    existing = {entry["id"]: entry for entry in project_catalog.projects(root)}
    if from_project not in existing:
        raise ValueError("unknown source project")
    if project_id in existing:
        raise ValueError("project identity already exists")

    source = existing[from_project]
    parent = root / "config" / "projects" / project_id
    target = parent / "soc.yaml"
    if parent.exists() or parent.is_symlink():
        raise ValueError("new project directory already exists")

    soc = yaml.safe_load((root / source["config"]).read_text())
    soc["name"] = project_id
    socgen.validate(soc)
    contracts_path = root / "config" / "interface_contracts.yaml"
    if not contracts_path.is_file():
        contracts_path = ROOT / "config" / "interface_contracts.yaml"
    floonoc_gen.profiles(soc, yaml.safe_load(contracts_path.read_text()))

    catalog_path = root / project_catalog.REGISTRY
    original = catalog_path.read_text()
    entry = {
        "id": project_id, "title": title.strip(), "subtitle": subtitle.strip(),
        "config": target.relative_to(root).as_posix(),
        "qualification": "source_contract_only",
    }
    # Insert inside the authors' existing YAML sequence, not at a fixed
    # indentation or after the entire file. Preserve comments and existing keys.
    sequence = next(node for key, node in yaml.compose(original).value
                    if key.value == "projects")
    if sequence.flow_style:
        offset = sequence.value[-1].end_mark.index
        item = yaml.safe_dump(entry, sort_keys=False, allow_unicode=True,
                              default_flow_style=True).strip()
        catalog_text = original[:offset] + ", " + item + original[offset:]
    else:
        offset = sequence.end_mark.index
        indent = " " * sequence.start_mark.column
        item = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)
        prefix = original[:offset]
        if not prefix.endswith("\n"):
            prefix += "\n"
        catalog_text = prefix + "".join(indent + line for line in item.splitlines(True)) + original[offset:]
    expected = yaml.safe_load(original)
    expected["projects"].append(entry)
    if yaml.safe_load(catalog_text) != expected:
        raise ValueError("project catalog append failed validation")

    stage = None
    replaced = False
    parent.mkdir(parents=False)
    try:
        target.write_text(yaml.safe_dump(soc, sort_keys=False))
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=catalog_path.parent,
                prefix=".catalog-", suffix=".yaml", delete=False) as handle:
            stage = Path(handle.name)
            handle.write(catalog_text)
        os.replace(stage, catalog_path)
        replaced = True
        # Validate the complete, real catalog rather than trusting a copy.
        project_catalog.projects(root)
    except Exception:
        if replaced:
            catalog_path.write_text(original)
        if target.exists():
            target.unlink()
        parent.rmdir()
        raise
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)
    return target


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--id", required=True, help="unique lowercase project ID")
    p.add_argument("--from-project", required=True, help="supported source configuration to start from")
    p.add_argument("--title", required=True)
    p.add_argument("--subtitle", required=True)
    p.add_argument("--root", type=Path, default=ROOT)
    args = p.parse_args()
    path = create_project(args.id, args.from_project, args.title, args.subtitle,
                          root=args.root)
    print(f"Created {path}: SOURCE CONTRACT ONLY; edit YAML and qualify RTL before claiming compile/PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
