"""Read-only runtime HDL handle adapter for elaboration-verified CSR fields.

This adapter intentionally does NOT manufacture hierarchy from SystemRDL,
store writes, or emulate AXI semantics. A simulator must provide *actual*
visible HDL handles. Frontdoor-only fields are never accessed via backdoor.
Both Verilator/cocotb and Xezim/VPI can supply wrappers with .value/len.
"""
from __future__ import annotations

import re
from .csr_backdoor import BindingError, bind, POLICIES

PART = re.compile(r"^([a-zA-Z_$][a-zA-Z0-9_$]*)(?:\[([0-9]+)\])?$")


def resolve_handle(dut, full_path: str):
    """Walk real simulator handles; do not accept arbitrary Python attributes.

    The user-supplied physical path must start at the simulator top handle's
    actual name, e.g. 'reset_axi_tb.u_regblock.some_q'.
    """
    if not isinstance(full_path, str) or not full_path:
        raise BindingError("missing simulator hierarchy path")
    actual_top = getattr(dut, "_name", None)
    if not actual_top:
        raise BindingError("runtime DUT handle has no verifiable name")
    parts = full_path.split(".")
    if not parts or parts[0] != actual_top:
        raise BindingError("path does not match the actual simulator top")
    obj = dut
    for part in parts[1:]:
        m = PART.fullmatch(part)
        if not m:
            raise BindingError(f"invalid simulator hierarchy segment {part!r}")
        label, index = m.group(1), m.group(2)
        try:
            obj = getattr(obj, label)
            if index is not None:
                obj = obj[int(index)]
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            raise BindingError(f"RTL hierarchy handle not available: {full_path}") from exc
    return obj


def width_of(handle):
    try:
        width = len(handle)
    except (AttributeError, TypeError, ValueError):
        raise BindingError("HDL handle has no measurable bit width") from None
    if type(width) is not int or width <= 0:
        raise BindingError("HDL handle width invalid")
    return width


def discover(dut, *, variant: str, build_sha256: str, simulator: str,
             requested_paths: list[str], strict: bool = False):
    """Build runtime inventory only from actual handle resolution.

    Missing handles are omitted by default and thus cannot be falsely bound.
    strict=True fails closed for a required field. These objects are
    simulator-*visible*, not yet proven to be authoritative CSR flops.
    """
    if not isinstance(build_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", build_sha256):
        raise BindingError("missing exact compiled build fingerprint")
    if not isinstance(variant, str) or not variant:
        raise BindingError("variant required")
    if not isinstance(simulator, str) or simulator not in ("verilator-cocotb", "xezim-vpi", "xezim-dpi"):
        raise BindingError("unsupported simulator backend")
    objects = []
    handles = {}
    for path in requested_paths:
        if path in handles:
            raise BindingError("duplicate requested physical handle")
        try:
            obj = resolve_handle(dut, path)
            width = width_of(obj)
        except BindingError:
            if strict:
                raise
            continue
        handles[path] = obj
        objects.append({"path": path, "kind": "logic", "width_bits": width,
                        "writable": False,
                        "qualification": "runtime_visible_not_proven_register_storage"})
    return ({"schema_version": 1, "variant": variant, "top": dut._name,
             "build_sha256": build_sha256, "simulator": simulator, "objects": objects},
            handles)


class SafeCsrBackdoor:
    """Only frontdoor-equivalent, *read-only* RTL visibility is offered.

    Invoking read() against a frontdoor-only, missing, or non-qualified field
    raises BindingError. Reading a state signal is NOT an AXI transaction.
    """
    def __init__(self, composed, dut, *, build_sha256, simulator, specs,
                 strict=False):
        paths = [r["rtl_path"] for r in specs if r.get("rtl_path")]
        inventory, handles = discover(
            dut, variant=composed["variant"], build_sha256=build_sha256,
            simulator=simulator, requested_paths=paths, strict=strict)
        available = {obj["path"] for obj in inventory["objects"]}
        filtered = [r for r in specs if r.get("rtl_path") in available]
        bound = bind(composed, inventory, filtered)
        self.report = bound
        self._handles = handles
        self._entries = {entry["logical_path"]: entry for entry in bound["fields"]}

    def read(self, logical_path: str) -> int:
        entry = self._entries.get(logical_path)
        if entry is None:
            raise BindingError(f"unknown logical CSR field: {logical_path}")
        if entry["policy"] != "backdoor_read_only":
            raise BindingError(f"{logical_path}: side-effect policy prohibits backdoor read")
        if entry["status"] != "bound_unvalidated" or not entry.get("readable"):
            raise BindingError(f"{logical_path}: no qualified simulator handle")
        handle = self._handles[entry["rtl_path"]]
        try:
            bits = int(handle.value)
        except (AttributeError, TypeError, ValueError) as exc:
            raise BindingError(f"{logical_path}: HDL state unreadable") from exc
        shift = entry["rtl_lsb"]
        return (bits >> shift) & ((1 << entry["width_bits"]) - 1)

    def write(self, logical_path, value):
        raise BindingError("raw CSR backdoor writes are disabled; use frontdoor AXI or verified semantic hook")
