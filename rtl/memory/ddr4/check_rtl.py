#!/usr/bin/env python3
"""Isolated DDR4 generated-RTL compile diagnostic, without shared CI changes.

Requires bringup.py generate and a preinstalled Verilator and/or Xezim.
Compilation is not initialization and not functional memory traffic.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bringup import CORE_NAME, DEFAULT_OUTPUT, checked_output_dir

ENGINES = ("verilator", "xezim")


def generated_sources(output: Path) -> list[Path]:
    """Select actual generated Verilog only; no collateral from other IPs."""
    output = checked_output_dir(output)
    gateware = output / "gateware"
    sources = sorted(gateware.glob("*.v")) + sorted(gateware.glob("*.sv"))
    core = gateware / f"{CORE_NAME}.v"
    if not core.is_file():
        raise ValueError(f"generate the pinned DDR4 controller first: missing {core}")
    if core not in sources:
        raise ValueError(f"missing generated top source in {gateware}")
    if not sources:
        raise ValueError(f"no generated HDL in {gateware}")
    if any(not p.is_file() or p.is_symlink() or gateware.resolve() not in p.resolve().parents
           for p in sources):
        raise ValueError("unsafe or missing generated HDL path")
    return sources


def compile_command(engine: str, tool: str, sources_file: Path) -> list[str]:
    if engine == "verilator":
        return [tool, "--lint-only", "--timing", "-Wno-fatal",
                "--top-module", CORE_NAME, "-f", str(sources_file)]
    if engine == "xezim":
        return [tool, "--compile", "--no-cache", "-s", CORE_NAME,
                "-f", str(sources_file)]
    raise ValueError(f"unknown DDR4 RTL engine {engine}")


def execute(engine: str, output: Path, filelist: Path, timeout: int) -> dict:
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine}")
    override = os.environ.get("XEZIM_BIN") if engine == "xezim" else None
    tool = override or shutil.which(engine)
    log = output / f"{engine}.log"
    info = {"engine": engine, "status": "failed", "log": str(log), "pass": False}
    if not tool or not Path(tool).is_file():
        log.write_text(f"Missing {engine} executable: XEZIM_BIN or PATH is required.\n")
        info["reason"] = "tool-not-installed"
        return info
    command = compile_command(engine, tool, filelist)
    info["argv"] = command
    try:
        with log.open("w") as handle:
            cp = subprocess.run(command, cwd=output, stdout=handle,
                                stderr=subprocess.STDOUT, check=False, timeout=timeout)
        info["exit_code"] = cp.returncode
        info["pass"] = cp.returncode == 0
        info["status"] = "compile-passed" if cp.returncode == 0 else "compile-failed"
    except subprocess.TimeoutExpired:
        info["reason"] = "compile-timeout"
        with log.open("a") as handle:
            handle.write(f"\nTIMEOUT after {timeout}s\n")
    return info


def run(output: Path, engines: list[str], timeout: int) -> dict:
    output = checked_output_dir(output)
    sources = generated_sources(output)
    manifest = output / "ddr4_manifest.json"
    if not manifest.is_file():
        raise ValueError(f"missing generated RTL provenance manifest: {manifest}")
    evidence = json.loads(manifest.read_text())
    if evidence.get("status") != "generated-not-simulated" or evidence.get("top") != CORE_NAME:
        raise ValueError("generated manifest does not match the expected DDR4 top")
    files = output / "ddr4_sources.f"
    files.write_text("".join(str(s.resolve()) + "\n" for s in sources))
    results = [execute(engine, output, files, timeout) for engine in engines]
    summary = {
        "status": "isolated-rtl-compile-diagnostic",
        "top": CORE_NAME,
        "sources": [str(s.relative_to(output)) for s in sources],
        "results": results,
        "all_passed": all(r["pass"] for r in results),
        "warning": "Compile/lint is not DDR controller initialization or AXI traffic",
    }
    (output / "ddr4_compile_results.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tool", choices=("verilator", "xezim", "both"), default="both")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    engines = list(ENGINES) if args.tool == "both" else [args.tool]
    try:
        summary = run(args.output_dir, engines, args.timeout)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"DDR4 RTL compile preflight failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
