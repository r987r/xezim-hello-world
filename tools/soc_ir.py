#!/usr/bin/env python3
"""Versioned source-declared SoC graph: one input contract for future emitters.

This initial #165 adapter normalizes CURRENT soc.yaml and current generated
NoC topology, without replacing pinned RTL emitters or claiming elaboration.
No behavioral SRAM/HBM model is silently promoted to controller RTL.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml

from socgen import integer, validate as validate_soc

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1


class SocIRError(ValueError):
    pass


def encoded(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def unique(rows: list, key: str, kind: str) -> dict:
    if not isinstance(rows, list):
        raise SocIRError(f"{kind} must be a list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str):
            raise SocIRError(f"malformed {kind} record")
        name = row[key]
        if not name or name in result:
            raise SocIRError(f"duplicate/invalid {kind} identity: {name}")
        result[name] = row
    return result


def _connection_id(row: dict) -> str:
    start, end = row["from"], row["to"]
    key = [start["instance"], start["port"], end["instance"], end["port"],
           row.get("type", "")]
    return "wire:" + digest(key)[:24]


def normalize_soc(soc: dict) -> dict:
    """A semantic normalization; named YAML ordering does not alter IR."""
    doc = copy.deepcopy(soc)
    for field in ("subsystems", "memory_targets"):
        unique(doc[field], "name", field)
        doc[field] = sorted(doc[field], key=lambda r: r["name"])
    for plane, items in doc["address_map"].items():
        unique(items, "name", "address_map." + plane)
        doc["address_map"][plane] = sorted(items, key=lambda r: r["name"])
    for net in doc["networks"].values():
        if "outputs" in net:
            unique(net["outputs"], "name", "NoC output")
            net["outputs"] = sorted(net["outputs"], key=lambda r: r["name"])
        if "reachable_subsystems" in net:
            refs = net["reachable_subsystems"]
            if len(refs) != len(set(refs)):
                raise SocIRError("duplicate reachable subsystem")
            net["reachable_subsystems"] = sorted(refs)
    return doc


def compile_ir(soc: dict, topology: dict) -> dict:
    """Compile the source-authoritative SoC and generated NoC contract.

    Reject drift, duplicates and invalid addresses without constructing
    a fake netlist. The graph is intentionally readonly until IR-driven
    emission has independent old-vs-new RTL equivalence tests.
    """
    if not isinstance(soc, dict) or not isinstance(topology, dict):
        raise SocIRError("SoC inputs must be objects")
    if topology.get("schema_version") != 1:
        raise SocIRError("unsupported source topology schema")
    # Use the existing SoC validator: never fork an address, boot or
    # subsystem placement policy in a second schema.
    validate_soc(soc)
    cfg = normalize_soc(soc)
    subsystem_names = set(unique(cfg["subsystems"], "name", "subsystem"))
    memories = unique(cfg["memory_targets"], "name", "memory target")
    nodes = unique(topology["instances"], "name", "RTL instance")
    links = {}
    for row in topology["connections"]:
        try:
            origin = row["from"]
            target = row["to"]
            if (not isinstance(origin["port"], str) or not origin["port"]
                    or not isinstance(target["port"], str) or not target["port"]
                    or origin["instance"] not in nodes
                    or target["instance"] not in nodes):
                raise SocIRError("unknown or malformed source connectivity endpoint")
            key = _connection_id(row)
        except (KeyError, TypeError) as exc:
            raise SocIRError("malformed generated connectivity link") from exc
        if key in links:
            raise SocIRError("duplicate generated link by physical endpoint")
        links[key] = {
            "id": key, "from": origin, "to": target,
            "protocol": row.get("type"),
            "signals": row.get("signals", []),
            "attachment": row.get("status", "not_declared"),
            "evidence": "source_generated_not_elaborated",
        }
    groups = unique(topology["groups"], "name", "network group")
    for group in groups.values():
        for name in group["instances"]:
            if name not in nodes:
                raise SocIRError("generated group contains unrecognized instance")
    for name in subsystem_names:
        if not any(n == name or n.startswith(name + ".") or
                   n.startswith(name + "_") for n in nodes):
            raise SocIRError(f"source SoC subsystem missing from generated graph: {name}")
    address = {}
    for plane, regions in cfg["address_map"].items():
        for item in regions:
            key = plane + ":" + item["name"]
            address[key] = {
                "name": item["name"], "plane": plane,
                "base": integer(item["base"]), "size": integer(item["size"]),
                "evidence": "source_config_not_elaborated",
            }
    for name in memories:
        if "data:" + name not in address:
            raise SocIRError(f"memory target lacks data aperture: {name}")

    modules = []
    for name, row in sorted(nodes.items()):
        info = row.get("info", {})
        if not isinstance(info, dict):
            raise SocIRError("malformed generated instance metadata")
        modules.append({
            "id": name, "module": row.get("module"),
            "ports": [],  # Physical bit/port proof belongs to existing #46.
            "interface_metadata": {
                key: info.get(key) for key in
                ("protocol", "role", "data_bits", "address_bits", "id_bits", "plane")
                if key in info},
            "network": info.get("network"),
            "attachment": info.get("status", "source_declared_only"),
        })
    config_digest = digest(cfg)
    body = {
        "schema_version": SCHEMA,
        "project": cfg["name"],
        "variant": "default",
        "canonical_config_sha256": config_digest,
        "address_map": [address[k] for k in sorted(address)],
        "buses": cfg["buses"],
        "fabrics": cfg["fabrics"],
        "subsystems": cfg["subsystems"],
        "memory_targets": cfg["memory_targets"],
        "networks": cfg["networks"],
        "instances": modules,
        "links": [links[k] for k in sorted(links)],
        "groups": [{"name": name, "instances": sorted(row["instances"]),
                    "info": row.get("info", {})}
                   for name, row in sorted(groups.items())],
        "ip_locks": "config/ip.lock.yaml plus Bender.lock remain authoritative",
        "evidence": "declared_soc_plus_generated_topology_not_rtl_elaboration",
        "known_limitations": [
            "RTL emitters do not yet consume this IR",
            "named variants beyond default still use legacy regress.py mode selection",
            "bit-accurate instance ports require independent #46 elaboration",
        ],
    }
    return {**body, "ir_sha256": digest(body)}


def verify_ir(value: dict, soc: dict, topology: dict) -> dict:
    reference = compile_ir(soc, topology)
    if value != reference:
        raise SocIRError("canonical SoC IR differs from source SoC/topology")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    soc_path = root / "config/soc.yaml"
    graph_path = root / "gen/diagrams/noc-topology.json"
    soc = yaml.safe_load(soc_path.read_text())
    topology = json.loads(graph_path.read_text())
    value = compile_ir(soc, topology)
    if args.check:
        if not args.out.is_file() or args.out.is_symlink():
            raise SocIRError("canonical SoC IR absent for check")
        verify_ir(json.loads(args.out.read_text()), soc, topology)
        print("PASS canonical SoC IR source match: " + value["ir_sha256"])
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(encoded(value))
    print("SOC-IR: " + value["ir_sha256"] + " (declarative; no RTL proof)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
