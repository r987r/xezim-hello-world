"""Real Verilator/Cocotb handle traversal test; no CSR bus shortcuts claimed."""
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

from tools.csr_backdoor import BindingError, compose
from tools.csr_runtime import SafeCsrBackdoor


@cocotb.test(timeout_time=150, timeout_unit="us")
async def actual_visible_hdl_signal(dut):
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.enable.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    catalog = {
        "schema_version": 1, "variant": "runtime_probe",
        "instances": [{
            "name": "probe0", "status": "implemented",
            "base": "0x40000000", "size": "0x100",
            "registers": [{
                "name": "status", "offset": "0", "size_bytes": 4,
                "fields": [
                    {"name": "counter", "lsb": 1, "msb": 7,
                     "backdoor_policy": "backdoor_read_only"},
                    {"name": "write_sensitive", "lsb": 8, "msb": 8,
                     "backdoor_policy": "frontdoor_only"}
                ]
            }]
        }]
    }
    entries = compose(catalog)
    path = "csr_runtime_tb.u_probe.state_q"
    binding = SafeCsrBackdoor(
        entries, dut, simulator="verilator-cocotb",
        build_sha256=os.environ["CSR_PROBE_BUILD_SHA256"],
        specs=[{"logical_path": "probe0.status.counter",
                "rtl_path": path, "rtl_lsb": 1}], strict=True)
    assert binding.read("probe0.status.counter") == 0
    dut.enable.value = 1
    for _ in range(6):
        await RisingEdge(dut.clk)
    dut.enable.value = 0
    await FallingEdge(dut.clk)
    observed = int(dut.observed.value)
    assert observed == 12, f"real RTL counter expected 12 got {observed}"
    assert binding.read("probe0.status.counter") == (observed >> 1) & 0x7f
    try:
        binding.read("probe0.status.write_sensitive")
        raise AssertionError("frontdoor-only logical CSR accepted direct read")
    except BindingError:
        pass
    try:
        binding.write("probe0.status.counter", 0)
        raise AssertionError("raw signal deposit accepted")
    except BindingError:
        pass
    missing = SafeCsrBackdoor(
        entries, dut, simulator="verilator-cocotb",
        build_sha256=os.environ["CSR_PROBE_BUILD_SHA256"],
        specs=[{"logical_path": "probe0.status.counter",
                "rtl_path": "csr_runtime_tb.u_probe.nonexistent"}])
    try:
        missing.read("probe0.status.counter")
        raise AssertionError("missing real HDL signal falsely bound")
    except BindingError:
        pass
    dut._log.info("PASS CSR backdoor runtime: real Verilator HDL handle, field extraction, no deposits")
