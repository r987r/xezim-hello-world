#!/usr/bin/env python3
"""Profile-aware, protocol-neutral design graph for the SoC 2D explorer.

The generator's topology is declared connectivity, NOT an elaborated proof.
Actor overlays describe each test scope, not necessarily current simulation
activity. Optional external reports have their own evidence level.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text())


def safe_source(root: Path, value: str) -> Path:
    """Resolve paths controlled by the repository's own regression YAML."""
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"source path escapes repository: {value}")
    if not path.is_file():
        raise ValueError(f"missing source: {path}")
    return path


def link_id(link: dict) -> str:
    """Stable across additions and ordering changes; never use noc_link_0001."""
    key = [link["from"]["instance"], link["from"].get("port", ""),
           link["to"]["instance"], link["to"].get("port", ""), link.get("name", "")]
    return "link:" + hashlib.sha256(
        json.dumps(key, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()[:20]


def catalog(root: Path = ROOT, *, verification_reports: dict[str, Path] | None = None) -> dict:
    """Convert arbitrary topology instances and regression profiles, without IP-type logic."""
    topology = read_json(root / "gen/diagrams/noc-topology.json")
    if topology.get("schema_version") != 1:
        raise ValueError("unsupported topology schema")
    instances = topology["instances"]
    connections = topology["connections"]
    groups = topology["groups"]
    names = [item["name"] for item in instances]
    if len(set(names)) != len(names):
        raise ValueError("duplicate topology instance")
    name_set = set(names)
    memberships: dict[str, list[str]] = {name: [] for name in names}
    for group in groups:
        for member in group["instances"]:
            if member not in name_set:
                raise ValueError(f"{group['name']}: group contains unknown instance {member}")
            memberships[member].append(group["name"])

    # Enrich generated topology with *current* SoC target backend contracts.
    # Do not mutate tracked generated JSON; next page build reflects new
    # config/backend integration automatically. Controller names in config
    # identify intended IP, not proof a physical controller was instantiated.
    soc_path = root / "config/soc.yaml"
    soc = yaml.safe_load(soc_path.read_text()) if soc_path.is_file() else {"memory_targets": []}
    target_specs = {t["name"]: t for t in soc.get("memory_targets", [])}
    if len(target_specs) != len(soc.get("memory_targets", [])):
        raise ValueError("duplicate configured memory target")
    if set(target_specs) - name_set:
        raise ValueError(f"configured memory target absent from generated topology: {sorted(set(target_specs) - name_set)}")
    nodes = []
    for item in sorted(instances, key=lambda node: node["name"]):
        info = dict(item.get("info") or {})
        target = target_specs.get(item["name"])
        if target is not None:
            backend = (target.get("simulation") or {}).get("backend")
            info["memory_integration"] = {
                "kind": target["kind"],
                "controller_profile": target.get("controller"),
                "soc_backend": backend,
                "integration": ("behavioral_axi_ram" if backend == "axi_ram"
                                else "configured_other_backend"),
                "evidence": "soc_yaml_and_generated_rtl_contract",
            }
        # Never carry legacy 3D x/y/z positions into the new view.
        nodes.append({"id": item["name"], "module": item["module"],
                      "kind": info.get("kind", "rtl_or_boundary"),
                      "groups": memberships[item["name"]],
                      "info": info})

    edges = []
    seen = set()
    for link in connections:
        source = link["from"]["instance"]
        target = link["to"]["instance"]
        if source not in name_set or target not in name_set:
            raise ValueError(f"unknown connectivity endpoint {source} -> {target}")
        key = link_id(link)
        if key in seen:
            raise ValueError(f"duplicate connectivity link {source} -> {target}")
        seen.add(key)
        edges.append({"id": key, "from": link["from"], "to": link["to"],
                      "name": link.get("name", ""), "type": link.get("type", ""),
                      "status": link.get("status", "unspecified"),
                      "signals": link.get("signals", [])})
    edges.sort(key=lambda edge: edge["id"])

    regression = yaml.safe_load((root / "config/regression.yaml").read_text())
    if regression.get("schema_version") != 1:
        raise ValueError("unsupported regression schema")
    tests = regression["tests"]
    verification_reports = verification_reports or {}
    if set(verification_reports) - set(tests):
        raise ValueError("external verification report references an unknown test profile")

    profiles = {}
    for name, test in sorted(tests.items()):
        report = test.get("report", {})
        axi = report.get("axi", {})
        actors_file = axi.get("actors")
        actors = {}
        actor_catalog_status = "not_declared"
        if actors_file:
            # Some positive regression variants (e.g. chip-cpu-dma) generate
            # their actor manifest only when that particular test executes.
            # Keep the profile visible without falsely claiming its runtime
            # actor roles; missing checked-in manifests remain an error.
            candidate = (root / actors_file).resolve()
            generated_runtime = (
                candidate.is_relative_to((root / ".tools/regression").resolve())
                and candidate.is_relative_to(root.resolve())
            )
            if not candidate.is_file() and generated_runtime:
                actor_catalog_status = "runtime_generated_not_available"
            else:
                data = read_json(safe_source(root, actors_file))
                if not isinstance(data.get("axi_actors"), dict):
                    raise ValueError(f"{name}: actor manifest lacks axi_actors")
                actors = data["axi_actors"]
                missing = set(actors) - name_set
                if missing:
                    raise ValueError(f"{name}: actors are not in generated topology: {sorted(missing)}")
                actor_catalog_status = "loaded_checked_in" if not generated_runtime else "loaded_runtime_generated"
        monitors = []
        monitor_catalog_status = "not_declared"
        if axi.get("catalog"):
            candidate = (root / axi["catalog"]).resolve()
            generated_runtime = (candidate.is_relative_to((root / ".tools/regression").resolve())
                                 and candidate.is_relative_to(root.resolve()))
            if not candidate.is_file() and generated_runtime and test.get("opt_in") is True:
                # The DDR real-controller variant regenerates this catalog only
                # while its selected simulation runs. Main Pages must not
                # pretend it exists or require a slow DDR4 build.
                monitor_catalog_status = "opt_in_runtime_generated_not_available"
            else:
                data = read_json(safe_source(root, axi["catalog"]))
                if not isinstance(data.get("monitors"), list):
                    raise ValueError(f"{name}: monitor catalog lacks monitors")
                monitor_catalog_status = ("loaded_runtime_generated"
                                          if generated_runtime else "loaded_checked_in")
                for monitor in data["monitors"]:
                    if any(endpoint in actors for endpoint in monitor.get("endpoints", [])):
                        monitors.append({"id": monitor["id"], "role": monitor.get("role"),
                                         "endpoints": monitor.get("endpoints", []),
                                         "plane": monitor.get("plane"),
                                         "data_width": monitor.get("data_width")})
        item = {"top": test.get("top"), "engine": test["engine"],
                "test_module": test.get("module"), "test_dir": test.get("test_dir"),
                "context": report.get("context", ""),
                "actors": actors, "monitors": monitors,
                "actor_catalog_path": actors_file,
                "actor_catalog_status": actor_catalog_status,
                "monitor_catalog_status": monitor_catalog_status,
                "evidence": "declared_test_profile",
                "verification_observability": ("declared_axi_monitors" if monitors else
                                               "no_axi_monitor_catalog")}
        if name in verification_reports:
            payload = read_json(verification_reports[name])
            if not isinstance(payload, (dict, list)):
                raise ValueError(f"{name}: external parser report must be JSON object or list")
            item["static_verification"] = {
                "producer": "hdl-kgraph", "evidence": "syntactic_inference_not_runtime",
                "report": payload}
        profiles[name] = item

    return {"schema_version": 1, "source": {
                "topology": "gen/diagrams/noc-topology.json",
                "regression": "config/regression.yaml",
                "structural_evidence": "generated_declared_not_slang_verified",
                "verification_evidence": "profile_declarations_and_optional_static_parser"},
            "nodes": nodes, "edges": edges,
            "groups": [{"name": g["name"], "instances": sorted(g["instances"]),
                        "info": g.get("info", {})} for g in groups],
            "profiles": profiles}


def changed_items(before: dict, after: dict) -> dict:
    b, a = set(before), set(after)
    return {"added": sorted(a - b), "removed": sorted(b - a),
            "changed": sorted(key for key in a & b if before[key] != after[key])}


def difference(before: dict, after: dict) -> dict:
    """Compare stable identities; preserve real protocol and role changes."""
    if before.get("schema_version") != 1 or after.get("schema_version") != 1:
        raise ValueError("incompatible graph schemas")
    result = {}
    for label, field in (("nodes", "id"), ("edges", "id")):
        a = {item[field]: item for item in before[label]}
        b = {item[field]: item for item in after[label]}
        result[label] = changed_items(a, b)
    result["profiles"] = changed_items(before["profiles"], after["profiles"])
    result["actor_changes"] = {}
    for profile in sorted(set(before["profiles"]) & set(after["profiles"])):
        a = before["profiles"][profile]["actors"]
        b = after["profiles"][profile]["actors"]
        change = changed_items(a, b)
        if any(change.values()):
            result["actor_changes"][profile] = change
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diff", type=Path, help="existing prior graph to compare")
    parser.add_argument("--verification-report", action="append", default=[], metavar="PROFILE=JSON",
                        help="import hdl-kgraph query uvm --json output; do not treat as runtime truth")
    args = parser.parse_args()
    reports = {}
    for pair in args.verification_report:
        if "=" not in pair:
            parser.error("--verification-report expects PROFILE=JSON")
        name, path = pair.split("=", 1)
        if not name or name in reports:
            parser.error("verification report profile must be unique and nonempty")
        reports[name] = Path(path)
    graph = catalog(args.root.resolve(), verification_reports=reports)
    data = difference(read_json(args.diff), graph) if args.diff else graph
    result = json.dumps(data, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
