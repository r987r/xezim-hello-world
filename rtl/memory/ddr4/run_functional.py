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
import subprocess
import sys
from xml.etree import ElementTree

from bringup import CORE_NAME, DEFAULT_OUTPUT, checked_output_dir, preflight as current_contract
from check_rtl import generated_sources
from traffic_observer import verify_capture
from latency_report import configured_clock_period_ps, report_from_capture
from dfi_probe_contract import write_control_file
from dfi_latency_report import report_from_dfi
from selective_verilator import run_selective
from warning_audit import audit_file
from dfi_to_protocol import standalone_plan, convert, TARGET

from tools.run_workspace import reserve_run, verify_artifact_inventory
from tools.test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[3]
INPUTS = ("csr.json", "ddr4_init_plan.json")
TEST_CASE = "ddr4_wishbone_init_axi_readwrite"


def preflight(path: Path):
    path = checked_output_dir(path)
    files = generated_sources(path)
    manifest = path / "ddr4_manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("generate the pinned DDR4 RTL and manifest first")
    info = json.loads(manifest.read_text())
    if (info.get("status") != "generated-not-simulated" or info.get("top") != CORE_NAME
            or info.get("source") != current_contract()):
        raise ValueError("DDR4 generation manifest does not match expected isolated top")
    for source in [*(path / name for name in INPUTS), *files]:
        expected = info.get("files_sha256", {}).get(source.relative_to(path).as_posix())
        if source.is_symlink() or not source.is_file() or sha(source.read_bytes()) != expected:
            raise ValueError(f"DDR4 selected source differs from its generator manifest: {source.name}")
    plan = json.loads((path / "ddr4_init_plan.json").read_text())
    if plan.get("status") != "plan-only-not-executed":
        raise ValueError("unexpected upstream DFII initialization plan state")
    return path, files


def provenance() -> dict:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    stamp = {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
             "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
             "workflow_attempt": os.environ.get("GITHUB_RUN_ATTEMPT")}
    if stamp["workflow_run_id"] and (stamp["dirty"] or not stamp["workflow_attempt"]):
        raise ValueError("DDR4 CI run requires clean source and an exact attempt")
    return stamp


def verify_native_execution(build: Path, workspace: Path, sources: list[Path], control: Path):
    """Require original Cocotb success and the actual selected compiler input order."""
    command = json.loads((workspace / "ddr4_compiler_command.json").read_text())
    argv = command.get("argv", [])
    if (command.get("simulator") != "verilator"
            or command.get("global_public_flat_rw") is not False
            or not argv or argv.count("--top-module") != 1 or argv.count("--vpi") != 1
            or argv.count(str(control)) != 1 or "--public-flat-rw" in argv
            or argv.count("-Mdir") != 1 or argv[argv.index("-Mdir")+1:][:1] != [str(build)]
            or argv[argv.index("--top-module")+1:][:1] != [CORE_NAME]
            or argv[-len(sources):] != [str(source) for source in sources]):
        raise ValueError("DDR4 native compiler invocation differs from selected sources or probes")
    candidates = list(build.glob("*_results.xml"))
    if len(candidates) != 1 or candidates[0].is_symlink() or not candidates[0].is_file():
        raise ValueError("DDR4 native Cocotb xUnit result missing or ambiguous")
    data = candidates[0].read_bytes()
    xml = ElementTree.fromstring(data)
    cases = list(xml.iter("testcase"))
    if (len(cases) != 1 or cases[0].get("name") != TEST_CASE
            or cases[0].get("classname") != "functional_tb"
            or any(next(xml.iter(tag), None) is not None
                   for tag in ("failure", "error", "skipped"))
            or any(node.get(key) not in (None, "0")
                   for node in xml.iter() for key in ("failures", "errors", "skipped"))):
        raise ValueError("DDR4 native Cocotb test did not pass")
    with (workspace / "results.xml").open("xb") as output:
        output.write(data)


def prepare_run(input_dir: Path):
    generated, sources = preflight(input_dir)
    stamp = provenance()
    filelist = "".join(str(source) + "\n" for source in sources).encode()
    plan = standalone_plan(CORE_NAME)
    identity = selected(TARGET, plan, filelist_bytes=filelist, root=ROOT)
    workspace = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    plan["identity"] = identity
    with (workspace / "sources.f").open("xb") as output:
        output.write(filelist)
    with (workspace / "plan.json").open("x") as output:
        output.write(json.dumps(plan, indent=2) + "\n")
    for name in (*INPUTS, "ddr4_manifest.json"):
        with (workspace / name).open("xb") as output:
            output.write((generated / name).read_bytes())
    build_root = ROOT / ".tools/ddr4-run-builds"
    if build_root.is_symlink():
        raise ValueError("DDR4 private build root cannot be a symlink")
    build = build_root / identity["run_id"]
    build.mkdir(parents=True, exist_ok=False)
    print("DDR4 standalone run workspace:", workspace, flush=True)
    if path := os.environ.get("GITHUB_OUTPUT"):
        with Path(path).open("a") as output:
            print(f"directory={workspace.relative_to(ROOT)}", file=output)
            print(f"run_id={identity['run_id']}", file=output)
    return generated, sources, workspace, build, stamp, identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help="existing generated LiteDRAM input directory; results use a new run workspace")
    args = parser.parse_args()
    try:
        generated, sources, output, build, stamp, identity = prepare_run(args.output_dir)
        # Leave the generated gateware and its compile evidence at the
        # original location. Only the verified source inputs are read there.
        control_file = write_control_file(
            generated / "gateware" / f"{CORE_NAME}.v",
            output / "ddr4_dfi_probes.vlt",
        )
        here = Path(__file__).resolve().parent
        # Cocotb drives exactly one clock. No duplicate Verilator --timing
        # clock or independent SV clock generator is instantiated.
        run_selective(
            control_file,
            verilog_sources=[str(s) for s in sources],
            toplevel=CORE_NAME,
            module="functional_tb",
            python_search=[str(here)],
            sim_build=str(build),
            extra_env={"DDR4_GENERATED_DIR": str(output)},
            compile_args=["-Wno-fatal", str(control_file)],
            waves=False,
        )
        verify_native_execution(build, output, sources, control_file)
        if (preflight(generated) != (generated, sources) or provenance() != stamp
                or (generated / "ddr4_manifest.json").read_bytes()
                != (output / "ddr4_manifest.json").read_bytes()):
            raise ValueError("DDR4 source selection changed during native execution")
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
        for channel, label in (("r", "RREADY"), ("b", "BREADY")):
            if (capture.get("stall_cycles", {}).get(channel, 0) < 12 or
                    capture.get("max_stall_streak", {}).get(channel, 0) < 8):
                raise ValueError(
                    f"missing real sustained {label} backpressure evidence")
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
                        "identity_sha256": identity["identity_sha256"],
                        "source": stamp,
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
                                    "channels": capture["channels"],
                                    "stall_cycles": capture["stall_cycles"],
                                    "max_stall_streak": capture["max_stall_streak"]},
                        "warning": "Does not prove full-chip DDR or silicon DDR PHY"}, indent=2) + "\n"
        )
        from report_html import load, render
        html = render(load(output))
        if "UNMEASURED" not in html:
            raise ValueError("standalone DDR4 report lost its unmeasured boundaries")
        (output / "ddr4-report.html").write_text(html)
        verify_artifact_inventory(output, identity, [
            "sources.f", "results.xml", "ddr4_compiler_command.json",
            "ddr4_simulation_compiler.log", "ddr4_functional_result.json",
            "ddr4_traffic_events.jsonl", "ddr4_traffic_summary.json",
            "ddr4_dfi_events.jsonl", "ddr4_dfi_summary.json", "ddr4_mrs_evidence.json",
        ])
        convert(output, output, identity=identity)
        print("PASS actual DDR4 standalone Wishbone initialization and AXI integrity")
        return 0
    except (ValueError, OSError, ImportError, RuntimeError, AssertionError,
            subprocess.CalledProcessError, ElementTree.ParseError, KeyError) as exc:
        print(f"FAIL DDR4 functional test: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
