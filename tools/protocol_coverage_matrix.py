"""Coverage accounting over *existing* protocol_report.build JSON output.

This module never samples pins, drives BFMs or fabricates latency metrics.
It reports incomplete/missing protocol observations as explicit gaps.
"""
from collections import Counter


def summarize(report, required_protocols):
    if report.get("schema_version") != 1 or not isinstance(report.get("sources"), list) or not isinstance(report.get("records"), list):
        raise ValueError("invalid protocol-report schema")
    declared = {}
    for item in report["sources"]:
        name, protocol = item.get("id"), item.get("protocol")
        if not isinstance(name, str) or not name or not isinstance(protocol, str) or not protocol:
            raise ValueError("invalid protocol monitor catalog")
        if name in declared:
            raise ValueError("duplicate monitor ID")
        declared[name] = protocol
    counts = Counter()
    incomplete = []
    for row in report["records"]:
        source = row.get("source")
        if source not in declared:
            raise ValueError("record from undeclared protocol source")
        if row.get("protocol") != declared[source]:
            raise ValueError("monitor changed protocol")
        counts[declared[source]] += 1
        if row.get("kind") == "transaction":
            if row.get("status") != "complete" or row.get("end_ps") is None:
                incomplete.append(source)
            elif row.get("start_ps") is None or row["end_ps"] < row["start_ps"]:
                raise ValueError("invalid completed transaction times")
    required = set(required_protocols)
    if not all(isinstance(p, str) and p for p in required):
        raise ValueError("invalid required protocol")
    missing = sorted(required - {p for p, n in counts.items() if n > 0})
    issues = list(report.get("issues") or [])
    if not report.get("capture_complete"):
        issues.append("source capture was not closed cleanly")
    return {"status": "coverage_complete" if not (missing or incomplete or issues) else "coverage_missing",
            "observed_by_protocol": dict(sorted(counts.items())),
            "declared_protocols": sorted(set(declared.values())),
            "missing_required_protocols": missing,
            "incomplete_sources": sorted(set(incomplete)),
            "source_capture_issues": issues,
            "provenance": "existing_protocol_report_observations_only"}


def require_coverage(result):
    if result["status"] != "coverage_complete":
        raise AssertionError("required real monitor coverage missing: " + str(result))
    return result
