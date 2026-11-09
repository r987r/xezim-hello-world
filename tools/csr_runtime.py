"""Read-only CSR runtime handle resolution against exact validated RTL inventory.

This adapter does not perform VPI writes, cannot emulate MMIO side effects
and never fabricates a simulator handle. Simulator callers must enumerate
their *real elaborated* signals and supply matching build provenance.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from tools.csr_backdoor import BindingError, bind, compose, PATH_RE


@dataclass(frozen=True)
class RuntimeEvidence:
    simulator: str
    top: str
    variant: str
    build_sha256: str


class ReadOnlyCsrRuntime:
    def __init__(self, catalog: dict, inventory: dict, bindings: list[dict],
                 handles: dict[str, Any], evidence: RuntimeEvidence):
        if not evidence.build_sha256 or len(evidence.build_sha256) != 64:
            raise BindingError("missing exact simulator build hash")
        for key in ("simulator", "top", "variant", "build_sha256"):
            if inventory.get(key) != getattr(evidence, key):
                raise BindingError(f"runtime {key} does not match bound elaboration inventory")
        self.map = bind(compose(catalog), inventory, bindings)
        expected={item["rtl_path"] for item in self.map["fields"]
                  if item["status"]=="bound_unvalidated"}
        if set(handles)!=expected:
            raise BindingError("runtime handles do not match exactly the elaborated binding inventory")
        for path,handle in handles.items():
            if not PATH_RE.fullmatch(path) or not hasattr(handle,"value"):
                raise BindingError(f"missing/invalid live simulator handle: {path}")
        self._handles = dict(handles)
        self._fields = {x["logical_path"]:x for x in self.map["fields"]}

    def read(self, logical_path: str, *, quiescent: bool) -> int:
        if not quiescent:
            raise BindingError("CSR backdoor read requires an explicitly quiescent checkpoint")
        if logical_path not in self._fields:
            raise BindingError("unknown logical CSR field")
        entry = self._fields[logical_path]
        if entry["status"] != "bound_unvalidated":
            raise BindingError("CSR field unavailable for backdoor")
        if entry["policy"] != "backdoor_read_only":
            raise BindingError("CSR field is not approved for raw backdoor reads")
        value = self._handles[entry["rtl_path"]].value
        try:
            raw = int(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise BindingError("unresolved or X/Z RTL value; cannot read CSR field") from exc
        if raw < 0 or raw >= 1 << entry["rtl_width_bits"]:
            raise BindingError("live RTL signal width/value mismatch")
        return (raw >> entry["rtl_lsb"]) & ((1 << entry["width_bits"]) - 1)

    def snapshot(self, *, quiescent: bool) -> dict:
        """Emit a source-bound CSR availability/read snapshot, never an AXI PASS.

        A visible storage handle is still semantically *unvalidated* until a
        separate real frontdoor comparison. Preserve unavailable/side-effect
        fields as unavailable and never sample them through a raw handle.
        """
        if not quiescent:
            raise BindingError("CSR snapshot requires quiescent checkpoint")
        fields = []
        for entry in self.map["fields"]:
            item = {
                "logical_path": entry["logical_path"],
                "address": entry["address"],
                "policy": entry["policy"],
                "binding_status": entry["status"],
                "rtl_path": entry["rtl_path"],
                "read_evidence": "not_available",
                "value": None,
            }
            if (entry["status"] == "bound_unvalidated"
                    and entry["policy"] == "backdoor_read_only"):
                item["value"] = self.read(entry["logical_path"], quiescent=True)
                item["read_evidence"] = "quiescent_live_hdl_read_not_frontdoor_verified"
            fields.append(item)
        return {
            "schema_version": 1,
            "simulator": self.map["simulator"],
            "top": self.map["top"],
            "variant": self.map["variant"],
            "build_sha256": self.map["build_sha256"],
            "inventory_sha256": self.map["inventory_sha256"],
            "catalog_sha256": self.map["catalog_sha256"],
            "qualification": "live_handle_snapshot_not_independent_csr_or_axi_proof",
            "frontdoor_equivalence_proven": False,
            "protocol_traffic_observed": False,
            "fields": fields,
        }

    def write(self, *args, **kwargs):
        raise BindingError("direct CSR backdoor writes are disabled; use frontdoor or qualified semantic hook")


def cocotb_handle(root: Any, rtl_path: str) -> Any:
    """Resolve a *literal* listed hierarchical VPI name, never fuzzy match."""
    if not PATH_RE.fullmatch(rtl_path):
        raise BindingError("malformed requested RTL path")
    parts = rtl_path.split(".")
    if parts[0] != getattr(root, "_name", None):
        raise BindingError("RTL top differs from resolved cocotb root")
    handle = root
    for part in parts[1:]:
        if "[" in part:
            basename, index = part.split("[",1)
            index = int(index[:-1])
            try:
                handle = getattr(handle, basename)[index]
            except (AttributeError, IndexError, KeyError, TypeError) as exc:
                raise BindingError(f"RTL array handle unavailable: {part}") from exc
        else:
            try:
                handle = getattr(handle, part)
            except AttributeError as exc:
                raise BindingError(f"RTL handle unavailable: {part}") from exc
    if not hasattr(handle, "value"):
        raise BindingError("RTL path resolves to scope, not readable signal")
    return handle
