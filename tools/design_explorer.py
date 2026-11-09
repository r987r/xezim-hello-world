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

    return {"schema_version": 1, "configuration": normalized_configuration(soc), "source": {
                "topology": "gen/diagrams/noc-topology.json",
                "regression": "config/regression.yaml",
                "structural_evidence": "generated_declared_not_slang_verified",
                "verification_evidence": "profile_declarations_and_optional_static_parser"},
            "nodes": nodes, "edges": edges,
            "groups": [{"name": g["name"], "instances": sorted(g["instances"]),
                        "info": g.get("info", {})} for g in groups],
            "profiles": profiles}


def normalized_configuration(value: dict) -> dict:
    """Normalize named SoC objects without silently dropping future keys."""
    if not isinstance(value, dict):
        raise ValueError("invalid declared SoC configuration")
    value = json.loads(json.dumps(value, sort_keys=True))
    for field in ("subsystems", "memory_targets"):
        items = value.get(field)
        if isinstance(items, list):
            names = [v["name"] for v in items]
            if len(set(names)) != len(names):
                raise ValueError("duplicate declared " + field)
            value[field] = sorted(items, key=lambda v: v["name"])
    for plane, items in value.get("address_map", {}).items():
        if not isinstance(items, list):
            raise ValueError("invalid address map plane " + plane)
        names = [v["name"] for v in items]
        if len(set(names)) != len(names):
            raise ValueError("duplicate address map name")
        value["address_map"][plane] = sorted(items, key=lambda v: v["name"])
    for item in value.get("networks", {}).values():
        if isinstance(item, dict):
            if isinstance(item.get("outputs"), list):
                item["outputs"] = sorted(item["outputs"], key=lambda v: v["name"])
            if isinstance(item.get("reachable_subsystems"), list):
                item["reachable_subsystems"] = sorted(item["reachable_subsystems"])
    return value


def _index_unique(items: list, field: str) -> dict:
    result = {}
    for item in items:
        name = item[field]
        if name in result:
            raise ValueError("duplicate semantic identity " + str(name))
        result[name] = item
    return result


def _route_key(item: dict) -> str:
    return json.dumps([item["from"]["instance"], item["from"].get("port", ""),
                       item["to"]["instance"], item["to"].get("port", ""),
                       item.get("type", "")], separators=(",", ":"))


def _delta(old: dict, new: dict) -> dict:
    return {key: {"before": old.get(key), "after": new.get(key)}
            for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)}


def _compare_maps(old: dict, new: dict) -> dict:
    common = sorted(set(old) & set(new))
    return {"added": sorted(set(new) - set(old)),
            "removed": sorted(set(old) - set(new)),
            "changed": {key: _delta(old[key], new[key]) for key in common
                        if old[key] != new[key]}}


def semantic_difference(before: dict, after: dict) -> dict:
    """Review source-declared nodes, physical links and buses, not RTL proof."""
    if before.get("schema_version") != 1 or after.get("schema_version") != 1:
        raise ValueError("unsupported semantic graph schema")
    old_edges = _index_unique([
        {"semantic_id": _route_key(item), **item} for item in before["edges"]
    ], "semantic_id")
    new_edges = _index_unique([
        {"semantic_id": _route_key(item), **item} for item in after["edges"]
    ], "semantic_id")
    old_config, new_config = (before.get("configuration") or {},
                              after.get("configuration") or {})
    if not isinstance(old_config, dict) or not isinstance(new_config, dict):
        raise ValueError("invalid declared configuration")
    return {
        "schema_version": 1,
        "evidence": "source_declared_only_not_elaborated_or_observed",
        "instances": _compare_maps(_index_unique(before["nodes"], "id"),
                                   _index_unique(after["nodes"], "id")),
        "routes": _compare_maps(old_edges, new_edges),
        "groups": _compare_maps(_index_unique(before["groups"], "name"),
                                _index_unique(after["groups"], "name")),
        "test_profiles": _compare_maps(before["profiles"], after["profiles"]),
        "soc_configuration": _delta(old_config, new_config),
    }


def markdown_diff(diff: dict) -> str:
    """Readable compact view of the same source-only JSON semantic changes."""
    view = diff["semantic"]
    lines = ["# SoC architecture diff (source declared)", "",
             "No elaborated connectivity, simulator traffic or checker PASS implied.", ""]
    for category in ("instances", "routes", "groups", "test_profiles"):
        entry = view[category]
        lines.append("## " + category.replace("_", " ").title())
        for status in ("added", "removed"):
            for name in entry[status]:
                lines.append("- " + status + ": " + str(name))
        for name, fields in entry["changed"].items():
            lines.append("- changed: " + str(name))
            for field, delta in fields.items():
                lines.append("  - " + field + ": " + json.dumps(delta, sort_keys=True))
        if not any((entry["added"], entry["removed"], entry["changed"])):
            lines.append("- No changes")
        lines.append("")
    lines.append("## SoC configuration")
    for field, change in view["soc_configuration"].items():
        lines.append("- " + field + ": " + json.dumps(change, sort_keys=True))
    if not view["soc_configuration"]:
        lines.append("- No changes")
    return "\n".join(lines) + "\n"


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
    result["semantic"] = semantic_difference(before, after)
    return result



def selected_variant_diff(root_before: Path, profile_before: str,
                          root_after: Path, profile_after: str) -> dict:
    """Source-only comparison of two independently verified selected runs."""
    from difflib import unified_diff
    from selected_rtl_provenance import verify_selected_archive

    def read(root, profile):
        root = Path(root).resolve()
        tests = yaml.safe_load((root / "config/regression.yaml").read_text())["tests"]
        if profile not in tests:
            raise ValueError("unknown selected RTL profile")
        return root, verify_selected_archive(root, profile, tests[profile])

    root_a, a = read(root_before, profile_before)
    root_b, b = read(root_after, profile_after)

    def hashes(field):
        before, after = a.get(field, {}), b.get(field, {})
        return {"added": sorted(set(after) - set(before)),
                "removed": sorted(set(before) - set(after)),
                "changed": sorted(k for k in before.keys() & after.keys()
                                  if before[k] != after[k])}

    top_before, top_after = a.get("selected_soc_top"), b.get("selected_soc_top")
    rtl = None
    if top_before or top_after:
        if not top_before or not top_after:
            raise ValueError("selected SoC top absent in one run")
        path_a = root_a / a["archive"] / top_before
        path_b = root_b / b["archive"] / top_after
        if not path_a.is_file() or not path_b.is_file():
            raise ValueError("missing verified generated SoC top")
        if max(path_a.stat().st_size, path_b.stat().st_size) > 2000000:
            raise ValueError("RTL top too large for bounded text review")
        differences = list(unified_diff(
            path_a.read_text().splitlines(), path_b.read_text().splitlines(),
            fromfile=profile_before + "/" + top_before,
            tofile=profile_after + "/" + top_after, lineterm=""))
        rtl = {"changed": bool(differences), "diff_lines": differences[:500],
               "truncated": len(differences) > 500, "total": len(differences)}
    # Compare source-selected compiler/variant semantics rather than
    # per-invocation identity or review-stage manifest self hashes. This
    # captures selected RTL topology/backend changes that a text diff alone
    # cannot distinguish; each archive has already been verified above.
    source_fields = (
        "compiled_top", "selected_soc_top", "definition_sha256",
        "config_sha256", "filelist_sha256", "includes", "defines", "args",
        "network_filelists",
    )
    selected_contract_changes = {
        name: {"before": a.get(name), "after": b.get(name)}
        for name in source_fields if a.get(name) != b.get(name)
    }
    return {
        "schema_version": 1,
        "evidence": "selected_source_sha_verified_not_elaborated_or_observed",
        "selected_compiler_contract": {
            "evidence": "compiler_source_selected_not_elaborated",
            "changed": selected_contract_changes,
        },
        "before": {"profile": profile_before, "sha": a["compiler_input_sha256"]},
        "after": {"profile": profile_after, "sha": b["compiler_input_sha256"]},
        "rtl_sources": hashes("source_sha256"),
        "include_headers": hashes("include_headers_sha256"),
        "generated_files": hashes("generated_sha256"),
        "selected_soc_top_text": rtl,
    }


def selected_variant_markdown(result: dict) -> str:
    if result.get("evidence") != "selected_source_sha_verified_not_elaborated_or_observed":
        raise ValueError("invalid source-diff evidence tier")
    lines = ["# Exact selected RTL comparison", "",
             "SHA-verified compiler input source, not elaboration or observed traffic.", ""]
    for stage in ("before", "after"):
        lines.append(stage + ": " + result[stage]["profile"] + " (" +
                     result[stage]["sha"] + ")")
    contract = result["selected_compiler_contract"]
    if contract.get("evidence") != "compiler_source_selected_not_elaborated":
        raise ValueError("invalid selected compiler contract evidence tier")
    lines.extend(["", "## Selected compiler and hardware selection",
                  "Source-attested compiler contract only; not physical pin proof."])
    for name, delta in sorted(contract["changed"].items()):
        lines.append("- changed " + name + ": " + json.dumps(delta, sort_keys=True))
    if not contract["changed"]:
        lines.append("- No compiler-selection changes")
    for group in ("rtl_sources", "include_headers", "generated_files"):
        lines.extend(["", "## " + group])
        for kind in ("added", "removed", "changed"):
            for path in result[group][kind]:
                lines.append(kind + ": " + path)
    if result["selected_soc_top_text"] is not None:
        top = result["selected_soc_top_text"]
        lines.extend(["", "## Generated SoC top SystemVerilog diff",
                      "Total diff lines: " + str(top["total"]),
                      *top["diff_lines"]])
        if top["truncated"]:
            lines.append("TRUNCATED: see original archived generated RTL.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diff", type=Path, help="existing prior graph to compare")
    parser.add_argument("--selected-before", metavar="PROFILE")
    parser.add_argument("--selected-after", metavar="PROFILE")
    parser.add_argument("--before-root", type=Path)
    parser.add_argument("--after-root", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--verification-report", action="append", default=[], metavar="PROFILE=JSON",
                        help="import hdl-kgraph query uvm --json output; do not treat as runtime truth")
    args = parser.parse_args()
    if args.selected_before or args.selected_after:
        if not args.selected_before or not args.selected_after or args.diff:
            parser.error("selected comparison needs two profiles without --diff")
        result = selected_variant_diff(
            args.before_root or args.root, args.selected_before,
            args.after_root or args.root, args.selected_after)
        output = (selected_variant_markdown(result) if args.format == "markdown"
                  else json.dumps(result, indent=2) + "\n")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output)
        else:
            print(output, end="")
        return
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
    if args.format == "markdown" and not args.diff:
        parser.error("--format markdown requires --diff")
    result = markdown_diff(data) if args.format == "markdown" else json.dumps(data, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
