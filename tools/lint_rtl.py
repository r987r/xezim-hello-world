#!/usr/bin/env python3
"""Run pinned slang lint and elaboration on Bender-resolved regression profiles.

Default policy: report HDL diagnostics without blocking unrelated work, but
fail the job on missing tools, bad filelists, corrupt reports or tool crashes.
Use --enforce to turn any reported design error into a failing result.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


def select_profiles(root: Path, requested: list[str]) -> list[str]:
    cfg = yaml.safe_load((root / "config/regression.yaml").read_text())
    if cfg.get("schema_version") != 1 or not isinstance(cfg.get("tests"), dict):
        raise ValueError("invalid regression configuration")
    tests = cfg["tests"]
    unknown = sorted(set(requested) - set(tests))
    if unknown:
        raise ValueError(f"unknown lint profiles: {unknown}")
    if requested:
        names = list(dict.fromkeys(requested))
    else:
        # All positive, executable NoC/chip targets; no special cases for CPUs/DMA.
        names = [name for name, test in tests.items()
                 if test.get("sources") == "noc"
                 and test.get("engine") == "cocotb-verilator"
                 and test.get("top") and not test.get("reuse_build")
                 and not test.get("expect_failure")
                 and not test.get("opt_in", False)]
    if not names or any(not isinstance(tests[n].get("top"), str) for n in names):
        raise ValueError("no elaboratable RTL profiles selected")
    return names


def location_parts(value: str, root: Path) -> tuple[str, int | None, int | None]:
    match = re.fullmatch(r"(.+):([0-9]+):([0-9]+)", value)
    if not match:
        return (value, None, None)
    path, line, column = match.groups()
    p = Path(path)
    if p.is_absolute():
        try:
            path = p.relative_to(root.resolve()).as_posix()
        except ValueError:
            path = p.as_posix()
    return path, int(line), int(column)


def parse_diagnostics(path: Path, root: Path, profile: str, mode: str) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"{profile}/{mode}: slang produced no diagnostics JSON")
    try:
        rows = json.loads(path.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{profile}/{mode}: invalid diagnostics JSON") from exc
    if not isinstance(rows, list):
        raise ValueError(f"{profile}/{mode}: unexpected diagnostics schema")
    findings = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("message"), str) or not isinstance(row.get("severity"), str):
            raise ValueError(f"{profile}/{mode}: malformed diagnostic")
        severity = row["severity"].lower()
        if severity in ("fatal", "internal"):
            severity = "error"
        if severity not in ("error", "warning", "note", "info"):
            raise ValueError(f"{profile}/{mode}: unsupported severity {severity!r}")
        file, line, column = location_parts(str(row.get("location", "")), root)
        findings.append({
            "profile": profile, "mode": mode, "severity": severity,
            "code": str(row.get("code", "")),
            "option": str(row.get("optionName", "")),
            "message": row["message"], "file": file, "line": line,
            "column": column, "symbol_path": str(row.get("symbolPath", "")),
            "origin": "vendor" if file.startswith(".tools/") else "project",
            "notes": row.get("notes", []),
        })
    return findings


def verify_plan(root: Path, profile: str, top: str) -> Path:
    directory = root / ".tools/regression" / profile
    filelist, planfile = directory / "sources.f", directory / "plan.json"
    if not filelist.is_file() or not planfile.is_file():
        raise ValueError(f"{profile}: resolved Bender sources missing (run regress.py --stage files)")
    plan = json.loads(planfile.read_text())
    if plan.get("top") != top or plan.get("target") != profile:
        raise ValueError(f"{profile}: plan does not match registered RTL top")
    if not plan.get("sources") or not isinstance(plan.get("sources"), list):
        raise ValueError(f"{profile}: no Bender-resolved RTL sources")
    return filelist


def annotate(findings: list[dict], limit: int = 40) -> None:
    total = 0
    for row in findings:
        if row["severity"] not in ("warning", "error"):
            continue
        if total >= limit:
            break
        level = "error" if row["severity"] == "error" else "warning"
        props = []
        if row["file"] and not Path(row["file"]).is_absolute():
            props.append("file=" + row["file"].replace(",", "%2C"))
            if row["line"]:
                props.append(f"line={row['line']}")
            if row["column"]:
                props.append(f"col={row['column']}")
        escaped = (row["message"].replace("%", "%25").replace("\n", "%0A")
                   .replace("\r", "%0D"))
        code = row["code"]
        print(f"::{level} {','.join(props)}::{code}: {escaped}", flush=True)
        total += 1
    if len(findings) > total:
        print(f"Additional lint diagnostics are in the uploaded JSON reports ({len(findings)} total).")


def analyze(root: Path, profile: str, top: str, binary: str, outdir: Path,
            *, enforce: bool = False, execute=subprocess.run) -> dict:
    files = verify_plan(root, profile, top)
    outdir.mkdir(parents=True, exist_ok=True)
    modes = ("lint", "elaborate")
    results = []
    all_findings = []
    for mode in modes:
        diagnostic = outdir / f"{mode}.raw.json"
        transcript = outdir / f"{mode}.log"
        if diagnostic.exists():
            diagnostic.unlink()
        command = [binary, "--top", top, "-f", str(files),
                   "--diag-json", str(diagnostic), "--error-limit", "0"]
        if mode == "lint":
            command.append("--lint-only")
        try:
            run = execute(command, cwd=root, capture_output=True, text=True, timeout=300,
                          check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"{profile}/{mode}: slang infrastructure failure: {exc}") from exc
        transcript.write_text("command: " + " ".join(command) + "\n\n"
                              + run.stdout + "\n" + run.stderr)
        if run.returncode != 0 and not diagnostic.is_file():
            raise ValueError(f"{profile}/{mode}: slang failed without design diagnostics "
                             f"(code={run.returncode}): {run.stderr[-1500:]}")
        findings = parse_diagnostics(diagnostic, root, profile, mode)
        errors = sum(row["severity"] == "error" for row in findings)
        # A nonzero exit without a structured design error is a tool failure;
        # never mark a segfault or broken invocation as a lint finding.
        if run.returncode < 0 or (run.returncode != 0 and not errors):
            raise ValueError(f"{profile}/{mode}: slang failed without design diagnostics "
                             f"(code={run.returncode}): {run.stderr[-1500:]}")
        if run.returncode == 0 and errors:
            raise ValueError(f"{profile}/{mode}: inconsistent slang exit status and diagnostics")
        results.append({"mode": mode, "exit_code": run.returncode,
                        "passed": run.returncode == 0,
                        "counts": dict(Counter(f["severity"] for f in findings)),
                        "diagnostics": diagnostic.name, "log": transcript.name})
        all_findings.extend(findings)
    digest = hashlib.sha256(files.read_bytes()).hexdigest()
    report = {"schema_version": 1, "profile": profile, "top": top,
              "producer": "slang", "source": "bender_resolved_regression_filelist",
              "filelist_sha256": digest, "modes": results,
              "findings": all_findings,
              "policy": "enforce" if enforce else "report_only",
              "report_timestamp": datetime.now(timezone.utc).isoformat(),
              "summary": dict(Counter(row["severity"] for row in all_findings))}
    (outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    annotate(all_findings)
    print(f"LINT {profile}: {len(all_findings)} findings "
          f"({report['summary'].get('error', 0)} errors, "
          f"{report['summary'].get('warning', 0)} warnings), "
          f"report={outdir}/report.json", flush=True)
    return report


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("profiles", nargs="*")
    cli.add_argument("--root", type=Path, default=ROOT)
    cli.add_argument("--slang", default=os.getenv("SLANG_BIN", "slang"))
    cli.add_argument("--output", type=Path)
    cli.add_argument("--enforce", action="store_true")
    cli.add_argument("--list", action="store_true")
    args = cli.parse_args()
    root = args.root.resolve()
    cfg = yaml.safe_load((root / "config/regression.yaml").read_text())
    profiles = select_profiles(root, args.profiles)
    if args.list:
        print("\n".join(profiles))
        return 0
    binary = shutil.which(args.slang)
    if not binary:
        raise ValueError(f"slang executable not found: {args.slang}")
    out = args.output or (root / ".tools/lint")
    reports = []
    errors = 0
    # Continue across design-level errors so all profiles have evidence.
    for profile in profiles:
        top = cfg["tests"][profile]["top"]
        report = analyze(root, profile, top, binary, out / profile, enforce=args.enforce)
        reports.append({"profile": profile, "top": top,
                        "errors": report["summary"].get("error", 0),
                        "warnings": report["summary"].get("warning", 0),
                        "elaboration_passed": report["modes"][1]["passed"]})
        errors += report["summary"].get("error", 0)
    combined = {"schema_version": 1, "policy": "enforce" if args.enforce else "report_only",
                "profiles": reports, "total_errors": errors,
                "total_warnings": sum(p["warnings"] for p in reports)}
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(combined, indent=2) + "\n")
    print(f"SLANG lint complete: {len(reports)} profiles, {errors} errors, "
          f"{combined['total_warnings']} warnings; policy={combined['policy']}", flush=True)
    return 1 if args.enforce and errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(f"Lint infrastructure failed: {exc}")
