#!/usr/bin/env python3
"""Regenerate the pinned PeakRDL real RTL and test its AXI4-Lite port.

A short, intentionally standalone preflight; not a replacement for chip
CPU->Config NoC integration. Build stays inside the ignored .tools tree.
"""
from pathlib import Path

from csrgen import generate, CONFIG, RDL
from cocotb.runner import get_runner

ROOT = Path(__file__).resolve().parents[1]
CSR = ROOT / ".tools" / "csr-axi"
RTL = CSR / "rtl"
BUILD = ROOT / ".tools" / "csr-axi-obj"


def main():
    generate(CONFIG, RDL, CSR, "cold_boot")
    runner = get_runner("verilator")
    runner.build(
        sources=[
            str(RTL / "soc_boot_reset_ctrl_regblock_pkg.sv"),
            str(RTL / "soc_boot_reset_ctrl_regblock.sv"),
            str(ROOT / "dv/csr/reset_axi_tb.sv"),
        ],
        hdl_toplevel="reset_axi_tb",
        build_dir=BUILD,
        build_args=["--timing", "--assert", "-Wno-fatal"],
        always=True,
        waves=False,
    )
    runner.test(
        hdl_toplevel="reset_axi_tb",
        hdl_toplevel_lang="verilog",
        test_module="dv.csr.test_reset_axi",
        test_dir=ROOT,
        seed=82,
    )


if __name__ == "__main__":
    main()
