"""Fast electrical/frontdoor check of actual generated PeakRDL RTL.

No faked register model, no hierarchy deposits, no bypass of AXI handshakes.
Tests AXI-Lite local register contract; the full chip separately checks
CPU->Config-NoC->AXI4/Lite conversion->same generated RTL.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, with_timeout
from cocotbext.axi import AxiLiteBus, AxiLiteMaster


async def write(master, offset, value, *, length=4):
    result = await with_timeout(master.write(offset, value.to_bytes(length, "little")), 30, "us")
    return int(result.resp)


async def read(master, offset, length=4):
    result = await with_timeout(master.read(offset, length), 30, "us")
    return int(result.resp), int.from_bytes(result.data, "little")


@cocotb.test(timeout_time=300, timeout_unit="us")
async def reset_release_ack_and_strobes(dut):
    dut.clk.value = 0
    dut.rst_n.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    master = AxiLiteMaster(
        AxiLiteBus.from_prefix(dut, "s_axil"),
        dut.clk, dut.rst_n, reset_active_level=False)
    for _ in range(8):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await FallingEdge(dut.clk)

    assert int(dut.release_o.value) == 0
    assert int(dut.secondary_ack_o.value) == 0
    assert await read(master, 0) == (0, 0)
    assert await read(master, 4) == (0, 0)

    # Non-release high byte is reserved; it MUST NOT release a core.
    assert await write(master, 3, 0xff, length=1) == 0
    assert await read(master, 0) == (0, 0)
    assert int(dut.release_o.value) == 0

    # A halfword written to the upper half of ACK preserves lower word bits.
    assert await write(master, 6, 0x1234, length=2) == 0
    assert await read(master, 4) == (0, 0x12340000)
    assert int(dut.secondary_ack_o.value) == 0x12340000

    # CPU1 reports its boot acknowledgment at the real 0x4 word.
    assert await write(master, 4, 1) == 0
    assert await read(master, 4) == (0, 1)
    assert int(dut.secondary_ack_o.value) == 1

    # CPU0 issues a valid write and observes a real secondary release bit.
    assert await write(master, 0, 1) == 0
    assert await read(master, 0) == (0, 1)
    assert int(dut.release_o.value) == 1

    # Two-core RDL has only 0x0 and 0x4 registers. Unmapped word is SLVERR.
    assert (await read(master, 8))[0] == 2
    assert await write(master, 8, 0xa5a5a5a5) == 2
    assert int(dut.release_o.value) == 1
    assert int(dut.secondary_ack_o.value) == 1

    # Reset is a real hardware reset; both fields must clear and remain
    # readable through the protocol after reset re-assertion/deassertion.
    await FallingEdge(dut.clk)
    dut.rst_n.value = 0
    for _ in range(8):
        await RisingEdge(dut.clk)
    assert int(dut.release_o.value) == 0
    assert int(dut.secondary_ack_o.value) == 0
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(5):
        await FallingEdge(dut.clk)
    assert await read(master, 0) == (0, 0)
    assert await read(master, 4) == (0, 0)
    dut._log.info("PASS peakrdl AXI-Lite: reset/ACK/release/strobes/SLVERR")
