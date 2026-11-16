"""PCIe RC BFM -> real verilog-pcie RTL -> real FlooNoC -> real tc_sram."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
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
    # The BAR0_RELOCATE constant is an elaboration-time SV parameter,
    # but Verilator's continuous output assignment is not VPI-visible
    # until a simulator evaluation. Reading at time 0 can return the
    # stale default 0 even when "-GBAR0_RELOCATE=1" was compiled.
    # Observe the real selected RTL mode AFTER clock and delta evaluation.
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    relocated = bool(int(dut.bar0_relocation_enabled.value))
    dut._log.info("PCIE0_RTL_BAR_RELOCATE_SAMPLED=%d after actual clock evaluation",
                  int(relocated))
    rc = RootComplex()
    # The upstream RC has two reserved mappings: low mem_pool spans
    # [0, 0x80000000), while the 16-byte MSI aperture starts at 0x80000000.
    # Consequently the older low-pool mapping failed "address out of range";
    # replacing it with a 1MiB root mapping at 0x80000000 failed "overlaps
    # existing region" because of that MSI aperture. The device's BAR0 is
    # exactly 4KiB at 0x80001000: route ONLY its actual address window.
    # offset=None preserves absolute addresses in authentic TLP requests.
    # This never substitutes host RAM for real RTL or fabricates a completion.
    if relocated:
        host_bar = 0x80001000
        bar_size = 0x1000
        assert not rc.mem_address_space.find_regions(host_bar, bar_size), (
            "host BAR collides with an upstream reserved RC region"
        )
        rc.mem_address_space.register_region(
            rc.mem_region, host_bar, bar_size, offset=None
        )
        rc.mem_base = host_bar
        matches = rc.mem_address_space.find_regions(host_bar, bar_size)
        assert len(matches) == 1 and matches[0][3] is rc.mem_region, (
            "relocated PCIe host BAR must use the real TLP route"
        )
    else:
        rc.mem_pool.register_region(rc.mem_region, 0x12000000, 0x100000, offset=None)
        rc.mem_base = 0x12000000
    dev = PcieIfDevice(
        clk=dut.clk, rst=dut.rst,
        rx_req_tlp_bus=PcieIfRxBus.from_prefix(dut, "rx_req_tlp"),
        tx_cpl_tlp_bus=PcieIfTxBus.from_prefix(dut, "tx_cpl_tlp"),
        cfg_max_payload=dut.max_payload_size,
    )
    dev.functions[0].configure_bar(0, 4096 if relocated else 1024 * 1024)
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
    if relocated:
        # Upper edge completes exactly at the end of the 4KiB BAR.
        vectors.append((0xff0, bytes((i * 11 + 1) & 255 for i in range(16))))
    dut._log.info("PCIE0_BAR_MODE=%s host_base=%#x sram_base=%#x",
                  "relocated" if relocated else "legacy",
                  0x80001000 if relocated else 0x12000000, 0x12000000)
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
        "PCIE0_REAL_NOC_SRAM_PASS mode=%s vectors=%d SRAM_WRITES=%d SRAM_READS=%d",
        "relocated" if relocated else "legacy", len(vectors),
        int(dut.sram_write_count.value), int(dut.sram_read_count.value)
    )
