"""Full-chip latency under real CPU boot, using ONLY the unowned DMA BFM.

CPU0/CPU1 execute their existing cold-boot RTL and CHECK unchanged. There is
no iDMA in this default variant. The existing boot TB authorizes the probe
only after CPUs have finished; it must never attach to a real iDMA bus.
"""
import cocotb
from dv.full_chip.test_boot import execute_cold_boot


@cocotb.test()
async def measured_boot_fabric_latency(dut):
    await execute_cold_boot(dut, benchmark=True)
