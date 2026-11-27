#!/usr/bin/env python3
"""Keep the six existing direct Icarus Ethernet runs in their own CI archives."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

if __package__:
    from .ethernet_frame_workspace import checkout_provenance, git
    from .run_workspace import reserve_run
    from .test_identity import selected, sha
else:
    from ethernet_frame_workspace import checkout_provenance, git
    from run_workspace import reserve_run
    from test_identity import selected, sha

ROOT = Path(__file__).resolve().parents[1]
LOCK = "config/ip.lock.yaml"
FETCHER = "tools/ip_fetch.py"
AXI_ROOT = ".tools/verilog_axi"

# These are the direct CI compiler inputs, in the original order. These jobs
# are not registered full-chip tests or public traffic observations.
LANES = {
    "cq-writer": ("completion-record-write", "ethernet_cq_axi_writer_tb",
                  ("ethernet_cq_axi_writer.v",), "cq_writer_tb.v",
                  ("axi_dma_wr.v", "axi_ram.v"), ("checks", "AW", "B")),
    "queue-control": ("queue-control", "ethernet_queue_ctrl_tb",
                      ("ethernet_queue_ctrl.sv",), "queue_ctrl_tb.sv",
                      (), ("checks",)),
    "rx-desc": ("rx-descriptor-fetch", "ethernet_rx_desc_fetch_tb",
                ("ethernet_rx_desc_fetch.v",), "rx_desc_fetch_tb.v",
                ("axi_dma_rd.v", "axi_ram.v"), ("checks", "AXI_reads")),
    "rx-dma": ("rx-dma-sram", "ethernet_rx_dma_tb",
               ("ethernet_rx_dma.v",), "rx_dma_tb.v",
               ("axi_dma_wr.v", "axi_ram.v"), ("checks", "AW", "B", "bytes")),
    "rx-queue": ("rx-queue-engine", "ethernet_rx_queue_engine_tb",
                 ("ethernet_queue_ctrl.sv", "ethernet_rx_desc_fetch.v",
                  "ethernet_rx_dma.v", "ethernet_rx_queue_engine.v", "ethernet_cq_axi_writer.v"),
                 "rx_queue_engine_tb.v", ("axi_dma_rd.v", "axi_dma_wr.v", "axi_ram.v"),
                 ("checks", "AXI_desc_AR", "AXI_payload_AW", "CQ_AW", "CQ_B")),
    "tx-dma": ("tx-dma-sram", "ethernet_tx_dma_tb",
               ("ethernet_tx_dma.v",), "tx_dma_tb.v",
               ("axi_dma_rd.v", "axi_ram.v"), ("checks", "AR", "AXIS_beats")),
}


def sources_for(lane):
    _, _, rtl, bench, upstream, _ = LANES[lane]
    return (
        *(f"rtl/io/ethernet0/{name}" for name in rtl),
        f"dv/ethernet0/{bench}",
        *(f"{AXI_ROOT}/rtl/{name}" for name in upstream),
    )


def fetched_provenance(root, upstream):
    if not upstream:
        return {}
    lock = (root / LOCK).read_bytes()
    pin = yaml.safe_load(lock)["third_party"]["verilog_axi"]["commit"]
    checkout = root / AXI_ROOT
    if not isinstance(pin, str) or not re.fullmatch(r"[a-f0-9]{40}", pin):
        raise ValueError("invalid verilog_axi pin")
    if git(checkout, "rev-parse", "HEAD").decode().strip() != pin:
        raise ValueError("unexpected verilog_axi checkout")
    for name in upstream:
        rel = "rtl/" + name
        path = checkout / rel
        if path.is_symlink() or path.read_bytes() != git(checkout, "show", f"{pin}:{rel}"):
            raise ValueError(f"compiler input differs from pinned source bytes: {rel}")
    return {"revisions": {"verilog_axi": pin}, "lock_sha256": sha(lock),
            "fetcher_sha256": sha((root / FETCHER).read_bytes())}


def verify_transcript(lane, stdout):
    _, top, _, _, _, fields = LANES[lane]
    pattern = rb"PASS " + top.encode() + b"".join(
        b" " + field.encode() + rb"=[0-9]+" for field in fields
    )
    if sum(re.fullmatch(pattern, line) is not None for line in stdout.splitlines()) != 1:
        raise ValueError(f"missing or ambiguous original {top} PASS marker")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", choices=LANES)
    args = parser.parse_args()
    revision, dirty = checkout_provenance(ROOT, os.environ)
    logical_test, top, _, _, upstream, _ = LANES[args.lane]
    sources = sources_for(args.lane)
    filelist = ("\n".join(sources) + "\n").encode()
    plan = {
        "target": f"ethernet-{args.lane}", "logical_test": logical_test,
        "engine": "icarus", "sources": "ethernet-unit", "top": top,
        "source_revision": revision, "checkout_dirty": dirty,
        "evidence_scope": "isolated_unit_transcripts_only",
        "source_sha256": {name: sha((ROOT / name).read_bytes()) for name in sources},
        "fetch_provenance": fetched_provenance(ROOT, upstream),
    }
    identity = selected(plan["target"], plan, root=ROOT, filelist_bytes=filelist)
    out = reserve_run(ROOT / ".tools/runs", identity, plan=plan)
    (out / "sources.f").write_bytes(filelist)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            print(f"run_dir={out.relative_to(ROOT).as_posix()}", file=output)
    print(f"Ethernet RTL unit evidence: {out.relative_to(ROOT)}", flush=True)
    with tempfile.TemporaryDirectory(prefix="ethernet-unit-") as build:
        binary = str(Path(build) / top)
        compile_argv = ["iverilog", "-g2012", "-Wall", "-s", top, "-o", binary, *sources]
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
    verify_transcript(args.lane, stdout)


if __name__ == "__main__":
    main()
