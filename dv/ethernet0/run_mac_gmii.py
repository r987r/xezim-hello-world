#!/usr/bin/env python3
"""Compile and run the pinned standalone real GMII Ethernet MAC Cocotb test."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
LOCK = ROOT / "rtl/io/ethernet0/ip.lock.yml"
SOURCES = ("verilog_ethernet", "verilog_axis")


def fetch_pinned():
    data = yaml.safe_load(LOCK.read_text())
    if data.get("schema_version") != 1:
        raise ValueError("invalid Ethernet IP lock schema")
    result = {}
    for name in SOURCES:
        spec = data["third_party"][name]
        sha = spec["commit"]
        url = spec["git"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("Ethernet third-party IP must use full immutable SHA")
        if url != f"https://github.com/alexforencich/{name.replace('_', '-')}.git":
            raise ValueError("Ethernet upstream repo is not the reviewed source")
        output = ROOT / ".tools" / "ethernet0" / name
        output.parent.mkdir(parents=True, exist_ok=True)
        if not (output / ".git").is_dir():
            subprocess.run(["git", "init", "-q", str(output)], check=True)
            subprocess.run(["git", "-C", str(output), "remote", "add",
                            "origin", url], check=True)
        old = subprocess.run(["git", "-C", str(output), "rev-parse", "HEAD"],
                             capture_output=True, text=True)
        if old.returncode or old.stdout.strip() != sha:
            subprocess.run(["git", "-C", str(output), "fetch", "-q", "--depth",
                            "1", "origin", sha], check=True)
            subprocess.run(["git", "-C", str(output), "checkout",
                            "-q", "--detach", sha], check=True)
        got = subprocess.check_output(["git", "-C", str(output),
                                      "rev-parse", "HEAD"], text=True).strip()
        if got != sha:
            raise ValueError("upstream IP SHA mismatch")
        for path in spec["modules"]:
            if not (output / path).is_file():
                raise ValueError(f"missing pinned source {name}/{path}")
        result[name] = (output, spec)
        print(f"Ethernet pinned RTL: {name} {sha}", flush=True)
    return result


def main():
    if not shutil.which("iverilog"):
        raise ValueError("iverilog is required for this isolated regression")
    if not shutil.which("git"):
        raise ValueError("git is required for pinned RTL fetch")
    ip = fetch_pinned()
    sources = [
        ROOT / "rtl/io/ethernet0/ethernet0_mac_gmii.v",
        *[ip["verilog_ethernet"][0] / x for x in ip["verilog_ethernet"][1]["modules"]],
        *[ip["verilog_axis"][0] / x for x in ip["verilog_axis"][1]["modules"]],
    ]
    output = ROOT / ".tools" / "regression" / "ethernet0-gmii"
    output.mkdir(parents=True, exist_ok=True)
    # Separate compile check gives a fast, explicit syntax/elaboration failure
    # even when Cocotb runner setup itself fails.
    subprocess.run(["iverilog", "-g2012", "-s", "ethernet0_mac_gmii",
                    "-t", "null", *[str(s) for s in sources]], check=True)
    print("PASS isolated real Ethernet GMII RTL elaboration", flush=True)
    from cocotb_test.simulator import run
    os.chdir(ROOT)
    run(
        simulator="icarus",
        verilog_sources=[str(s) for s in sources],
        toplevel="ethernet0_mac_gmii",
        module="dv.ethernet0.tb_mac_gmii",
        python_search=[str(ROOT)],
        sim_build=str(output / "sim_build"),
        timescale="1ns/1ps",
        waves=False,
        extra_env={"COCOTB_LOG_LEVEL": "INFO"},
    )
    print("PASS isolated real Ethernet GMII MAC and CDC traffic", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"FAIL isolated Ethernet RTL: {exc}", file=sys.stderr)
        sys.exit(1)
