#!/usr/bin/env python3
"""Archive the existing isolated PCIe Icarus transcripts, not a chip verdict."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

if __package__:
    from .run_workspace import reserve_run
    from .test_identity import selected, sha
else:
    from run_workspace import reserve_run
    from test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[1]
LANES = {
    "device-prelink": ("tb_endpoint_prelink_ctrl", ("endpoint_prelink_ctrl", "tb_endpoint_prelink_ctrl"), (
        b"PASS: device BAR size/target",
        b"PASS: CPU DBI aliases mirror original host BAR0/MSE",
    )),
    "host-bar0": ("tb_pcie_bar0_host_cfg", ("pcie_bar0_host_cfg", "tb_pcie_bar0_host_cfg"), (
        b"PASS: real AXI-Lite host BAR0",
    )),
    "phy-response": ("tb_pcie_phy_status_responder", ("phy_status_responder", "tb_phy_status_responder"), (
        b"PASS: Gen1 receiver-detect",
    )),
    "bar0-complete-span": ("tb_bar0_noc_translate", ("bar0_noc_translate", "tb_bar0_noc_translate"), (
        b"PASS: BAR0 bus/local-NoC complete-span mapping",
    )),
}


def execute(lane, *, root=ROOT, env=None):
    root = Path(root).resolve()
    env = os.environ if env is None else env
    top, source_names, markers = LANES[lane]
    family = "pcie-bar-window" if lane == "bar0-complete-span" else "pcie-prelink"
    sources = [f"dv/pcie_link/{name}.sv" for name in source_names]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))
    if env.get("GITHUB_ACTIONS") == "true" or "GITHUB_RUN_ID" in env:
        if (dirty or env.get("GITHUB_SHA") != revision
                or any(not (env.get(key, "").isdecimal() and int(env[key]) > 0)
                       for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
            raise ValueError("PCIe unit CI requires a clean exact checkout, run, and attempt")

    filelist = ("\n".join(sources) + "\n").encode()
    plan = {"target": f"{family}-{lane}", "logical_test": lane, "top": top,
            "engine": "icarus", "sources": family, "source_revision": revision,
            "checkout_dirty": dirty, "evidence_scope": "isolated_unit_transcripts_only",
            "source_sha256": {p: sha((root / p).read_bytes()) for p in sources}}
    identity = selected(plan["target"], plan, root=root, env=env, filelist_bytes=filelist)
    out = reserve_run(root / ".tools/runs", identity, plan=plan)
    (out / "sources.f").write_bytes(filelist)
    with tempfile.TemporaryDirectory(prefix=f"{family}-") as tmp:
        binary = str(Path(tmp) / "test.vvp")
        compile_argv = ["iverilog", "-g2012", "-Wall", "-s", top, "-o", binary, *sources]
        sim_argv = ["vvp", binary]
        (out / "plan.json").write_text(json.dumps({
            **plan, "identity": identity, "cwd": ".", "compile_argv": compile_argv,
            "simulation_argv": sim_argv,
        }, indent=2) + "\n")
        if env.get("GITHUB_OUTPUT"):
            with Path(env["GITHUB_OUTPUT"]).open("a") as output:
                output.write(f"execution_id={identity['run_id']}\n")
        with (out / "compile.log").open("wb") as log:
            subprocess.run(compile_argv, cwd=root, check=True, stdout=log,
                           stderr=subprocess.STDOUT)
        with (out / "simulation.log").open("wb") as stdout, (out / "simulation.stderr.log").open("wb") as stderr:
            subprocess.run(sim_argv, cwd=root, check=True, stdout=stdout, stderr=stderr)
        trace = (out / "simulation.log").read_bytes()
        print(trace.decode("utf-8", errors="replace"), end="", flush=True)
        if any(not any(line.startswith(marker) for line in trace.splitlines()) for marker in markers):
            raise ValueError(f"{lane}: missing original simulator PASS marker")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
    args = parser.parse_args()
    try:
        execute(args.lane)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
