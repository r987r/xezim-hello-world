"""Read-only runtime binding to real elaborated Verilator storage.

This test-only RTL probe is distinct from real CSR/Config-NoC equivalence.
"""
import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

from tools.csr_backdoor import BindingError
from tools.csr_runtime import ReadOnlyCsrRuntime, RuntimeEvidence, cocotb_handle


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
                     "backdoor_policy": "frontdoor_only"},
                ],
            }],
        }],
    }
    path = "csr_runtime_tb.u_probe.state_q"
    signal = cocotb_handle(dut, path)
    build_sha = os.environ["CSR_PROBE_BUILD_SHA256"]
    inventory = {
        "schema_version": 1, "variant": "runtime_probe",
        "top": dut._name, "simulator": "verilator",
        "build_sha256": build_sha,
        "objects": [{"path": path, "kind": "logic",
                     "width_bits": len(signal), "writable": False}],
    }
    binding = [{"logical_path": "probe0.status.counter",
                "rtl_path": path, "rtl_lsb": 1}]
    runtime = ReadOnlyCsrRuntime(
        catalog, inventory, binding, {path: signal},
        RuntimeEvidence("verilator", dut._name, "runtime_probe", build_sha))
    logical = "probe0.status.counter"
    assert runtime.read(logical, quiescent=True) == 0
    try:
        runtime.read(logical, quiescent=False)
        raise AssertionError("non-quiescent backdoor read accepted")
    except BindingError:
        pass

    dut.enable.value = 1
    for _ in range(6):
        await RisingEdge(dut.clk)
    dut.enable.value = 0
    await FallingEdge(dut.clk)
    observed = int(dut.observed.value)
    assert observed == 12, f"expected actual Verilator counter 12 got {observed}"
    assert runtime.read(logical, quiescent=True) == ((observed >> 1) & 0x7f)
    try:
        runtime.read("probe0.status.write_sensitive", quiescent=True)
        raise AssertionError("frontdoor-only CSR backdoor read accepted")
    except BindingError:
        pass
    try:
        runtime.write(logical, 0)
        raise AssertionError("direct register deposit was accepted")
    except BindingError:
        pass
    try:
        cocotb_handle(dut, "csr_runtime_tb.u_probe.missing_q")
        raise AssertionError("nonexistent HDL handle was accepted")
    except BindingError:
        pass
    dut._log.info("PASS CSR runtime: actual Verilator HDL field, quiescence, no direct writes")
