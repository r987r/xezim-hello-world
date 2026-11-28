#!/usr/bin/env python3
"""Archive the original direct DDR Foundation simulations without build products."""
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
RTL = "rtl/memory/ddr4/"
FLAGS = ("--binary", "--timing", "--assert", "-Wno-fatal")
FAMILY = "ddr-foundation-unit"
LANES = {
    "aperture-guard": (
        "tb_ddr_litedram_aperture_guard",
        ("soc_aperture_guard.sv", "tb_soc_aperture_guard.sv"),
        b"PASS real DDR-B RTL aperture/burst guard: no physical aliases",
    ),
    "axi-bridge": (
        "tb_ddr_litedram_axi_bridge",
        ("soc_aperture_guard.sv", "soc_axi_bridge.sv", "tb_soc_axi_bridge.sv"),
        b"PASS DDR-B actual RTL bridge: DECERR AW/W/B/AR/R, backpressure, real forwarding, "
        b"25-bit translation, preserved IDs and data",
    ),
    "axi-wishbone": (
        "tb_ddr_litedram_axi_wishbone",
        ("soc_axi_wishbone_bridge.sv", "tb_soc_axi_wishbone_bridge.sv"),
        b"PASS DDR-B real Config NoC AXI4-to-Wishbone RTL: read/write, 16KiB guard, "
        b"translated CSR, stalls, DECERR",
    ),
}


def checkout_provenance(root, env):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))
    if env.get("GITHUB_ACTIONS") == "true" or "GITHUB_RUN_ID" in env:
        if (dirty or env.get("GITHUB_SHA") != revision
                or any(not (env.get(key, "").isdecimal() and int(env[key]) > 0)
                       for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
            raise ValueError("DDR unit CI requires a clean exact checkout, run, and attempt")
    return revision, dirty


def verify_transcript(lane, stdout):
    if stdout.splitlines().count(LANES[lane][2]) != 1:
        raise ValueError(f"{lane}: missing or ambiguous original simulator PASS marker")


def execute(lane, root=ROOT, env=None):
    root = Path(root).resolve()
    env = os.environ if env is None else env
    revision, dirty = checkout_provenance(root, env)
    top, names, _ = LANES[lane]
    sources = [RTL + name for name in names]
    filelist = ("\n".join(sources) + "\n").encode()
    plan = {"target": f"{FAMILY}-{lane}", "logical_test": lane, "top": top,
            "engine": "verilator", "sources": FAMILY, "source_revision": revision,
            "checkout_dirty": dirty, "evidence_scope": "isolated_unit_transcripts_only",
            "source_sha256": {name: sha((root / name).read_bytes()) for name in sources}}
    identity = selected(plan["target"], plan, root=root, env=env, filelist_bytes=filelist)
    out = reserve_run(root / ".tools/runs", identity, plan=plan)
    (out / "sources.f").write_bytes(filelist)
    if env.get("GITHUB_OUTPUT"):
        with Path(env["GITHUB_OUTPUT"]).open("a") as output:
            print(f"run_dir={out.relative_to(root).as_posix()}", file=output)
    with tempfile.TemporaryDirectory(prefix=f"{FAMILY}-") as tmp:
        compiler = ["verilator", *FLAGS, "--top-module", top, "--Mdir", tmp, *sources]
        simulator = [str(Path(tmp) / f"V{top}")]
        (out / "plan.json").write_text(json.dumps({
            **plan, "identity": identity, "cwd": ".", "compile_argv": compiler,
            "simulation_argv": simulator,
        }, indent=2) + "\n")
        with (out / "compile.log").open("wb") as compile_log:
            subprocess.run(compiler, cwd=root, check=True, stdout=compile_log,
                           stderr=subprocess.STDOUT)
        with (out / "simulation.log").open("wb") as stdout, (out / "simulation.stderr.log").open("wb") as stderr:
            subprocess.run(simulator, cwd=root, check=True, stdout=stdout, stderr=stderr)
    stdout = (out / "simulation.log").read_bytes()
    print(stdout.decode("utf-8", errors="replace"), end="", flush=True)
    verify_transcript(lane, stdout)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
    execute(parser.parse_args().lane)
