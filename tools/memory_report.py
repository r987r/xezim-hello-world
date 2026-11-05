"""Validate memory policy evidence inside the existing correlated AXI report.

Memory operations are NOT AXI transactions. Strict/hybrid must additionally
prove accepted frontdoor traffic at the expected modeled address. Missing or
malformed evidence fails the existing regression, not merely an optional UI.
"""
import json
from pathlib import Path

POLICIES = ("strict", "fast", "hybrid")
EXPECTED_METHODS = {
    ("init", "strict"): "frontdoor",
    ("check", "strict"): "frontdoor",
    ("init", "fast"): "backdoor",
    ("check", "fast"): "backdoor",
    ("init", "hybrid"): "backdoor",
    ("check", "hybrid"): "backdoor+frontdoor-sample",
}


def read_memory_report(directory, rows, period_ps):
    path = Path(directory) / "memory-operations.json"
    if not path.is_file():
        return None, ["memory evidence is missing"]
    try:
        obj = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        return None, [f"memory evidence is unreadable: {exc}"]
    issues = []
    if obj.get("schema_version") != 1 or obj.get("source") != "real_floonoc_host_sparse":
        issues.append("memory evidence must describe the actual routed NoC host backing")
    events = obj.get("events")
    if not isinstance(events, list) or len(events) != 6:
        issues.append("memory evidence must contain six INIT/CHECK events")
        events = events if isinstance(events, list) else []
    observed = set()
    for e in events:
        if not isinstance(e, dict):
            issues.append("invalid memory operation entry")
            continue
        op, method = e.get("operation"), e.get("method")
        pol = next((p for p in POLICIES if EXPECTED_METHODS.get((op, p)) == method), None)
        # 'backdoor' init is shared by fast/hybrid, assigned by deterministic
        # event position, not silently guessed from its access method.
        idx = len(observed)
        if idx < 6:
            mode, op_expected = POLICIES[idx // 2], ("init", "check")[idx % 2]
            if (op, method) != (op_expected, EXPECTED_METHODS[(op_expected, mode)]):
                issues.append(f"memory event {idx}: unexpected operation/method")
        observed.add((idx, op))
        if e.get("bytes") != obj.get("size_bytes") or type(e.get("wall_ns")) is not int or e["wall_ns"] < 0:
            issues.append("memory event bytes/timing invalid")
        if type(e.get("simulated_cycles")) is not int or e["simulated_cycles"] < 0:
            issues.append("memory event lacks valid simulator cycle measurement")
    try:
        address = int(obj["address"], 0)
        size = obj["size_bytes"]
        if type(size) is not int or not 0 < size <= 65536:
            raise ValueError("invalid memory sample size")
    except (ValueError, KeyError, TypeError):
        address, size = 0, 0
        issues.append("memory evidence lacks a valid modeled address/size")
    if obj.get("validation") != "two-way AXI/backdoor proof plus scratch restoration":
        issues.append("backdoor reciprocity proof not recorded")
    if (type(period_ps) is not int or not period_ps > 0 or
            obj.get("clock_period_ps") != period_ps):
        issues.append("memory operation clock disagrees with accepted AXI capture clock")
    # Verify actual accepted and completed traffic through an authorized
    # initiator boundary rather than relying on testbench self-report.
    accepted = [row for row in rows if row.get("role") == "initiator"
                and row.get("status") == "complete"
                and row.get("operation") in ("write", "read")
                and row.get("response") is not None
                and int(row["response"], 0) == 0
                and address <= int(row["address"], 0) < address + size]
    if not any(r["operation"] == "write" for r in accepted):
        issues.append("no accepted completed AXI frontdoor write for memory region")
    if not any(r["operation"] == "read" for r in accepted):
        issues.append("no accepted completed AXI frontdoor read for memory region")
    if not obj.get("route_initiator") or not obj.get("memory_target"):
        issues.append("memory provider route identity missing")
    if len(issues):
        return obj, issues
    return obj, []
