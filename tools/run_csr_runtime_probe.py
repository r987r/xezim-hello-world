#!/usr/bin/env python3
"""Archive the original standalone read-only HDL probe, not a chip verdict."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile

if __package__:
    from .run_workspace import reserve_run
    from .test_identity import selected, sha
else:
    from run_workspace import reserve_run
    from test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "dv/csr_runtime/probe.sv"
TOP = "csr_runtime_tb"
MODULE = "dv.csr_runtime.test_bind_hdl"
BUILD_ARGS = ("--timing", "--assert", "--public-flat-rw", "-Wno-fatal")
SEED = 91
INPUTS = (SOURCE, "dv/csr_runtime/test_bind_hdl.py", "tools/csr_runtime.py",
          "tools/csr_backdoor.py", "tools/run_csr_runtime_probe.py",
          ".github/workflows/csr-backdoor.yml")
PASS_MARKER = b"PASS CSR runtime: actual Verilator HDL field, quiescence, no direct writes"


def checkout_provenance(root, env):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))
    if env.get("GITHUB_ACTIONS") == "true" or "GITHUB_RUN_ID" in env:
        if (dirty or env.get("GITHUB_SHA") != revision
                or any(not (env.get(key, "").isdecimal() and int(env[key]) > 0)
                       for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
            raise ValueError("CSR probe CI requires a clean exact checkout, run, and attempt")
    return revision, dirty


def verify_simulation(outcome, transcript):
    # Cocotb's runner outside pytest returns an XML path, not a test verdict.
    if outcome != (1, 0) or transcript.count(PASS_MARKER) != 1:
        raise ValueError("CSR probe did not complete its one original runtime policy test")


def main():
    import cocotb
    from cocotb.runner import get_results, get_runner

    revision, dirty = checkout_provenance(ROOT, os.environ)
    filelist = f"{SOURCE}\n".encode()
    source_bytes = (ROOT / SOURCE).read_bytes()
    # Preserve the existing probe fingerprint and snapshot bytes.
    fingerprint = hashlib.sha256(source_bytes + b"verilator|public-flat-rw|csr_runtime_tb").hexdigest()
    plan = {
        "target": "csr-runtime-quiescent", "logical_test": "quiescent-hdl-read",
        "sources": "csr-runtime", "engine": "cocotb-verilator", "top": TOP, "seed": SEED,
        "source_revision": revision, "checkout_dirty": dirty,
        "evidence_scope": "isolated_quiescent_hdl_source_evidence_only",
        "source_sha256": {name: sha((ROOT / name).read_bytes()) for name in INPUTS},
        "probe_build_sha256": fingerprint, "build_args": list(BUILD_ARGS), "test_module": MODULE,
        "verilator_version": subprocess.check_output(
            ["verilator", "--version"], cwd=ROOT, text=True).strip(),
        "cocotb_version": cocotb.__version__,
    }
    identity = selected(plan["target"], plan, root=ROOT, filelist_bytes=filelist)
    out = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    (out / "sources.f").write_bytes(filelist)
    (out / "plan.json").write_text(json.dumps({**plan, "identity": identity}, indent=2) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            print(f"run_dir={out.relative_to(ROOT).as_posix()}", file=output)
    print(f"CSR probe evidence: {out.relative_to(ROOT)}", flush=True)

    with tempfile.TemporaryDirectory(prefix="csr-runtime-", dir=ROOT / ".tools") as build:
        runner = get_runner("verilator")
        runner.build(
            sources=[str(ROOT / SOURCE)], hdl_toplevel=TOP, build_dir=build,
            build_args=list(BUILD_ARGS), always=True, waves=False,
            log_file=out / "compile.log",
        )
        results = runner.test(
            hdl_toplevel=TOP, hdl_toplevel_lang="verilog", test_module=MODULE,
            test_dir=ROOT, seed=SEED, results_xml=str(Path(build) / "results.xml"),
            extra_env={
                "CSR_PROBE_BUILD_SHA256": fingerprint,
                "CSR_PROBE_EVIDENCE_PATH": str(out / "csr-backdoor-map.json"),
            },
            log_file=out / "simulation.log",
        )
        transcript = (out / "simulation.log").read_bytes()
        print(transcript.decode("utf-8", errors="replace"), end="", flush=True)
        verify_simulation(get_results(results), transcript)


if __name__ == "__main__":
    main()
