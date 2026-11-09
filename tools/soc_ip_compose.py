#!/usr/bin/env python3
"""Typed SoC subsystem/IP composition manifests, without invented RTL pins.

Extends the existing subsystem_plugin_contract.Registry and source SoC IR.
This initial #166 deliverable is an exact, fail-closed declaration of what
each supported SoC subsystem requires. Actual full_chip_gen emitter migration
and old-vs-new selected RTL equivalence are subsequent milestones.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

from soc_ir import compile_ir, encoded, digest
from subsystem_plugin_contract import Port, Registry, SubsystemContract

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1
KNOWN = frozenset(("compute", "memory", "peripheral"))
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")


class CompositionError(ValueError):
    pass


def registry(data_bits: int, config_bits: int) -> Registry:
    """One reusable contract per *type*, not per instance name."""
    for name, width in (("data", data_bits), ("config", config_bits)):
        if type(width) is not int or not 1 <= width <= 1024:
            raise CompositionError("invalid typed " + name + " bus width")

    def port(name: str, protocol: str, direction: str, role: str, width: int) -> Port:
        return Port(name, protocol, direction, role, width, "soc")

    fabric = Registry()
    fabric.register(SubsystemContract(
        "compute", ("soc",), (
            port("data_master", "axi4", "output", "initiator", data_bits),
            port("data_target", "axi4", "input", "target", data_bits),
            port("config_master", "axi4_lite", "output", "initiator", config_bits),
            port("config_target", "axi4_lite", "input", "target", config_bits),
        ), "full_chip_gen"))
    fabric.register(SubsystemContract(
        "memory", ("soc",), (
            port("data_target", "axi4", "input", "target", data_bits),
            port("config_target", "axi4_lite", "input", "target", config_bits),
        ), "full_chip_gen"))
    fabric.register(SubsystemContract(
        "peripheral", ("soc",), (
            port("data_master", "axi4", "output", "initiator", data_bits),
            port("data_target", "axi4", "input", "target", data_bits),
            port("config_master", "axi4_lite", "output", "initiator", config_bits),
            port("config_target", "axi4_lite", "input", "target", config_bits),
        ), "full_chip_gen"))
    return fabric


def compose(soc: dict, ir: dict, *, locks: dict[str, str] | None = None) -> dict:
    """Validate instance contracts against the current normalized SoC graph."""
    if (not isinstance(soc, dict) or not isinstance(ir, dict)
            or ir.get("schema_version") != 1
            or ir.get("project") != soc.get("name")):
        raise CompositionError("foreign SoC IR / source project")
    if not isinstance(ir.get("subsystems"), list) or not ir.get("ir_sha256"):
        raise CompositionError("invalid source IR")
    subsystems = ir["subsystems"]
    if subsystems != sorted(soc["subsystems"], key=lambda v: v["name"]):
        raise CompositionError("IR instance inventory does not match source SoC")
    if any(row.get("type") not in KNOWN for row in subsystems):
        raise CompositionError("unsupported subsystem type requires registered emitter")
    data_width = ir["buses"]["data"]["data_bits"]
    config_width = ir["buses"]["config"]["data_bits"]
    contracts = registry(data_width, config_width)
    topology_ids = {inst["id"] for inst in ir["instances"]}
    addresses = {row["name"]: row for row in ir["address_map"]}
    all_ports = {}
    instance_metadata = []
    for spec in subsystems:
        name, kind = spec["name"], spec["type"]
        if not IDENT.fullmatch(name):
            raise CompositionError("unsupported instance name syntax")
        if (not any(inst == name or inst.startswith(name + "_")
                    or inst.startswith(name + ".") for inst in topology_ids)):
            raise CompositionError(f"{name}: no corresponding generated source topology")
        domain = spec.get("clock_domain", "soc")
        if domain != "soc":
            # No implicit CDC: a clock-changing capability requires explicit
            # adapter/physical proof before the generator can accept it.
            raise CompositionError(f"{name}: unsupported clock domain without CDC adapter")
        template = contracts.resolve(kind)
        if kind == "compute":
            cpu = spec.get("cpu")
            if not isinstance(cpu, dict) or not cpu.get("ip"):
                raise CompositionError("compute instance requires real CPU IP declaration")
            implementation = {"cpu": cpu["ip"],
                              "dma": soc["subsystem_types"]["compute"]["dma"]}
        elif kind == "memory":
            targets = [row for row in ir["memory_targets"]
                       if row["name"].startswith(name + ".")]
            if not targets:
                raise CompositionError("memory instance requires registered memory targets")
            implementation = {"targets": [
                {"name": row["name"], "controller_profile": row["controller"],
                 "simulation_backend": row["simulation"]["backend"]}
                for row in targets]}
        else:
            ip = spec.get("ip")
            if not isinstance(ip, str) or not ip:
                raise CompositionError("peripheral instance requires registered IP")
            implementation = {"ip": ip}
        ports = [{
            "name": p.name, "protocol": p.protocol, "direction": p.direction,
            "role": p.role, "data_bits": p.width, "clock": p.clock,
            "port_evidence": "logical_contract_not_rtl_pin_elaboration",
        } for p in template.ports]
        all_ports[name] = ports
        apertures = sorted(item for item in addresses if item.startswith(("data:", "config:"))
                           and addresses[item]["name"].startswith(name + "."))
        instance_metadata.append({
            "name": name, "kind": kind,
            "emitter": template.emitter, "clock_domain": domain,
            "implementation": implementation,
            "address_apertures": apertures,
            "ports": ports,
            "attachment_evidence": "source_config_and_generated_topology_not_rtl_elaboration",
        })
    graph_links = sorted([{
        "id": edge["id"], "from": edge["from"], "to": edge["to"],
        "evidence": edge["evidence"],
    } for edge in ir["links"]], key=lambda x: x["id"])
    body = {
        "schema_version": SCHEMA,
        "project": ir["project"],
        "variant": ir["variant"],
        "soc_ir_sha256": ir["ir_sha256"],
        "source_locks_sha256": locks or {},
        "instances": instance_metadata,
        "source_topology_links": graph_links,
        "evidence": "typed_subsystem_contract_not_compiled_pin_binding",
        "unimplemented_gates": [
            "per-instance source-closure loader and generic SV emitter",
            "generated RTL old/new equivalence and NoC/CSR parity",
            "multi-instance emission and supported IP variant composition",
            "real byte/port elaboration and independent protocol traffic proof",
        ],
    }
    return {**body, "composition_sha256": digest(body)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    soc = yaml.safe_load((root / "config/soc.yaml").read_text())
    graph = json.loads((root / "gen/diagrams/noc-topology.json").read_text())
    ir = compile_ir(soc, graph)
    lock_files = ("config/ip.lock.yaml", "Bender.lock", "Bender.yml")
    locks = {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
             for path in lock_files}
    result = compose(soc, ir, locks=locks)
    if args.check:
        if args.out.is_symlink() or not args.out.is_file():
            raise CompositionError("missing typed composition manifest")
        if json.loads(args.out.read_text()) != result:
            raise CompositionError("stale or foreign typed composition manifest")
        print("PASS typed composition source parity: " + result["composition_sha256"])
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(encoded(result))
        print("IP-COMPOSE: " + result["composition_sha256"] +
              " (type contracts only; no RTL emitted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
