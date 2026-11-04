"""Real PULP iDMA AXI descriptor + payload traffic, no CPU preload shortcut.

Only this isolated DMA scope seeds AXI SRAM directly; the existing cold-boot
regression always runs real CPU flash-to-SRAM copies.
"""
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.utils import get_sim_time
from cocotb.triggers import FallingEdge, RisingEdge, Timer, with_timeout
from cocotbext.axi import AddressSpace, AxiBus, AxiSlave, SparseMemoryRegion

from dv.common.dma_vectors import build_dma_vector, verify_dma_readback

ROOT = Path(__file__).resolve().parents[2]


async def submit(dut, phys_addr):
    """One real upstream 64-bit APB descriptor-head write."""
    await FallingEdge(dut.clk_i)
    dut.apb_addr_i.value = 0
    dut.apb_data_i.value = phys_addr
    dut.apb_write_i.value = 1
    dut.apb_select_i.value = 1
    dut.apb_enable_i.value = 0
    await FallingEdge(dut.clk_i)
    dut.apb_enable_i.value = 1
    for _ in range(100):
        await RisingEdge(dut.clk_i)
        if int(dut.apb_ready_o.value):
            assert int(dut.apb_error_o.value) == 0, "iDMA APB submission error"
            break
    else:
        raise AssertionError("iDMA descriptor APB submission blocked")
    await FallingEdge(dut.clk_i)
    dut.apb_select_i.value = 0
    dut.apb_enable_i.value = 0
    dut.apb_write_i.value = 0


async def read_dma_status(dut):
    """Read the actual pinned desc64 status CSR over APB (offset 8)."""
    await FallingEdge(dut.clk_i)
    dut.apb_addr_i.value = 8
    dut.apb_write_i.value = 0
    dut.apb_data_i.value = 0
    dut.apb_select_i.value = 1
    dut.apb_enable_i.value = 0
    await FallingEdge(dut.clk_i)
    dut.apb_enable_i.value = 1
    for _ in range(100):
        await RisingEdge(dut.clk_i)
        if int(dut.apb_ready_o.value):
            assert not int(dut.apb_error_o.value)
            status = int(dut.apb_rdata_o.value)
            break
    else:
        raise AssertionError("DMA APB status read timed out")
    await FallingEdge(dut.clk_i)
    dut.apb_select_i.value = 0
    dut.apb_enable_i.value = 0
    return status


async def await_idle(dut):
    # Testbench wait only, not CPU busy-polling. Never reclaim the shared
    # descriptor SRAM before the frontend has fully retired all requests.
    for _ in range(3000):
        status = await read_dma_status(dut)
        assert (status & 2) == 0, "DMA FIFO full after chain completion"
        if not (status & 1):
            return
    raise AssertionError("DMA did not become idle following final IRQ")


@cocotb.test(timeout_time=500, timeout_unit="us")
async def real_dma_one_and_one_hundred_descriptors(dut):
    cfg = __import__("yaml").safe_load((ROOT/"config/soc.yaml").read_text())
    dut.clk_i.value = 0
    dut.rst_ni.value = 0
    dut.apb_addr_i.value = 0
    dut.apb_data_i.value = 0
    dut.apb_write_i.value = 0
    dut.apb_select_i.value = 0
    dut.apb_enable_i.value = 0
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())

    memory = AddressSpace(size=1 << 64)
    computes = [s["name"] for s in cfg["subsystems"] if s["type"] == "compute"]
    for name in computes:
        region = next(r for r in cfg["address_map"]["data"] if r["name"] == name+".sram")
        memory.register_region(SparseMemoryRegion(cfg["boot"]["simulation_sram_bytes"]),
                               int(region["base"], 0))
    for target in cfg["memory_targets"]:
        region = next(r for r in cfg["address_map"]["data"] if r["name"] == target["name"])
        memory.register_region(
            SparseMemoryRegion(1 << cfg["verification"]["memory"]["model_address_bits"]),
            int(region["base"], 0))
    # Real RTL AXI source; upstream cocotbext-axi RAM is the AXI target.
    slave = AxiSlave(AxiBus.from_prefix(dut, "dma"), dut.clk_i, dut.rst_ni,
                     reset_active_level=False, target=memory)

    for _ in range(12):
        await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk_i)

    irq_count = [0]
    irq_times = []

    async def watch_irq():
        # IRQ in the pinned frontend is combinational BVALID/BREADY, not
        # a registered interrupt. Sample one stable phase per clock to
        # avoid counting intra-cycle combinational/VPI value changes.
        last = False
        while True:
            await FallingEdge(dut.clk_i)
            await Timer(1, units="ns")
            active = bool(int(dut.irq_o.value))
            if active and not last:
                irq_count[0] += 1
                timestamp = str(get_sim_time(units='ns'))
                irq_times.append(timestamp)
                dut._log.info("DMA IRQ sampled at %s ns, bvalid=%d bready=%d", timestamp,
                              int(dut.dma_bvalid.value), int(dut.dma_bready.value))
            last = active

    irq_task = cocotb.start_soon(watch_irq())
    # Exercise long prefetch and final-IRQ semantics before pool reuse, then
    # submit an independent one-descriptor chain to the other memory model.
    for count, destination in ((100, "memory0.ddr0"), (1, "memory0.hbm0")):
        case = build_dma_vector(cfg, count=count, length=64,
                                destination=destination, profile="dma_only")
        manifest = case.manifest
        # Host-side memory initialization avoids thousands of very slow CPU
        # SRAM stores. NEVER enable this in the cold-boot regression.
        await memory.write(manifest["source_sram_base"], case.source_sram)
        expected_irq = irq_count[0] + 1
        await submit(dut, manifest["descriptor_head"])
        for _ in range(20000):
            if irq_count[0] >= expected_irq:
                break
            await RisingEdge(dut.clk_i)
        else:
            raise AssertionError("DMA expected IRQ timeout")
        await await_idle(dut)
        await Timer(100, units="ns")
        assert irq_count[0] == expected_irq, (
            f"DMA IRQ count {irq_count[0]} != {expected_irq} for {count} descriptors; "
            f"IRQ times (ns)={irq_times}")

        # Verify real AXI data movement with independently prepared golden bytes.
        for copy in manifest["copies"]:
            actual = await memory.read(copy["dst"], copy["length"])
            assert bytes(actual) == bytes.fromhex(copy["expected_hex"]), (
                f"DMA destination mismatch descriptor={copy['descriptor']:#x}")
            # The pinned desc64 frontend must issue a real completion writeback
            # over AXI, not merely assert IRQ or skip executing the descriptor.
            header = await memory.read(copy["descriptor"], 8)
            assert bytes(header) == b"\xff"*8, (
                f"DMA descriptor writeback missing at {copy['descriptor']:#x}")
        dut._log.info("PASS DMA real AXI: %d descriptor(s), destination %s, IRQ=%d times=%s",
                      count, destination, irq_count[0], irq_times)

    assert irq_count[0] == 2
    irq_task.kill()
    dut._log.info("PASS dma-rtl: 1 + 100 real PULP iDMA descriptors and 2 IRQs")
