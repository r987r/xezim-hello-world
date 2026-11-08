"""One actual SoC C/iDMA + pinned PCIe outbound requester test.

The existing execute_cold_boot remains the sole INIT/RUN/CHECK owner.  The
CPU0 C drives the real Config-NoC requester CSR and descriptor doorbells;
the Root Complex BFM supplies external host RAM/IOVA and independent checks.
Passive AXI/TLP capture is owned by the canonical cold-boot test.
"""
import cocotb
from dv.full_chip.test_boot import execute_cold_boot


@cocotb.test(timeout_time=11, timeout_unit="ms")
async def real_idma_to_pcie_host_memory(dut):
    await execute_cold_boot(dut, external="pcie0")
