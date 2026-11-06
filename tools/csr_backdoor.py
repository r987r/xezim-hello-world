"""Fail-closed instance-aware CSR path binding (no fabricated RTL hierarchy).

Input catalog: csrgen's per-variant register map, plus an actual elaboration
inventory supplied by a simulator-specific adapter. The inventory is evidence
of visibility, NOT evidence of an AXI transaction or correct register storage.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping

POLICIES = frozenset({
    "frontdoor_only", "backdoor_read_only",
    "quiescent_raw_storage_rw", "behavioral_hook_required", "unavailable",
})
SAFE_KINDS = frozenset({"reg", "logic", "var", "memory_word"})
PATH_RE = re.compile(r"^[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*|\[[0-9]+\])*$")


class BindingError(ValueError):
    pass


def _integer(v):
    if type(v) is int:
        return v
    if isinstance(v, str):
        return int(v, 0)
    raise BindingError(f"invalid integer {v!r}")


def _fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def compose(catalog: dict) -> dict:
    """Build logical CSR identities and absolute addresses, no physical paths."""
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("instances"), list):
        raise BindingError("unsupported CSR catalog")
    entries = []
    seen_names, occupied = set(), []
    for instance in catalog["instances"]:
        name = instance["name"]
        base, size = _integer(instance["base"]), _integer(instance["size"])
        if name in seen_names or base < 0 or size <= 0 or base + size > 1 << 64:
            raise BindingError("duplicate or malformed CSR instance")
        seen_names.add(name)
        if not instance.get("registers"):
            continue  # Reserved/external windows: no physical register claim.
        if instance.get("status") != "implemented":
            raise BindingError(f"{name}: registers declared in unavailable instance")
        for register in instance["registers"]:
            offset, bytes_ = _integer(register["offset"]), _integer(register["size_bytes"])
            regname = register["name"]
            if not isinstance(regname, str) or not regname or offset < 0 or bytes_ <= 0:
                raise BindingError("invalid register")
            if offset % bytes_ or offset + bytes_ > size:
                raise BindingError(f"{name}.{regname}: misaligned or out of bounds")
            address = base + offset
            if any(address < end and start < address + bytes_ for start, end in occupied):
                raise BindingError("overlapping composed CSR addresses")
            occupied.append((address, address + bytes_))
            fields = register.get("fields", [])
            for field in fields:
                logical = f"{name}.{regname}.{field['name']}"
                width = _integer(field["msb"]) - _integer(field["lsb"]) + 1
                if width <= 0 or _integer(field["lsb"]) < 0 or _integer(field["msb"]) >= bytes_ * 8:
                    raise BindingError(f"{logical}: invalid field slice")
                policy = field.get("backdoor_policy", "frontdoor_only")
                if policy not in POLICIES:
                    raise BindingError(f"{logical}: unrecognized backdoor policy")
                entries.append({
                    "logical_path": logical, "instance": name,
                    "register": regname, "field": field["name"],
                    "address": f"0x{address:x}", "lsb": _integer(field["lsb"]),
                    "width_bits": width, "policy": policy,
                })
    if len({e["logical_path"] for e in entries}) != len(entries):
        raise BindingError("duplicate logical CSR field path")
    return {"schema_version": 1, "variant": catalog.get("variant"),
            "catalog_sha256": _fingerprint(catalog), "fields": entries}


def bind(composed: dict, inventory: dict, bindings: list[dict]) -> dict:
    """Validate explicitly supplied bindings against actual elaboration inventory.

    A path listed in the inventory is only a visible HDL object, not proven
    register state: an integration test must still validate storage semantics.
    """
    if (composed.get("schema_version") != 1 or inventory.get("schema_version") != 1
            or not isinstance(inventory.get("objects"), list)
            or not inventory.get("top") or not inventory.get("build_sha256")
            or not inventory.get("simulator")):
        raise BindingError("missing exact-build elaboration evidence")
    if inventory.get("variant") != composed.get("variant"):
        raise BindingError("elaboration variant differs from CSR map")
    objects = {}
    for obj in inventory["objects"]:
        path = obj.get("path")
        if not isinstance(path, str) or not PATH_RE.fullmatch(path) or path in objects:
            raise BindingError("duplicate or malformed elaborated RTL path")
        objects[path] = obj
    provided = {}
    for binding in bindings:
        logical = binding.get("logical_path")
        if logical in provided or not isinstance(logical, str):
            raise BindingError("duplicate/invalid binding")
        provided[logical] = binding
    fields = []
    consumed = set()
    for field in composed["fields"]:
        logical = field["logical_path"]
        req = provided.pop(logical, None)
        entry = dict(field)
        entry["status"] = "unavailable"
        entry["rtl_path"] = None
        if req:
            path = req.get("rtl_path")
            if path not in objects:
                raise BindingError(f"{logical}: path absent from elaborated RTL")
            obj = objects[path]
            if obj.get("kind") not in SAFE_KINDS:
                raise BindingError(f"{logical}: HDL object is not storage")
            width = _integer(obj.get("width_bits"))
            slice_lsb = _integer(req.get("rtl_lsb", 0))
            if slice_lsb < 0 or slice_lsb + field["width_bits"] > width:
                raise BindingError(f"{logical}: field exceeds RTL signal width")
            if field["policy"] in ("frontdoor_only", "unavailable"):
                raise BindingError(f"{logical}: policy prohibits backdoor binding")
            if field["policy"] == "quiescent_raw_storage_rw" and not obj.get("writable", False):
                raise BindingError(f"{logical}: requested write against read-only RTL")
            # A shared storage word may hold multiple disjoint fields, but an
            # identical physical bit must not be bound to different logical fields.
            for bit in range(slice_lsb, slice_lsb + field["width_bits"]):
                address = (path, bit)
                if address in consumed:
                    raise BindingError(f"{logical}: aliased physical RTL bit")
                consumed.add(address)
            entry.update(status="bound_unvalidated", rtl_path=path, rtl_lsb=slice_lsb,
                         rtl_width_bits=width, rtl_kind=obj["kind"],
                         readable=True,
                         writable=field["policy"] == "quiescent_raw_storage_rw")
        fields.append(entry)
    if provided:
        raise BindingError(f"unknown logical CSR fields: {sorted(provided)}")
    return {
        "schema_version": 1, "variant": composed["variant"],
        "catalog_sha256": composed["catalog_sha256"],
        "simulator": inventory["simulator"], "top": inventory["top"],
        "build_sha256": inventory["build_sha256"],
        "inventory_sha256": _fingerprint(inventory),
        "qualification": "bindings_checked_against_elaboration_not_frontdoor_verified",
        "fields": fields,
    }
