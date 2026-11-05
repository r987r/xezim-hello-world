"""Joint real CPU0 + modeled PCIe RC INIT/RUN/CHECK regression.

No host writes to CPU boot SRAM or preloads the endpoint SRAM. CPU0 uses
real AXI/FlooNoC stores and polls; Root Complex accesses the same PCIe0 SRAM
via verilog-pcie's real TLP->AXI4 RTL and independent local FlooNoC.
"""
from pathlib import Path
import json
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
from cocotbext.pcie.core import RootComplex
from cocotb.utils import get_sim_time
from dv.common.test_flow import attach_from_plan, close_active
from dv.common.axi_trace import attach_observers, trace_phase

from dv.pcie0.discovery import enumerate_root_complex
import sys
ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_TB = ROOT / ".tools/verilog_pcie/tb/pcie_axi_master"
if not (UPSTREAM_TB / "pcie_if.py").exists():
    raise RuntimeError("pinned verilog-pcie host protocol model absent")
sys.path.insert(0, str(UPSTREAM_TB))
from pcie_if import PcieIfDevice, PcieIfRxBus, PcieIfTxBus

PCIE_SRAM = 0x12000000
PHASE_BAR = 0x800
MAGIC = {
    "device_init_ready": 0xc0011001,
    "host_init_ack": 0xc0011002,
    "run_enable": 0xc0012001,
    "host_run_ack": 0xc0012002,
    "check_enable": 0xc0013001,
    "host_check_ack": 0xc0013002,
}


async def poll_bar(bar, offset, expected):
    for _ in range(5000):
        got = int.from_bytes(await bar.read(offset, 4), "little")
        if got == expected:
            return
        await Timer(20, units="ns")
    raise AssertionError(f"missing BAR handshake {offset:#x} expected {expected:#x}")


async def wait_cpu_signal(sig, name):
    for _ in range(5000):
        if int(sig.value) == 1:
            return
        await Timer(200, units="ns")
    raise AssertionError("CPU phase never reached: " + name)


@cocotb.test(timeout_time=6, timeout_unit="ms")
async def cpu_and_pcie_root_complex_joint_boot(dut):
    dut.rst_n.value = 0
    dut.hold_mask.value = 0
    dut.completer_id.value = 0
    dut.max_payload_size.value = 0
    attach_observers(dut)
    flow = attach_from_plan(lambda: int(get_sim_time(units='ps')))
    if flow is None:
        raise AssertionError('PCIe0 host test requires configured common step-flow reporting')
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    rc = RootComplex()
    # cocotbext-pcie 0.2.14 requires a registered allocation region.
    rc.mem_pool.register_region(rc.mem_region, PCIE_SRAM, 0x100000, offset=None)
    rc.mem_base = PCIE_SRAM
    ep = PcieIfDevice(
        clk=dut.clk, rst=dut.rst,
        rx_req_tlp_bus=PcieIfRxBus.from_prefix(dut, "rx_req_tlp"),
        tx_cpl_tlp_bus=PcieIfTxBus.from_prefix(dut, "tx_cpl_tlp"),
        cfg_max_payload=dut.max_payload_size,
    )
    ep.functions[0].configure_bar(0, 1024 * 1024)
    rc.make_port().connect(ep)
    for _ in range(12):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    # HOST's independent PCIe responsibilities: enumerate, enable, manage BAR.
    with flow.step("init", "host0", "enumerate", origin="stimulus"):
        misses = await with_timeout(enumerate_root_complex(rc, timeout_us=80), 150, "us")
        dut._log.info("PCIE0_EXPECTED_DISCOVERY_MISSES=%d", misses)
        dev = rc.find_device(ep.functions[0].pcie_id)
        assert dev is not None, "PCIe Root Complex failed to enumerate endpoint model"
        await with_timeout(dev.enable_device(), 100, "us")
    dut.completer_id.value = int(ep.functions[0].pcie_id)
    bar = dev.bar_window[0]

    # INIT: CPU firmware must initialize peers before the host is allowed
    # to accept device-ready; BAR transactions really traverse PCIe0 RTL.
    with flow.step("init", "host0", "wait_device_ready", origin="observed"):
        await with_timeout(poll_bar(bar, PHASE_BAR, MAGIC["device_init_ready"]),
                           1000, "us")
    assert int(dut.init_mask.value) == (1 << 2)-1, "CPU INIT missing before device-ready"
    trace_phase("PCIE HOST INIT: real CPU remote AXI store observed through PCIe BAR")
    with flow.step("init", "host0", "init_ack", origin="stimulus"):
        await with_timeout(bar.write(PHASE_BAR+4, MAGIC["host_init_ack"].to_bytes(4, "little")),
                           100, "us")
    with flow.step("init", "cpu0", "init_complete", origin="checker"):
        await with_timeout(wait_cpu_signal(dut.init_complete, "init"), 800, "us")

    # RUN: same owner, same actual generated SRAM; patterns are derived from
    # physical addresses and use odd lengths to detect missing write strobes.
    with flow.step("run", "host0", "wait_run_enable", origin="observed"):
        await with_timeout(poll_bar(bar, PHASE_BAR+8, MAGIC["run_enable"]),
                           1000, "us")
    trace_phase("PCIE HOST RUN: BAR0 writes/read-completions through real PCIe0 NoC")
    with flow.step("run", "host0", "bar_roundtrip", origin="checker",
                   details={"vectors":4}):
        vectors = [(0x100, 8), (0x125, 17), (0x200, 64), (0x327, 33)]
        prior_wr = int(dut.pcie_sram_write_count.value)
        prior_rd = int(dut.pcie_sram_read_count.value)
        from tools.memory_service import Pattern
        for offset, size in vectors:
            pattern = Pattern("address_xor", seed=0x5a33).chunk(PCIE_SRAM+offset, size)
            await with_timeout(bar.write(offset, pattern), 100, "us")
            received = await with_timeout(bar.read(offset, size), 100, "us")
            assert bytes(received) == pattern, (
                f"PCIe0 real SRAM/bar readback incorrect offset={offset:#x}")
        assert int(dut.pcie_sram_write_count.value) > prior_wr, "no accepted PCIe0 SRAM writes"
        assert int(dut.pcie_sram_read_count.value) > prior_rd, "no accepted PCIe0 SRAM reads"
        assert not int(dut.status_error_cor.value)
        assert not int(dut.status_error_uncor.value)
    with flow.step("run", "host0", "run_ack", origin="stimulus"):
        await with_timeout(bar.write(PHASE_BAR+12, MAGIC["host_run_ack"].to_bytes(4, "little")),
                           100, "us")
    with flow.step("run", "cpu0", "run_complete", origin="checker"):
        await with_timeout(wait_cpu_signal(dut.run_complete, "run"), 800, "us")

    # CHECK: CPU0 itself waits for host checked-data acknowledgment; its
    # standard CPU CHECK cannot finish early.
    with flow.step("check", "host0", "wait_check_enable", origin="observed"):
        await with_timeout(poll_bar(bar, PHASE_BAR+16, MAGIC["check_enable"]),
                           800, "us")
    trace_phase("PCIE HOST CHECK: independent BAR data+SRAM handshake completed")
    with flow.step("check", "host0", "check_ack", origin="stimulus"):
        await with_timeout(bar.write(PHASE_BAR+20, MAGIC["host_check_ack"].to_bytes(4, "little")),
                           100, "us")
    with flow.step("check", "cpu0", "check_complete", origin="checker"):
        await with_timeout(wait_cpu_signal(dut.check_complete, "check"), 800, "us")
    await RisingEdge(dut.clk)
    assert int(dut.pass_flag.value) == 1
    assert int(dut.init_mask.value) == 3
    assert int(dut.hello_mask.value) == 3
    assert int(dut.check_mask.value) == 3
    for monitor in ("pcie_sram_last_read_addr", "pcie_sram_last_write_addr"):
        addr = int(getattr(dut, monitor).value)
        assert PCIE_SRAM <= addr < PCIE_SRAM + 16384
    close_active()
    dut._log.info(
        "PASS pciehost: real CPU0/host handshake and PCIe0 SRAM data "
        "vectors=%d writes=%d reads=%d", len(vectors),
        int(dut.pcie_sram_write_count.value),
        int(dut.pcie_sram_read_count.value),
    )
