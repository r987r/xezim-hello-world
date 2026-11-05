"""PCIe RC BFM -> real verilog-pcie RTL -> real FlooNoC -> real tc_sram."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, with_timeout
from discovery import enumerate_root_complex
from cocotbext.pcie.core import RootComplex
# Cocotb runner constructs its own PYTHONPATH. Make the locked upstream
# PcieIfDevice utility import path explicit inside the simulation process.
import sys
from pathlib import Path
VENDOR_TESTS = Path(__file__).resolve().parents[2] / ".tools/verilog_pcie/tb/pcie_axi_master"
if not (VENDOR_TESTS / "pcie_if.py").is_file():
    raise RuntimeError("pinned upstream PcieIfDevice simulation helper missing")
sys.path.insert(0, str(VENDOR_TESTS))
from pcie_if import PcieIfDevice, PcieIfRxBus, PcieIfTxBus


@cocotb.test(timeout_time=500, timeout_unit="us")
async def host_to_real_floonoc_tc_sram(dut):
    dut.rst.value = 1
    dut.clk.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    rc = RootComplex()
    # In cocotbext-pcie 0.2.14 the RC constructor registers the outbound
    # TLP region at its DEFAULT mem_base (0xc0000000). Changing mem_base
    # afterward moves BAR allocation, but does not change the AddressSpace
    # mapping, so BAR accesses fail before any TLP is sent. Install the
    # address-qualified outbound TLP region inside its low-address mem_pool.
    # This is RC BFM setup, not an RTL address-translation shortcut.
    rc.mem_pool.register_region(rc.mem_region, 0x12000000, 0x100000, offset=None)
    rc.mem_base = 0x12000000
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
    missing_count = await enumerate_root_complex(rc, timeout_us=40)
    dut._log.info("PCIE0_EXPECTED_DISCOVERY_MISSES=%d", missing_count)
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
            assert 0x12000000 <= addr < 0x12004000, f"{name} outside SRAM: {addr:#x}"
    assert not int(dut.status_error_cor.value)
    assert not int(dut.status_error_uncor.value)
    dut._log.info(
        "PCIE0_REAL_NOC_SRAM_PASS vectors=%d SRAM_WRITES=%d SRAM_READS=%d",
        len(vectors), int(dut.sram_write_count.value), int(dut.sram_read_count.value)
    )
