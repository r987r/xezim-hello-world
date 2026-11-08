"""One actual SoC C/iDMA + pinned PCIe outbound requester test.

The existing execute_cold_boot remains the sole INIT/RUN/CHECK owner.  The
Root Complex participant drives direct outbound descriptor ports only for
this intermediate milestone; no invented CPU requester CSR is claimed.
"""
import cocotb
from dv.full_chip.test_boot import execute_cold_boot


@cocotb.test(timeout_time=11, timeout_unit="ms")
async def real_idma_to_pcie_host_memory(dut):
    await execute_cold_boot(dut, external="pcie0")
