#!/usr/bin/env python3
"""Archive the unchanged direct Icarus frame-stager test, not a chip verdict."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

if __package__:
    from .run_workspace import reserve_run
    from .test_identity import selected, sha
else:
    from run_workspace import reserve_run
    from test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[1]
TOP = "ethernet_rx_frame_stager_tb"
LOCK = "rtl/io/ethernet0/ip.lock.yml"
AXIS_FIFO = "rtl/axis_fifo.v"
SOURCES = ("rtl/io/ethernet0/ethernet_rx_frame_stager.v",
           "dv/ethernet0/rx_frame_stager_tb.v",
           f".tools/ethernet0/verilog_axis/{AXIS_FIFO}")
MARKER = re.compile(rb"PASS ethernet_rx_frame_stager_tb checks=[0-9]+ good_beats=[0-9]+ drops=[0-9]+")


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def checkout_provenance(root, env):
    revision = git(root, "rev-parse", "HEAD").decode().strip()
    dirty = bool(git(root, "status", "--porcelain"))
    if env.get("GITHUB_ACTIONS") == "true" or "GITHUB_RUN_ID" in env:
        if (dirty or env.get("GITHUB_SHA") != revision
                or any(not (env.get(key, "").isdecimal() and int(env[key]) > 0)
                       for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))):
            raise ValueError("Ethernet frame-stager CI requires a clean exact checkout, run, and attempt")
    return revision, dirty


def fetched_provenance(root):
    import yaml

    lock = (root / LOCK).read_bytes()
    pins = yaml.safe_load(lock)["third_party"]
    fetched = {}
    for name in ("verilog_ethernet", "verilog_axis"):
        sub = root / ".tools" / "ethernet0" / name
        expected = pins[name]["commit"]
        if not re.fullmatch(r"[a-f0-9]{40}", expected) or git(sub, "rev-parse", "HEAD").decode().strip() != expected:
            raise ValueError(f"unexpected Ethernet pin for {name}")
        fetched[name] = expected
    source = root / SOURCES[-1]
    if source.is_symlink() or source.read_bytes() != git(source.parents[1], "show", f"HEAD:{AXIS_FIFO}"):
        raise ValueError("AXIS FIFO compiler input differs from the pinned source bytes")
    return {"revisions": fetched, "lock_sha256": sha(lock),
            "fetcher_sha256": sha((root / "dv/ethernet0/run_mac_gmii.py").read_bytes())}


def verify_transcript(stdout):
    if sum(MARKER.fullmatch(line) is not None for line in stdout.splitlines()) != 1:
        raise ValueError("missing or ambiguous original Ethernet frame-stager PASS marker")


def main():
    revision, dirty = checkout_provenance(ROOT, os.environ)
    frame_family = "ethernet-frame-stage"
    filelist = ("\n".join(SOURCES) + "\n").encode()
    fetch = fetched_provenance(ROOT)
    plan = {"target": "ethernet-frame-stager", "logical_test": "frame-staging-header-tap",
            "engine": "icarus", "sources": frame_family, "top": TOP,
            "source_revision": revision, "checkout_dirty": dirty,
            "evidence_scope": "isolated_unit_transcripts_only",
            "source_sha256": {name: sha((ROOT / name).read_bytes()) for name in SOURCES},
            "fetch_provenance": fetch}
    identity = selected(plan["target"], plan, root=ROOT, filelist_bytes=filelist)
    out = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    (out / "sources.f").write_bytes(filelist)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            print(f"run_dir={out.relative_to(ROOT).as_posix()}", file=output)
    print(f"Ethernet frame-stager evidence: {out.relative_to(ROOT)}", flush=True)
    with tempfile.TemporaryDirectory(prefix=f"{frame_family}-") as build:
        binary = str(Path(build) / "eth_stage_tb")
        compile_argv = ["iverilog", "-g2012", "-Wall", "-s", TOP, "-o", binary, *SOURCES]
        simulation_argv = ["vvp", binary]
        (out / "plan.json").write_text(json.dumps({
            **plan, "identity": identity, "cwd": ".", "compile_argv": compile_argv,
            "simulation_argv": simulation_argv,
        }, indent=2) + "\n")
        with (out / "compile.log").open("wb") as log:
            subprocess.run(compile_argv, cwd=ROOT, check=True, stdout=log, stderr=subprocess.STDOUT)
        with (out / "simulation.log").open("wb") as log, (out / "simulation.stderr.log").open("wb") as stderr:
            subprocess.run(simulation_argv, cwd=ROOT, check=True, stdout=log, stderr=stderr)
    stdout = (out / "simulation.log").read_bytes()
    print(stdout.decode("utf-8", errors="replace"), end="", flush=True)
    verify_transcript(stdout)


if __name__ == "__main__":
    main()
