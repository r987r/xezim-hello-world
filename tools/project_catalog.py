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
from floonoc_gen import profiles as floonoc_profiles

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "config/projects/catalog.yaml"
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
QUALIFICATIONS = {"generated_default", "source_contract_only", "ci_generated_compiled"}


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
                "generated_source", "qualification", "architecture_explorer"}:
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
        # Use the SAME FlooGen configuration builder as the actual RTL
        # generation path. These are source-qualified topology contracts,
        # not a claim that source-selected hardware has been elaborated.
        contracts_path = root / "config/interface_contracts.yaml"
        # Isolated catalog test fixtures intentionally supply only project
        # configs; they exercise the same checked-in shared contract.
        if not contracts_path.is_file():
            contracts_path = ROOT / "config/interface_contracts.yaml"
        contracts = yaml.safe_load(contracts_path.read_text())
        noc_profiles = floonoc_profiles(soc, contracts)
        noc_descriptions = {}
        for noc_name, noc in sorted(noc_profiles.items()):
            profile_cfg = noc["config"]
            noc_descriptions[noc_name] = {
                "name": noc_name, "plane": noc["plane"], "path": noc["path"],
                "family": noc["family"],
                "routers": profile_cfg["routers"],
                "connections": profile_cfg["connections"],
                "endpoints": profile_cfg["endpoints"],
                "routing": profile_cfg["routing"],
                "evidence": "generator_profile_not_elaborated_or_tested",
            }
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
        explorer_rel = item.get("architecture_explorer")
        if explorer_rel is not None:
            if item["qualification"] != "generated_default":
                raise ValueError("a source-only or CI-artifact project cannot borrow a published RTL explorer")
            if (not isinstance(explorer_rel, str) or not explorer_rel.endswith(".html")
                    or Path(explorer_rel).is_absolute()
                    or any(part in ("..", ".") for part in Path(explorer_rel).parts)):
                raise ValueError("invalid project architecture explorer path")
            if any(p.get("architecture_explorer") == explorer_rel for p in result):
                raise ValueError("architecture explorer belongs to more than one project")
        result.append({
            "id": project_id, "title": item["title"], "subtitle": item["subtitle"],
            "config": config_rel.as_posix(), "config_sha256":
                hashlib.sha256(config.read_bytes()).hexdigest(),
            "qualification": item["qualification"],
            "generated_source": generated,
            "architecture_explorer": explorer_rel,
            "subsystems": [s["name"] for s in soc["subsystems"]],
            "compute": [s["name"] for s in soc["subsystems"] if s["type"] == "compute"],
            "memory_targets": [t["name"] for t in soc["memory_targets"]],
            "data_links": meta.get("direct_data_links", []),
            "layout": soc.get("layout"),
            # Explicit per-project source hierarchy for the reusable viewer.
            # These are configuration declarations, NOT parsed RTL instances.
            "design": {
                "subsystems": soc["subsystems"],
                "subsystem_types": soc.get("subsystem_types", {}),
                "fabrics": soc.get("fabrics", {}),
                "networks": soc.get("networks", {}),
                "memory_targets": soc["memory_targets"],
                "buses": soc.get("buses", {}),
                "boot": soc.get("boot", {}),
                "noc_profiles": noc_descriptions,
            },
            "address_map": soc["address_map"],
            "source_evidence": ("tracked_generated_source_not_simulation" if generated else
                                "selected_compiled_CI_artifact_not_simulation"
                                if item["qualification"] == "ci_generated_compiled" else
                                "configured_only_no_generated_RTL"),
        })
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path)
    p.add_argument("--matrix", action="store_true",
                   help="GitHub Actions matrix driven solely by project catalog")
    p.add_argument("--ids", action="store_true", help="print project IDs, one per line")
    p.add_argument("--compiled-only", action="store_true",
                   help="select projects claiming compiled RTL, omitting config-only projects")
    args = p.parse_args()
    if args.matrix and args.ids:
        p.error("--matrix and --ids are mutually exclusive")
    selected = projects(args.root)
    if args.compiled_only:
        selected = [p for p in selected
                    if p["qualification"] in ("generated_default", "ci_generated_compiled")]
    if args.matrix:
        # Must remain one compact line for GITHUB_OUTPUT; no 2-project list.
        rendered = json.dumps({"project": [p["id"] for p in selected]},
                              separators=(",", ":"))
    elif args.ids:
        rendered = "\n".join(p["id"] for p in selected)
    else:
        rendered = json.dumps({"schema_version": 1, "projects": selected},
                              indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
