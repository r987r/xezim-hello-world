#!/usr/bin/env python3
"""Reserve evidence for the existing isolated upstream PCIe CI jobs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

if __package__:
    from .run_workspace import reserve_run
    from .test_identity import selected, sha
else:
    from run_workspace import reserve_run
    from test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[1]
LANES = {
    "endpoint": ("cocotb-verilator", "pcie_phy_top", (
        "fusesoc", "--cores-root=.tools/pcie_endpoint_openpcie", "run", "--target=sim",
        "fusesoc:pcie:phy_core:1.0.0")),
    "host": ("verilator", "testpipex1", (
        "make", "-C", ".tools/pcie_host_pcievhost/verilog/testpipex1",
        "-f", "makefile.verilator", "run", "VPROC_TOP=../../../vproc")),
}


def allocate(lane):
    engine, top, argv = LANES[lane]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    env = os.environ
    if env.get("GITHUB_ACTIONS") == "true" or "GITHUB_RUN_ID" in env:
        if (dirty or env.get("GITHUB_SHA") != revision
                or any(not (env.get(k, "").isdecimal() and int(env[k]) > 0)
                       for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
            raise ValueError("upstream PCIe CI requires a clean exact checkout, run and attempt")
    receipt = ROOT / "gen/pcie_link"
    raw = receipt.joinpath("selection.json").read_bytes()
    plan = {"target": f"pcie-upstream-{lane}", "logical_test": f"isolated-{lane}",
            "engine": engine, "sources": "pcie-upstream", "top": top,
            "source_revision": revision, "checkout_dirty": dirty, "cwd": ".",
            "execution_argv": argv, "selection_receipt_sha256": sha(raw),
            "evidence_scope": f"isolated_{lane}_not_chip_or_cross_provider"}
    identity = selected(plan["target"], plan, root=ROOT)
    out = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    out.joinpath("plan.json").write_text(json.dumps({**plan, "identity": identity}, indent=2) + "\n")
    out.joinpath("selection.json").write_bytes(raw)
    shutil.copyfile(receipt / "README.md", out / "README.md")
    with Path(env["GITHUB_OUTPUT"]).open("a") as log:
        print(f"run_dir={out.relative_to(ROOT).as_posix()}", file=log)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("lane", choices=LANES)
    allocate(cli.parse_args().lane)
