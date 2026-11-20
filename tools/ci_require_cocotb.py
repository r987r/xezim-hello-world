#!/usr/bin/env python3
"""Require executed, passing Cocotb tests even when a simulator exits zero.

Use this after FuseSoC/Verilator/Cocotb pipelines: successful elaboration or a
Verilog $finish following a Cocotb import failure must NEVER qualify a test.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

SUMMARY = re.compile(
    r"\bTESTS=(\d+)\s+PASS=(\d+)\s+FAIL=(\d+)\s+SKIP=(\d+)\b"
)
IMPORT_ERRORS = (
    "Failed to import module",
    "CRITICAL cocotb.regression",
    "ERROR    cocotb",
)


def require_passing_cocotb(log: str) -> tuple[int, int]:
    if any(needle in log for needle in IMPORT_ERRORS):
        raise ValueError("Cocotb failed import or initialization")
    matches = SUMMARY.findall(log)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one completed Cocotb summary, observed {len(matches)}"
        )
    tests, passed, failed, skipped = map(int, matches[0])
    if tests < 1 or passed != tests or failed != 0 or skipped != 0:
        raise ValueError(
            f"unqualified Cocotb tests: TESTS={tests} PASS={passed} "
            f"FAIL={failed} SKIP={skipped}"
        )
    return tests, passed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log", type=Path)
    args = ap.parse_args()
    try:
        tests, passed = require_passing_cocotb(args.log.read_text(errors="replace"))
    except (ValueError, OSError) as exc:
        ap.exit(1, f"FAIL: unqualified Cocotb run ({exc})\n")
    print(f"PASS: executed {tests} Cocotb tests, {passed} passed, zero failures/skips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
