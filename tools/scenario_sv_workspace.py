#!/usr/bin/env python3
"""Run the existing SCN-3 driver-only smoke in one canonical CI workspace."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__:
    from .run_workspace import reserve_run
    from .test_identity import selected, sha
else:
    from run_workspace import reserve_run
    from test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[1]
TARGET = "scenario-sv-contract"
TOP = "test_scenario_sv_adapter"
ADAPTER = "dv/common/test_scenario_sv_adapter.sv"
SCENARIO = "config/scenarios/dma-roundtrip.json"
SOC = "config/soc.yaml"
MARKER = b"PASS SCN-3 SystemVerilog scenario metadata and driver events (no RTL proof)"


def run(root=ROOT):
    env = os.environ
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))
    if env.get("GITHUB_ACTIONS") == "true" or "GITHUB_RUN_ID" in env:
        if (dirty or env.get("GITHUB_SHA") != revision
                or any(not (env.get(key, "").isdecimal() and int(env[key]) > 0)
                       for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
            raise ValueError("Scenario SV CI requires a clean exact checkout, run, and attempt")

    def call(argv, **kwargs):
        return subprocess.run(argv, cwd=root, check=True, **kwargs)

    def python(script, *args):
        return [sys.executable, f"tools/{script}.py", *args]

    # Keep the identity filelist independent of the random execution directory.
    # The literal argv below binds the generated source to this reserved run.
    names = ("soc_scenario_contract_pkg.sv", ADAPTER)
    source_roles = ("generated:" + names[0], "checkout:" + names[1])
    sources = ("\n".join(source_roles) + "\n").encode()
    plan = {"target": TARGET, "logical_test": "driver-event-contract", "top": TOP,
            "engine": "verilator", "sources": TARGET, "source_revision": revision,
            "checkout_dirty": dirty, "scenario": SCENARIO,
            "evidence_scope": "driver_contract_only_not_rtl_or_traffic"}
    identity = selected(TARGET, plan, root=root, env=env, filelist_bytes=sources)
    out = reserve_run(root / ".tools/runs", identity, plan=plan)
    (out / "sources.f").write_bytes(sources)
    rel = out.relative_to(root).as_posix()
    if env.get("GITHUB_OUTPUT"):
        with Path(env["GITHUB_OUTPUT"]).open("a") as output:
            print(f"run_dir={rel}", file=output)
    scenario_plan = f"{rel}/scenario-plan.json"
    package = f"{rel}/{names[0]}"
    smoke = f"{rel}/smoke.log"
    events = f"{rel}/sv-driver-events.json"
    resolver = python("scenario_plan", "--scenario", SCENARIO, "--soc", SOC, "--out", scenario_plan)
    emitter = python("scenario_sv", "generate", "--plan", scenario_plan, "--out", package)
    auditor = python("scenario_sv", "audit", "--plan", scenario_plan, "--log", smoke, "--out", events)
    call(resolver)
    call(emitter)
    with tempfile.TemporaryDirectory(prefix="scenario-sv-contract-") as tmp:
        compiler = ["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module",
                    TOP, "--Mdir", tmp, "-o", "scenario_sv_smoke", package, ADAPTER]
        simulator = [str(Path(tmp) / "scenario_sv_smoke")]
        recorded = {**plan, "identity": identity, "cwd": ".", "generation_argv": [resolver, emitter],
                    "compile_argv": compiler, "simulation_argv": simulator, "audit_argv": auditor,
                    "scenario_plan_sha256": sha((root / scenario_plan).read_bytes()),
                    "source_sha256": {name: sha((root / name).read_bytes())
                                      for name in (package, ADAPTER, SCENARIO, SOC)}}
        (out / "plan.json").write_text(json.dumps(recorded, indent=2) + "\n")
        with (out / "compile.log").open("wb") as log:
            call(compiler, stdout=log, stderr=subprocess.STDOUT)
        with (root / smoke).open("wb") as stdout, (out / "simulation.stderr.log").open("wb") as stderr:
            call(simulator, stdout=stdout, stderr=stderr)
    stdout = (root / smoke).read_bytes()
    if stdout.splitlines().count(MARKER) != 1:
        raise ValueError("missing or ambiguous original Scenario SV PASS marker")
    print(stdout.decode(), end="", flush=True)
    call(auditor)
    audit = json.loads((root / events).read_text())
    if (audit["status"], audit["rtl_evidence"], audit["event_count"]) != ("driver_log_unverified", None, 4):
        raise ValueError("unexpected Scenario SV driver-only audit")
    return out


if __name__ == "__main__":
    run()
