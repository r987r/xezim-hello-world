#!/usr/bin/env python3
"""Run actual selected Verilator CPU cold-boot RTL for each compiled SoC.

The shared generated full_chip_tb checks firmware ROM->SRAM copies, CPU
INIT/RUN/CHECK mailboxes and genuine CPU fetches. This does not exercise
Ethernet/PCIe IP or qualify DMA->DDR payload traffic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
PHASES = (
    "PHASE init complete: all CPUs ready",
    "PHASE run complete: all CPUs greeted",
    "PHASE check complete: coordinator observed all peer checks",
)


class ProjectSmokeError(RuntimeError):
    pass


def check_native_boot_log(stdout: str, cores: int) -> dict:
    """Do not mistake compilation, a partial boot or another chip for PASS."""
    if type(cores) is not int or cores < 1:
        raise ProjectSmokeError("invalid selected CPU count")
    lines = [line.strip() for line in stdout.splitlines()]
    positions = []
    for phase in PHASES:
        found = [i for i, line in enumerate(lines) if line == phase]
        if len(found) != 1:
            raise ProjectSmokeError(f"missing/duplicated native RTL phase: {phase}")
        positions.append(found[0])
    if not positions[0] < positions[1] < positions[2]:
        raise ProjectSmokeError("native RTL boot phases out of order")
    for idx in range(cores):
        label = f"hello world from CPU{idx} (firmware mailbox)"
        found = [i for i, line in enumerate(lines) if line == label]
        if len(found) != 1 or not positions[0] < found[0] < positions[1]:
            raise ProjectSmokeError(f"CPU{idx} missing, duplicate or out-of-phase firmware greeting")
    if sum(bool(re.fullmatch(r"hello world from CPU\d+ \(firmware mailbox\)", line))
           for line in lines) != cores:
        raise ProjectSmokeError("native RTL executed extra/unselected CPU")
    pass_line = f"PASS fullchip: {cores} real CPUs, shared NoCs, cold boot, init/run/check"
    accepted = [i for i, line in enumerate(lines) if line == pass_line]
    if len(accepted) != 1 or accepted[0] <= positions[-1]:
        raise ProjectSmokeError("missing/duplicated selected real RTL full-chip PASS")
    if any(line.startswith("PASS fullchip:") and line != pass_line for line in lines):
        raise ProjectSmokeError("another chip's PASS found in native output")
    if any("FAIL fullchip" in line or "%Error" in line for line in lines):
        raise ProjectSmokeError("simulator log contains fatal diagnostic")
    return {
        "observed_cores": cores,
        "observed_greetings": list(range(cores)),
        "init_run_check": True,
        "dut_checker_pass": True,
    }


def run(project_id: str, *, verilator: str = "verilator",
        build_timeout: int = 1200, sim_timeout: int = 300) -> Path:
    # Shared source selector; never load gen/chip for a different project.
    import project_catalog
    from project_compile import selected

    catalog = {p["id"]: p for p in project_catalog.projects(ROOT)}
    project = catalog.get(project_id)
    if project is None:
        raise ProjectSmokeError("unknown project ID; no default-project fallback")
    if project["qualification"] not in ("generated_default", "ci_generated_compiled"):
        raise ProjectSmokeError("source-only project cannot claim a functional run")

    chip_dir, selected_build = selected(project_id)
    compiler = chip_dir / "compile-result.json"
    if not compiler.is_file():
        raise ProjectSmokeError("run project_compile.py before native simulation")
    compiled = json.loads(compiler.read_text())
    if (compiled.get("project_id") != project_id
            or compiled.get("compile_status") != "cpp_build_passed"
            or not compiled.get("compiled_cpp")
            or compiled.get("filelist_sha256") != selected_build["filelist_sha256"]):
        raise ProjectSmokeError("selected-source compiled RTL receipt missing/mismatched")
    soc = yaml.safe_load((ROOT / project["config"]).read_text())
    cores = [s for s in soc["subsystems"] if s["type"] == "compute"]
    if not cores or project_id != soc["name"]:
        raise ProjectSmokeError("invalid selected CPU and project identity")

    out = ROOT / ".tools" / "project-smoke" / project_id
    out.mkdir(parents=True, exist_ok=True)
    object_dir = out / "obj_dir"
    filelist = ROOT / selected_build["filelist"]
    report_file = out / "result.json"
    report = {
        "schema_version": 1,
        "project_id": project_id,
        "test": "native-selected-real-cpu-cold-boot",
        "engine": "verilator-native",
        "source_config": project["config"],
        "source_config_sha256": project["config_sha256"],
        "filelist_sha256": selected_build["filelist_sha256"],
        "cpu_count": len(cores),
        "status": "failed",
        "actual_traffic_scope": "selected RTL CPU ROM/flash/SRAM boot and coordination",
        "ddr_data_qualified": False,
        "pcie_qualified": False,
        "ethernet_qualified": False,
    }
    build_cmd = [verilator, "--binary", "--timing", "-Wno-fatal", "-j", "2",
                 "--top-module", "full_chip_tb", "--Mdir", str(object_dir),
                 "-f", str(filelist)]
    try:
        built = subprocess.run(build_cmd, cwd=ROOT, capture_output=True, text=True,
                               errors="replace", timeout=build_timeout, check=False)
        (out / "native-build.log").write_text(
            "$ " + " ".join(build_cmd) + "\n" + built.stdout + built.stderr)
        if built.returncode != 0:
            raise ProjectSmokeError(f"native Verilator build exited {built.returncode}")
        executable = object_dir / "Vfull_chip_tb"
        if not executable.is_file():
            raise ProjectSmokeError("Verilator did not produce selected simulation executable")
        simulated = subprocess.run([str(executable)], cwd=ROOT,
                                   capture_output=True, text=True,
                                   errors="replace", timeout=sim_timeout, check=False)
        log = simulated.stdout + simulated.stderr
        (out / "native-sim.log").write_text(log)
        report["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        report["simulation_returncode"] = simulated.returncode
        if simulated.returncode != 0:
            raise ProjectSmokeError(f"native RTL simulation failed with exit {simulated.returncode}")
        report["observations"] = check_native_boot_log(log, len(cores))
        report["status"] = "passed"
    except subprocess.TimeoutExpired as exc:
        report["error"] = "bounded native compile/simulation timeout: " + str(exc)
        raise ProjectSmokeError(report["error"]) from exc
    except ProjectSmokeError as exc:
        report["error"] = str(exc)
        raise
    finally:
        report_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report_file


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True)
    p.add_argument("--verilator", default="verilator")
    args = p.parse_args()
    try:
        result = run(args.project, verilator=args.verilator)
    except ProjectSmokeError as error:
        print("FAIL selected RTL cold boot:", error, file=sys.stderr)
        return 1
    print("PASS selected RTL cold boot:", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
