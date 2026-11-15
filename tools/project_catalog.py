"""Single project registry for Pages, tooling, and future project-aware DV.

No project-specific verification engine, generated RTL shortcut, or duplicate
test-run store. Source-only projects have zero qualified hardware results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

from socgen import validate as validate_soc

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "config/projects/catalog.yaml"
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
QUALIFICATIONS = {"generated_default", "source_contract_only"}


def projects(root: Path = ROOT) -> list[dict]:
    root = root.resolve()
    registry_path = root / REGISTRY
    registry = yaml.safe_load(registry_path.read_text())
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise ValueError("invalid project catalog schema")
    listed = registry.get("projects")
    if not isinstance(listed, list) or not listed:
        raise ValueError("project catalog must contain at least one project")
    result, names, configs = [], set(), set()
    for item in listed:
        if not isinstance(item, dict) or set(item) - {
                "id", "title", "subtitle", "config",
                "generated_source", "qualification"}:
            raise ValueError("unknown project catalog keys")
        project_id = item.get("id")
        if not isinstance(project_id, str) or not IDENT.fullmatch(project_id):
            raise ValueError("invalid project identity")
        if project_id in names:
            raise ValueError("duplicate project identity")
        names.add(project_id)
        if any(not isinstance(item.get(k), str) or not item[k]
               for k in ("title", "subtitle", "config", "qualification")):
            raise ValueError("missing project metadata")
        if item["qualification"] not in QUALIFICATIONS:
            raise ValueError("unknown project qualification")
        config_rel = Path(item["config"])
        config = (root / config_rel).resolve()
        if (config.is_symlink() or not config.is_relative_to(root)
                or config_rel.is_absolute() or not config.is_file()
                or config_rel.suffix != ".yaml"):
            raise ValueError("unsafe or missing project SoC config")
        if config in configs:
            raise ValueError("projects must have independent authored configurations")
        configs.add(config)
        soc = yaml.safe_load(config.read_text())
        if soc.get("name") != project_id:
            raise ValueError("project identity differs from SoC config name")
        meta = validate_soc(soc)
        generated = item.get("generated_source")
        if item["qualification"] == "generated_default":
            if not isinstance(generated, str):
                raise ValueError("generated project requires source path")
            resolved = (root / generated).resolve()
            if (not resolved.is_relative_to(root) or not resolved.is_file()
                    or resolved.is_symlink()):
                raise ValueError("missing actual generated project RTL")
        elif generated is not None:
            raise ValueError("source-only project cannot claim generated hardware")
        result.append({
            "id": project_id, "title": item["title"], "subtitle": item["subtitle"],
            "config": config_rel.as_posix(), "config_sha256":
                hashlib.sha256(config.read_bytes()).hexdigest(),
            "qualification": item["qualification"],
            "generated_source": generated,
            "subsystems": [s["name"] for s in soc["subsystems"]],
            "compute": [s["name"] for s in soc["subsystems"] if s["type"] == "compute"],
            "memory_targets": [t["name"] for t in soc["memory_targets"]],
            "data_links": meta.get("direct_data_links", []),
            "layout": soc.get("layout"),
            "address_map": soc["address_map"],
            "source_evidence": ("generated_default_source_only_not_simulation"
                                if generated else "configured_only_no_generated_RTL"),
        })
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    result = {"schema_version": 1, "projects": projects(args.root)}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
