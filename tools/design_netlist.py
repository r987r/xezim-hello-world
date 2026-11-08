#!/usr/bin/env python3
"""Fail-closed per-profile slang-netlist / slang-report export.

Reuses .tools/regression/PROFILE/sources.f produced by tools/regress.py.
No floating toolchain download and no fallback to guessed connectivity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from selected_rtl_provenance import selected, public_fields

ROOT = Path(__file__).resolve().parents[1]


def analyze(root: Path, profile: str, mode: str, output: Path,
            *, netlist_binary: str = "slang-netlist",
            report_binary: str = "slang-report") -> dict:
    root = root.resolve()
    if mode not in ("netlist", "ports", "drivers", "variables"):
        raise ValueError(f"unsupported export mode: {mode}")
    attested = selected(root, profile)
    source_list = attested["source_list"]
    executable = shutil.which(netlist_binary if mode == "netlist" else report_binary)
    if not executable:
        raise ValueError("slang source-built binary not found (no fake report or fallback)")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()  # Prevent stale successful output after tool failure.
    args = [executable, "--top", attested["top"], "-f", str(source_list)]
    if mode == "netlist":
        args += ["--save-netlist", str(output)]
    else:
        args += ["--" + mode, "--format", "json"]
    run = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=600,
                         check=False)
    if run.returncode:
        if output.exists():
            output.unlink()
        raise ValueError(f"{mode} failed for {profile} (exit {run.returncode}):\n"
                         + (run.stderr + "\n" + run.stdout)[-6000:])
    if mode != "netlist":
        output.write_text(run.stdout)
    if not output.is_file() or not output.stat().st_size:
        raise ValueError(f"{mode} returned no nonempty output for {profile}")
    try:
        report = json.loads(output.read_text())
    except (ValueError, UnicodeDecodeError) as exc:
        output.unlink()
        raise ValueError(f"{mode}: tool emitted invalid JSON") from exc
    if not isinstance(report, (dict, list)):
        output.unlink()
        raise ValueError(f"{mode}: unexpected top-level output")
    meta = {**public_fields(attested), "mode": mode,
            "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "evidence": "elaborated_slang_netlist_inputs_attested",
            "output": str(output), "command": args,
            "tool_diagnostics": run.stderr.splitlines()}
    (output.parent / (output.name + ".meta.json")).write_text(
        json.dumps(meta, indent=2) + "\n")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--mode", choices=["netlist", "ports", "drivers", "variables"],
                        default="ports")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--slang-netlist", default="slang-netlist")
    parser.add_argument("--slang-report", default="slang-report")
    args = parser.parse_args()
    result = analyze(args.root, args.profile, args.mode, args.output,
                     netlist_binary=args.slang_netlist, report_binary=args.slang_report)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
