"""Fail-closed DDR4 generated-Verilog warning baseline, not a blanket waiver.

The pinned LiteDRAM/Migen 32-MiB simulation profile already emits these
diagnostic families. Both CI lint and simulation must preserve all raw logs.
A successful process exit (including -Wno-fatal) is never sufficient.
Future revisions must investigate/approve any changed diagnostic inventory.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

# Measured in the upstream-generated RTL at PR #24/#26 on Verilator 5.020.
# REVIEWED AS EXISTING, not claimed harmless: especially DFI address narrowing.
PINNED_BASELINE = {
    "WIDTHEXPAND": 1709,
    "WIDTHTRUNC": 254,
    "CASEINCOMPLETE": 84,
}
WARNING_RE = re.compile(r"%Warning-([A-Z][A-Z0-9_-]+):")
ERROR_RE = re.compile(r"%Error(?:-[A-Z][A-Z0-9_-]+)?:")
UNKNOWN_WARNING_RE = re.compile(r"%Warning(?!-[A-Z][A-Z0-9_-]+:)")


def assess(text: str, baseline: dict | None = None) -> dict:
    expected = PINNED_BASELINE if baseline is None else baseline
    observed = dict(sorted(Counter(WARNING_RE.findall(text)).items()))
    errors = ERROR_RE.findall(text)
    unknown = len(UNKNOWN_WARNING_RE.findall(text))
    differences = {key: {"expected": expected.get(key, 0), "actual": observed.get(key, 0)}
                   for key in sorted(set(expected) | set(observed))
                   if expected.get(key, 0) != observed.get(key, 0)}
    # This is intentionally exact-count matching, not an ignore/disable rule.
    # CI keeps the original diagnostic log for investigating every change.
    passed = bool(observed) and not errors and not unknown and not differences
    return {
        "status": "pass" if passed else "fail",
        "baseline": "pinned-litedram-sim-verilator-5.020",
        "observed": observed,
        "expected": expected,
        "total_warnings": sum(observed.values()),
        "verilator_errors": len(errors),
        "unrecognized_warnings": unknown,
        "changes": differences,
        "warning": "Existing widths/case warnings remain open for semantic review; matching does not prove RTL correctness.",
    }


def audit_file(path: Path, output: Path, baseline: dict | None = None) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError("DDR4 compiler diagnostic log is missing or unsafe")
    report = assess(path.read_text(errors="replace"), baseline)
    output.write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "pass":
        raise ValueError("DDR4 compiler diagnostics changed or include errors: "
                         + json.dumps({"changes": report["changes"],
                                       "errors": report["verilator_errors"],
                                       "unknown": report["unrecognized_warnings"]}))
    return report
