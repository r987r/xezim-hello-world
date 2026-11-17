#!/usr/bin/env python3
"""Project-selected RTL Cocotb AXI4 traffic using existing shared runner.

The selected Bender/FlooGen source filelist is reused byte-for-byte.
No new testbench RTL, bus model, or project-specific name branching.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from xml.etree import ElementTree

from project_compile import selected
from regress import parse_filelist
from sim_cocotb import main as simulate_cocotb

ROOT = Path(__file__).resolve().parents[1]


class ProjectAxiError(RuntimeError):
    pass


def selected_plan(project: str) -> tuple[Path, Path]:
    chip_dir, compilation = selected(project)
    receipt_path = chip_dir / "compile-result.json"
    if not receipt_path.is_file():
        raise ProjectAxiError("selected chip has no verified C++ compile receipt")
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("project_id") != project
            or receipt.get("filelist_sha256") != compilation["filelist_sha256"]
            or receipt.get("compile_status") != "cpp_build_passed"):
        raise ProjectAxiError("selected chip compile receipt does not match")
    from project_catalog import projects
    catalog = {p["id"]: p for p in projects(ROOT)}
    if catalog[project]["qualification"] not in ("generated_default", "ci_generated_compiled"):
        raise ProjectAxiError("source-only project cannot run hardware")
    filelist = ROOT / compilation["filelist"]
    sources, includes, defines = parse_filelist(filelist.read_text())
    # Same source closure as Verilator compile; only adds Cocotb guards.
    if "COCOTB_SIM" not in defines:
        defines.append("COCOTB_SIM=1")
    out = ROOT / ".tools/project-axi" / project
    out.mkdir(parents=True, exist_ok=True)
    plan = {
        "project_id": project,
        "sources": sources,
        "includes": includes,
        "defines": defines,
        "top": "full_chip_tb",
        "module": "dv.full_chip.test_project_axi",
        "test_dir": ".",
        "build": str(out / "obj_dir"),
        "results_xml": str(out / "results.xml"),
        "args": [],
        "seed": 1,
        "stage": "simulate",
    }
    plan_path = out / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return plan_path, out


def run(project: str) -> Path:
    plan, out = selected_plan(project)
    os.environ["SOC_PROJECT_ID"] = project
    simulate_cocotb(plan)
    xml = out / "results.xml"
    report = out / "axi-result.json"
    if not xml.is_file() or not report.is_file():
        raise ProjectAxiError("selected Cocotb XML or byte-witness artifact missing")
    tests = ElementTree.parse(xml).findall(".//testcase")
    if (len(tests) != 1 or any(
            any(t.find(tpe) is not None for tpe in ("error", "failure", "skipped"))
            for t in tests)):
        raise ProjectAxiError("project AXI simulation did not complete exactly one test")
    observed = json.loads(report.read_text())
    chip = json.loads((ROOT / ".tools/projects" / project / "chip/manifest.json").read_text())
    expected_targets = {m["name"] for m in chip["memory_models"]}
    got = {m["target"] for m in observed.get("memory", [])}
    if (observed.get("project_id") != project
            or not observed.get("actual_axi_readback")
            or expected_targets != got
            or any(m["bytes_checked"] != 32 for m in observed["memory"])
            or observed.get("real_ddr_controller_qualified") is not False):
        raise ProjectAxiError("memory RTL byte evidence incomplete or wrong project")
    observed["source_filelist_sha256"] = hashlib.sha256(
        (ROOT / ".tools/projects" / project / "chip/sources.f").read_bytes()).hexdigest()
    observed["status"] = "passed"
    report.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        print("PASS selected real AXI4 readback:", run(args.project))
        return 0
    except (ProjectAxiError, RuntimeError, ValueError, OSError) as exc:
        print(f"FAIL selected project AXI readback: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
