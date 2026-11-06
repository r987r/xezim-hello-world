"""Compatibility test selector for the canonical dv/full_chip/test_boot.py flow.

The host RootComplex is a participant adapter, not an alternate test engine.
"""
import cocotb
from dv.full_chip.test_boot import execute_cold_boot


@cocotb.test(timeout_time=6, timeout_unit="ms")
async def cpu_and_pcie_root_complex_joint_boot(dut):
    await execute_cold_boot(dut, external="pcie0")
