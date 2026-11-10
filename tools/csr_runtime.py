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

    def compare_frontdoor_axi_read(
        self, logical_path: str, trace: dict, *, monitor: str,
        tested_sha: str, workflow_run_id: str, workflow_attempt: str,
        quiescent_start_ps: int, snapshot_ps: int,
    ) -> dict:
        """Compare one genuine 32-bit Config-NoC AXI read with live RTL.

        Called from the original simulator process at an explicit quiescent
        checkpoint, with its own passive trace. No extra BFM or CSR writes.
        A historical trace, unsupported width, missing completion, side
        effect or mismatched source/run never qualifies.
        """
        import re
        if (not re.fullmatch(r"[a-f0-9]{40}", tested_sha)
                or not workflow_run_id.isdecimal()
                or not workflow_attempt.isdecimal()
                or type(quiescent_start_ps) is not int
                or type(snapshot_ps) is not int
                or quiescent_start_ps < 0
                or snapshot_ps <= quiescent_start_ps):
            raise BindingError("unqualified frontdoor run source/checkpoint")
        field = self._fields.get(logical_path)
        if field is None or field["status"] != "bound_unvalidated":
            raise BindingError("CSR field not bound for frontdoor comparison")
        if field["policy"] != "backdoor_read_only":
            raise BindingError("CSR has side effects or unsafe backdoor policy")
        if not isinstance(trace, dict) or trace.get("schema_version") != 2:
            raise BindingError("missing canonical passive AXI trace")
        run = trace.get("run") or {}
        if (run.get("commit") != tested_sha
                or run.get("dirty") is not False
                or run.get("engine") != "cocotb-verilator"
                or str(run.get("workflow_run_id")) != workflow_run_id
                or str(run.get("workflow_attempt")) != workflow_attempt
                or run.get("capture_bound") is not True
                or run.get("capture_overflow") is not False):
            raise BindingError("AXI trace provenance/capture does not match live run")
        axi = (trace.get("sections") or {}).get("axi") or {}
        if axi.get("issues") or not isinstance(axi.get("transactions"), list):
            raise BindingError("dirty or incomplete AXI transactions")
        monitors = [m for m in axi.get("monitors", [])
                    if m.get("id") == monitor]
        if (len(monitors) != 1 or monitors[0].get("plane") != "config"
                or monitors[0].get("role") != "initiator"
                or monitors[0].get("data_width") != 32):
            raise BindingError("unqualified 32-bit config initiator capture")
        def numeric(value):
            if type(value) is int:
                return value
            if isinstance(value, str):
                try:
                    return int(value, 0)
                except ValueError:
                    pass
            raise BindingError("invalid AXI address, response or read data")
        address = numeric(field["address"])
        relevant = [tx for tx in axi["transactions"]
                    if tx.get("monitor") == monitor
                    and tx.get("plane") == "config"
                    and numeric(tx.get("address")) == address
                    and type(tx.get("start_ps")) is int
                    and quiescent_start_ps <= tx["start_ps"] <= snapshot_ps]
        if len(relevant) != 1:
            raise BindingError("ambiguous/missing AXI CSR transaction in quiescent window")
        row = relevant[0]
        beats = row.get("beats")
        if (row.get("role") != "initiator"
                or row.get("operation") != "read"
                or row.get("status") != "complete"
                or row.get("issues")
                or row.get("expected_beats") != 1
                or not isinstance(beats, list) or len(beats) != 1
                or type(row.get("end_ps")) is not int
                or row["end_ps"] > snapshot_ps
                or row["end_ps"] < row["start_ps"]
                or numeric(row.get("response")) != 0
                or numeric((row.get("request") or {}).get("size")) != 2
                or numeric(beats[0].get("last")) != 1
                or numeric(beats[0].get("resp")) != 0):
            raise BindingError("CSR frontdoor read is incomplete/unsafe/not four bytes")
        value = numeric(beats[0].get("data"))
        if value < 0 or value >= 1 << 32:
            raise BindingError("AXI CSR read data outside 32-bit bus width")
        frontdoor = (value >> field["lsb"]) & ((1 << field["width_bits"]) - 1)
        backdoor = self.read(logical_path, quiescent=True)
        if frontdoor != backdoor:
            raise BindingError("independently accepted AXI CSR differs from live HDL bits")
        return {
            "schema_version": 1,
            "status": "matching_accepted_axi_and_quiescent_live_hdl_field",
            "logical_path": logical_path, "address": field["address"],
            "field_bits": field["width_bits"],
            "frontdoor_value": frontdoor, "backdoor_value": backdoor,
            "rtl_path": field["rtl_path"],
            "simulator": self.map["simulator"], "top": self.map["top"],
            "variant": self.map["variant"],
            "build_sha256": self.map["build_sha256"],
            "tested_sha": tested_sha, "workflow_run_id": workflow_run_id,
            "workflow_attempt": workflow_attempt,
            "quiescent_start_ps": quiescent_start_ps,
            "snapshot_ps": snapshot_ps,
            "axi_uid": row.get("uid"),
            "scope": "one_32bit_AXI_read_and_one_live_hdl_field_not_coverage",
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
