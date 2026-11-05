"""Deduplicate pinned slang lint/compile diagnostics without hiding failures.

Consumes existing tools/lint_rtl.py report.json findings. Original raw errors
and warnings remain published; this report is grouping evidence for #32.
"""
import json
from collections import Counter
from pathlib import Path


def deduplicate(reports):
    raw = Counter()
    unique = {}
    profiles = set()
    for report in reports:
        if report.get("schema_version") != 1 or not isinstance(report.get("findings"), list):
            raise ValueError("expected slang lint report schema v1")
        profile = report.get("profile")
        if not isinstance(profile, str) or not profile:
            raise ValueError("lint report missing profile")
        profiles.add(profile)
        for item in report["findings"]:
            if not isinstance(item, dict) or item.get("severity") not in ("error", "warning", "note", "info"):
                raise ValueError("invalid lint finding")
            code = str(item.get("code", ""))
            file = str(item.get("file", ""))
            line = item.get("line")
            symbol = str(item.get("symbol_path", ""))
            if line is not None and (type(line) is not int or line < 1):
                raise ValueError("invalid lint location")
            key = (code, file, line, symbol)
            raw[(profile, item["severity"])] += 1
            group = unique.setdefault(key, {"code": code, "file": file, "line": line,
                                            "symbol_path": symbol, "modes": set(),
                                            "profiles": set(), "severities": set(),
                                            "messages": set(), "occurrences": 0})
            group["profiles"].add(profile)
            group["modes"].add(str(item.get("mode", "unknown")))
            group["severities"].add(item["severity"])
            group["messages"].add(str(item.get("message", "")))
            group["occurrences"] += 1
    rows = []
    for value in unique.values():
        rows.append({**value, **{k: sorted(value[k]) for k in
                                  ("modes", "profiles", "severities", "messages")}})
    rows.sort(key=lambda v: (v["file"], v["line"] or 0, v["code"], v["symbol_path"]))
    return {"schema_version": 1, "scope": "deduplicated_diagnostics_not_fixed",
            "profiles": sorted(profiles), "raw_counts": [
                {"profile": p, "severity": s, "count": n}
                for (p, s), n in sorted(raw.items())],
            "unique_count": len(rows), "findings": rows}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = deduplicate([json.loads(p.read_text()) for p in args.reports])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
