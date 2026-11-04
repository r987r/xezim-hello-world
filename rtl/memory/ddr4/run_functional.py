#!/usr/bin/env python3
"""Isolated real-LiteDRAM Cocotb/Verilator regression; no chip boot dependencies.

Requires prior bringup.py generate. Does not change shared NoC generators,
boot firmware, memory topology, or generator-owned gen/ directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from bringup import CORE_NAME, DEFAULT_OUTPUT, checked_output_dir
from check_rtl import generated_sources
from traffic_observer import clear_prior_capture, verify_capture
from latency_report import configured_clock_period_ps, report_from_capture
from dfi_probe_contract import write_control_file
from dfi_latency_report import report_from_dfi
from selective_verilator import run_selective
from warning_audit import audit_file


def preflight(path: Path):
    path = checked_output_dir(path)
    files = generated_sources(path)
    manifest = path / "ddr4_manifest.json"
    if not manifest.is_file():
        raise ValueError("generate the pinned DDR4 RTL and manifest first")
    info = json.loads(manifest.read_text())
    if info.get("status") != "generated-not-simulated" or info.get("top") != CORE_NAME:
        raise ValueError("DDR4 generation manifest does not match expected isolated top")
    for name in ("csr.json", "ddr4_init_plan.json"):
        if not (path / name).is_file():
            raise ValueError(f"missing upstream-generated {name}")
    plan = json.loads((path / "ddr4_init_plan.json").read_text())
    if plan.get("status") != "plan-only-not-executed":
        raise ValueError("unexpected upstream DFII initialization plan state")
    return path, files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        output, sources = preflight(args.output_dir)
        # Stale summaries or traces from earlier local runs must never let a
        # new run pass if the observer was omitted or failed to initialize.
        clear_prior_capture(output)
        latency_file = output / 'ddr4_latency.json'
        if latency_file.exists():
            if latency_file.is_symlink() or not latency_file.is_file():
                raise ValueError('invalid DDR4 latency artifact path')
            latency_file.unlink()
        # Selective Verilator VPI exposure: only pinned DFI and bank activity
        # nets, never the large memory arrays and never vendor RTL edits.
        control_file = write_control_file(
            output / "gateware" / f"{CORE_NAME}.v",
            output / "ddr4_dfi_probes.vlt",
        )
        for name in ("ddr4_dfi_events.jsonl", "ddr4_dfi_summary.json",
                     "ddr4_internal_latency.json"):
            item = output / name
            if item.is_symlink():
                raise ValueError(f"invalid stale DFI artifact symlink: {name}")
            if item.is_file():
                item.unlink()
        here = Path(__file__).resolve().parent
        # Cocotb drives exactly one clock. No duplicate Verilator --timing
        # clock or independent SV clock generator is instantiated.
        run_selective(
            control_file,
            verilog_sources=[str(s) for s in sources],
            toplevel=CORE_NAME,
            module="functional_tb",
            python_search=[str(here)],
            sim_build=str(output / "functional_sim_build"),
            extra_env={"DDR4_GENERATED_DIR": str(output)},
            compile_args=["-Wno-fatal", str(control_file)],
            waves=False,
        )
        # -Wno-fatal permits pinned upstream warnings but never hides them.
        diagnostics = audit_file(
            output / "ddr4_simulation_compiler.log",
            output / "ddr4_warning_audit.json")
        print("DDR4 Verilator diagnostics: " +
              json.dumps({"warnings": diagnostics["observed"],
                          "errors": diagnostics["verilator_errors"],
                          "status": diagnostics["status"]}), flush=True)
        # Independent post-run check: the protocol test is not enough to
        # claim a pass if passive capture was disabled, truncated or stopped.
        capture = verify_capture(output)
        latency = report_from_capture(output, configured_clock_period_ps())
        internal = report_from_dfi(output, configured_clock_period_ps())
        stage_digest = {
            name: {"status": detail["status"],
                   "samples": detail.get("samples", 0),
                   "avg_cycles": detail.get("avg_cycles")}
            for name, detail in internal["internal_stages"].items()
        }
        print("DDR4 measured internal stages: " +
              json.dumps(stage_digest, sort_keys=True), flush=True)
        (output / "ddr4_functional_result.json").write_text(
            json.dumps({"status": "pass", "top": CORE_NAME,
                        "scope": "isolated LiteDRAM generated RTL/DFI model",
                        "latency": {"status": "measured_axi_and_modeled_dfi",
                                    "file": "ddr4_latency.json",
                                    "internal_file": "ddr4_internal_latency.json",
                                    "internal_status": internal["status"],
                                    "reads": latency["measured"]["read"]["samples"],
                                    "writes": latency["measured"]["write"]["samples"]},
                        "compiler_diagnostics": {"status": diagnostics["status"],
                                                 "file": "ddr4_warning_audit.json",
                                                 "warnings": diagnostics["total_warnings"]},
                        "monitor": {"status": capture["status"],
                                    "sampled_cycles": capture["sampled_cycles"],
                                    "phases": capture["phases"],
                                    "channels": capture["channels"]},
                        "warning": "Does not prove full-chip DDR or silicon DDR PHY"}, indent=2) + "\n"
        )
        print("PASS actual DDR4 standalone Wishbone initialization and AXI integrity")
        return 0
    except (ValueError, OSError, ImportError, RuntimeError, AssertionError) as exc:
        print(f"FAIL DDR4 functional test: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
