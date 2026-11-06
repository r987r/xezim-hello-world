#!/usr/bin/env python3
"""Compile and run a real elaborated Verilator hierarchy probe for CSR backdoor.

No full-chip CSR equivalence is implied; that is a separate later gate.
"""
from pathlib import Path
import hashlib
import os

from cocotb.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dv/csr_runtime/probe.sv"


def main():
    fingerprint = hashlib.sha256(SOURCE.read_bytes() + b"verilator|public-flat-rw|csr_runtime_tb").hexdigest()
    os.environ["CSR_PROBE_BUILD_SHA256"] = fingerprint
    runner = get_runner("verilator")
    runner.build(
        sources=[str(SOURCE)],
        hdl_toplevel="csr_runtime_tb",
        build_dir=ROOT/".tools/csr-runtime-obj",
        build_args=["--timing", "--assert", "--public-flat-rw", "-Wno-fatal"],
        always=True,
        waves=False,
    )
    runner.test(
        hdl_toplevel="csr_runtime_tb",
        hdl_toplevel_lang="verilog",
        test_module="dv.csr_runtime.test_bind_hdl",
        test_dir=ROOT,
        seed=91,
    )


if __name__ == "__main__":
    main()
