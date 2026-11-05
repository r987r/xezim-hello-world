"""PCIe RC BFM -> real verilog-pcie RTL -> real FlooNoC -> real tc_sram."""
import logging

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, with_timeout
from cocotbext.pcie.core import RootComplex
from pcie_if import PcieIfDevice, PcieIfRxBus, PcieIfTxBus


class ExpectedDiscoveryMisses(logging.Filter):
    def __init__(self):
        super().__init__()
        self.count = 0

    def filter(self, record):
        if record.levelno == logging.WARNING and "Failed to route config type 0 TLP" in record.getMessage():
            self.count += 1
            return False
        return True


@cocotb.test(timeout_time=500, timeout_unit="us")
async def host_to_real_floonoc_tc_sram(dut):
    dut.rst.value = 1
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    rc = RootComplex()
    rc.mem_base = 0x10000000
    dev = PcieIfDevice(
        clk=dut.clk, rst=dut.rst,
        rx_req_tlp_bus=PcieIfRxBus.from_prefix(dut, "rx_req_tlp"),
        tx_cpl_tlp_bus=PcieIfTxBus.from_prefix(dut, "tx_cpl_tlp"),
        cfg_max_payload=dut.max_payload_size,
    )
    dev.functions[0].configure_bar(0, 1024 * 1024)
    rc.make_port().connect(dev)
    for _ in range(12):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(8):
        await RisingEdge(dut.clk)
    expected = ExpectedDiscoveryMisses()
    logger = logging.getLogger("cocotb.pcie.RootComplex")
    logger.addFilter(expected)
    try:
        await with_timeout(rc.enumerate(), 40, "us")
    finally:
        logger.removeFilter(expected)
    dut._log.info("PCIE0_EXPECTED_DISCOVERY_MISSES=%d", expected.count)
    device = rc.find_device(dev.functions[0].pcie_id)
    assert device is not None, "missing PCIe Endpoint"
    await device.enable_device()
    dut.completer_id.value = int(dev.functions[0].pcie_id)
    bar0 = device.bar_window[0]
    vectors = [
        (0x100, bytes(range(8))),
        (0x125, bytes((i * 7 + 3) & 255 for i in range(17))),
        (0x200, bytes((i * 13 + 9) & 255 for i in range(64))),
    ]
    for offset, payload in vectors:
        before_w = int(dut.sram_write_count.value)
        before_r = int(dut.sram_read_count.value)
        await with_timeout(bar0.write(offset, payload), 60, "us")
        got = await with_timeout(bar0.read(offset, len(payload)), 60, "us")
        assert bytes(got) == payload, f"real SRAM mismatch offset={offset:#x}: {bytes(got).hex()}"
        assert int(dut.sram_write_count.value) > before_w, "no SRAM write accepted"
        assert int(dut.sram_read_count.value) > before_r, "no SRAM read accepted"
        for name in ("sram_last_write_addr", "sram_last_read_addr"):
            addr = int(getattr(dut, name).value)
            assert 0x10000000 <= addr < 0x10004000, f"{name} outside SRAM: {addr:#x}"
    assert not int(dut.status_error_cor.value)
    assert not int(dut.status_error_uncor.value)
    dut._log.info(
        "PCIE0_REAL_NOC_SRAM_PASS vectors=%d SRAM_WRITES=%d SRAM_READS=%d",
        len(vectors), int(dut.sram_write_count.value), int(dut.sram_read_count.value)
    )
