"""Attested, complete *port-boundary* AXI bit connectivity for memory_tb.

Use original slang-netlist Port IDs and enabled directed edges, never inferred
matching names or merged replica nodes. A wiring proof is not a protocol,
transaction, NoC route, clock-domain, DDR PHY or silicon verification result.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from signal_paths import read_graph, enumerate_ports

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "aw": ("id", "addr", "len", "size", "burst", "lock", "cache", "prot", "qos", "valid", "ready"),
    "w": ("data", "strb", "last", "valid", "ready"),
    "b": ("id", "resp", "valid", "ready"),
    "ar": ("id", "addr", "len", "size", "burst", "lock", "cache", "prot", "qos", "valid", "ready"),
    "r": ("id", "data", "resp", "last", "valid", "ready"),
}
FIXED_WIDTHS = {"len": 8, "size": 3, "burst": 2, "lock": 1,
                "cache": 4, "prot": 3, "qos": 4, "valid": 1,
                "ready": 1, "last": 1, "resp": 2}


class ConnectivityEvidenceError(ValueError):
    """Fail-closed rejection of missing or untrusted compiler wiring evidence."""


def _positive(value, name: str, limit: int = 4096) -> int:
    if type(value) is not int or not 1 <= value <= limit:
        raise ConnectivityEvidenceError(f"invalid {name}: {value!r}")
    return value


def _geometry(manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise ConnectivityEvidenceError("selected memory manifest is not an object")
    in_count = _positive(manifest.get("ingress"), "ingress", 16)
    targets = manifest.get("targets")
    if (not isinstance(targets, list) or not targets or len(targets) > 16
            or not all(isinstance(t, dict) and isinstance(t.get("name"), str)
                       and t["name"] for t in targets)
            or len({t["name"] for t in targets}) != len(targets)
            or manifest.get("target_count") != len(targets)):
        raise ConnectivityEvidenceError("invalid selected memory target inventory")
    addr = _positive(manifest.get("address_bits"), "address_bits", 128)
    data = _positive(manifest.get("data_bits"), "data_bits", 1024)
    in_id = _positive(manifest.get("id_bits"), "id_bits", 32)
    backing = _positive(manifest.get("backing_addr_bits"), "backing_addr_bits", 128)
    if data % 8 or backing > addr:
        raise ConnectivityEvidenceError("unaligned data width or backing address width exceeds AXI")
    return {"ingress": in_count, "targets": len(targets), "address": addr,
            "data": data, "input_id": in_id,
            "output_id": in_id + (in_count - 1).bit_length(),
            "backing_address": backing}


def _response_to_initiator(channel: str, field: str) -> bool:
    # AW/W/AR READY is target->initiator, B/R payload and VALID are reverse,
    # B/R READY is initiator->target. Do not infer this from node names alone.
    if channel in ("aw", "w", "ar"):
        return field == "ready"
    return field != "ready"


@dataclass(frozen=True)
class Link:
    name: str
    channel: str
    field: str
    side: str
    index: int
    source: str
    destination: str
    source_is_local: bool
    packed_width_per_lane: int
    local_width: int
    instance_count: int

    @property
    def packed_slice(self) -> tuple[int, int]:
        start = self.index * self.packed_width_per_lane
        return start, start + self.local_width - 1


def links(manifest: dict) -> list[Link]:
    """Authoritative geometry comes from the selected generated manifest.

    Memory AXI models intentionally truncate AWADDR/ARADDR to their backing
    address bits, and expose no QOS target ports. Those omissions are explicit,
    never silently counted as complete 64-bit/AXI4 wiring.
    """
    g = _geometry(manifest)
    out = []
    for side, count in (("s", g["ingress"]), ("m", g["targets"])):
        for index in range(count):
            for channel, fields in FIELDS.items():
                for field in fields:
                    if side == "m" and field == "qos":
                        continue  # memory target model has no QOS input
                    width = FIXED_WIDTHS.get(field)
                    if field == "id":
                        width = g["input_id"] if side == "s" else g["output_id"]
                    elif field == "addr":
                        width = g["address"]
                    elif field == "data":
                        width = g["data"]
                    elif field == "strb":
                        width = g["data"] // 8
                    if width is None:
                        raise ConnectivityEvidenceError(f"unknown AXI field {field}")
                    local_width = (g["backing_address"] if side == "m" and field == "addr"
                                   else width)
                    full_field = channel + field
                    packed = f"memory_tb.fabric.{side}_axi_{full_field}"
                    local = (f"memory_tb.masters[{index}].u_agent.{full_field}"
                             if side == "s" else
                             f"memory_tb.memories[{index}].u_mem.s_axi_{full_field}")
                    reverse = _response_to_initiator(channel, field)
                    source_is_local = (side == "s") != reverse
                    source, destination = ((local, packed) if source_is_local
                                           else (packed, local))
                    out.append(Link(f"{'ingress' if side == 's' else 'target'}{index}.{full_field}",
                                    channel, field, side, index, source, destination,
                                    source_is_local, width, local_width, count))
    return out


def _bits(bounds: list, *, name: str) -> set[int]:
    if (not isinstance(bounds, list) or len(bounds) != 2
            or any(type(b) is not int or b < 0 for b in bounds)):
        raise ConnectivityEvidenceError(f"{name}: invalid bit bounds")
    return set(range(min(bounds), max(bounds) + 1))


def _port_group(by_path: dict, path: str, width: int, label: str) -> list[dict]:
    group = by_path.get(path, [])
    if not group:
        raise ConnectivityEvidenceError(f"{label}: missing real elaborated port {path}")
    observed: set[int] = set()
    for p in group:
        observed.update(_bits(p["bounds"], name=path))
    required = set(range(width))
    if observed != required:
        missing = sorted(required - observed)
        extra = sorted(observed - required)
        raise ConnectivityEvidenceError(
            f"{label}: {path} full port width mismatch, expected={width}, "
            f"missing={missing[:8]}, extra={extra[:8]}")
    return group


def _prove_link(link: Link, by_path: dict, adjacency: dict) -> dict:
    packed_w = link.packed_width_per_lane * link.instance_count
    local_w = link.local_width
    source_w = local_w if link.source_is_local else packed_w
    dest_w = packed_w if link.source_is_local else local_w
    src_nodes = _port_group(by_path, link.source, source_w, link.name)
    dst_nodes = _port_group(by_path, link.destination, dest_w, link.name)
    for p in src_nodes:
        if p["direction"] != "Out":
            raise ConnectivityEvidenceError(f"{link.name}: non-output source {p['id']}")
    for p in dst_nodes:
        if p["direction"] != "In":
            raise ConnectivityEvidenceError(f"{link.name}: non-input sink {p['id']}")

    start, stop = link.packed_slice
    segment = set(range(start, stop + 1))
    dst_by_id = {node["id"]: node for node in dst_nodes}
    all_covered: set[int] = set()
    witness: set[tuple[int, int, int, int]] = set()
    reached_target: dict[int, set[int]] = {n["id"]: set() for n in dst_nodes}
    for src in src_nodes:
        own_bits = _bits(src["bounds"], name=link.name)
        # The serialized edge bounds use packed crossbar coordinates, even
        # when the source is the single-lane, local BFM or target model.
        required = ({bit + start for bit in own_bits} if link.source_is_local
                    else own_bits & segment)
        if not required:
            continue
        observed: set[int] = set()
        for edge in adjacency[src["id"]]:
            dst = dst_by_id.get(edge["target"])
            if dst is None:
                continue
            edge_bits = _bits(edge.get("bounds"), name=f"{link.name} edge")
            if not edge_bits <= segment:
                raise ConnectivityEvidenceError(
                    f"{link.name}: misrouted/oversized edge on source {src['id']}")
            dest_bits = _bits(dst["bounds"], name=link.name)
            valid = ({b for b in edge_bits if b in dest_bits} if link.source_is_local
                     else {b for b in edge_bits if b - start in dest_bits})
            if valid != edge_bits:
                raise ConnectivityEvidenceError(
                    f"{link.name}: edge outside destination bit bounds for {dst['id']}")
            observed |= valid
            reached_target[dst["id"]] |= valid
            witness.add((src["id"], dst["id"], min(edge_bits), max(edge_bits)))
        missing = sorted(required - observed)
        if missing:
            raise ConnectivityEvidenceError(
                f"{link.name}: missing directed bit(s) {missing[:8]} "
                f"from original source replica {src['id']}")
        all_covered |= required
    if all_covered != segment:
        raise ConnectivityEvidenceError(
            f"{link.name}: missing entire source segment bits "
            f"{sorted(segment - all_covered)[:8]}")
    # Separate target port replicas must also be wired. A second unconnected
    # Port node with the same human-readable path is not evidence of delivery.
    for dest in dst_nodes:
        bits = _bits(dest["bounds"], name=link.name)
        required = (bits & segment if link.source_is_local
                    else {b + start for b in bits})
        missing = sorted(required - reached_target[dest["id"]])
        if missing:
            raise ConnectivityEvidenceError(
                f"{link.name}: missing sink bits {missing[:8]} "
                f"on original destination replica {dest['id']}")
    return {"name": link.name, "channel": link.channel, "source": link.source,
            "destination": link.destination, "packed_slice": [start, stop],
            "connected_bit_count": len(segment), "source_port_width": source_w,
            "destination_port_width": dest_w,
            "source_nodes": [n["id"] for n in src_nodes],
            "destination_nodes": [n["id"] for n in dst_nodes],
            "directed_enabled_edge_witnesses": [list(item) for item in sorted(witness)],
            "scope": "direct_interface_port_edge_not_internal_functional_route"}


def audit(netlist: Path, *, selected_meta: Path, manifest_path: Path | None = None,
          source_profile: str = "memory") -> dict:
    manifest_path = Path(manifest_path) if manifest_path else ROOT / "gen/memory/manifest.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    meta = json.loads(selected_meta.read_text())
    source_sha = meta.get("selected_source_sha256")
    if (meta.get("profile") != source_profile or source_profile != "memory"
            or meta.get("top") != "memory_tb" or meta.get("mode") != "netlist"
            or meta.get("evidence") != "elaborated_slang_netlist_inputs_attested"
            or not isinstance(source_sha, dict)
            or not isinstance(source_sha.get("gen/memory/memory_tb.sv"), str)
            or len(source_sha["gen/memory/memory_tb.sv"]) != 64
            or not isinstance(meta.get("plan_sha256"), str)
            or len(meta["plan_sha256"]) != 64):
        raise ConnectivityEvidenceError("missing selected memory RTL provenance")
    actual_hash = hashlib.sha256(netlist.read_bytes()).hexdigest()
    if meta.get("output_sha256") != actual_hash:
        raise ConnectivityEvidenceError("original exported netlist hash mismatch")
    _, nodes, adjacency = read_graph(netlist)
    by_path: dict[str, list[dict]] = {}
    for p in enumerate_ports(nodes):
        by_path.setdefault(p["path"], []).append(p)
    checks = [_prove_link(link, by_path, adjacency) for link in links(manifest)]
    if not checks:
        raise ConnectivityEvidenceError("empty original selected RTL connectivity contract")
    return {"schema_version": 2, "profile": source_profile,
            "netlist_sha256": actual_hash,
            "selected_plan_sha256": meta["plan_sha256"],
            "selected_source_sha256": source_sha,
            "generated_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "checked_direct_port_pairs": len(checks),
            "checked_bit_positions": sum(x["connected_bit_count"] for x in checks),
            "evidence": "actual_elaborated_memory_axi_all_declared_port_bits_only",
            "runtime_axi_accepted": False,
            "physical_ddr_phy_qualified": False,
            "limitations": ["Target-model AWADDR/ARADDR intentionally clip to backing_addr_bits",
                            "Target model has no AWQOS/ARQOS ports",
                            "Only direct port bindings, not internal crossbar transactions/clock/CDC or SoC routes"],
            "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", required=True, type=Path)
    parser.add_argument("--meta", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / "gen/memory/manifest.json")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.netlist, selected_meta=args.meta, manifest_path=args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"CONNECT: {report['checked_direct_port_pairs']} memory AXI field pairs, "
          f"{report['checked_bit_positions']} declared port bit positions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
