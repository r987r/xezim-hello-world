"""Real PULP iDMA AXI descriptor + payload traffic, no CPU preload shortcut.

Only this isolated DMA scope seeds AXI SRAM directly; the existing cold-boot
regression always runs real CPU flash-to-SRAM copies.
"""
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
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

    async def watch_irq():
        while True:
            await RisingEdge(dut.irq_o)
            irq_count[0] += 1

    irq_task = cocotb.start_soon(watch_irq())
    # One immediate interrupt, followed by a long 100-descriptor chain.
    for count, destination in ((1, "memory0.hbm0"), (100, "memory0.ddr0")):
        case = build_dma_vector(cfg, count=count, length=64,
                                destination=destination, profile="dma_only")
        manifest = case.manifest
        # Host-side memory initialization avoids thousands of very slow CPU
        # SRAM stores. NEVER enable this in the cold-boot regression.
        await memory.write(manifest["source_sram_base"], case.source_sram)
        expected_irq = irq_count[0] + 1
        await submit(dut, manifest["descriptor_head"])
        await with_timeout(RisingEdge(dut.irq_o), 200, "us")
        await Timer(100, units="ns")
        assert irq_count[0] == expected_irq, (
            f"DMA IRQ count {irq_count[0]} != {expected_irq} for {count} descriptors")

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
        dut._log.info("PASS DMA real AXI: %d descriptor(s), destination %s, IRQ=%d",
                      count, destination, irq_count[0])

    assert irq_count[0] == 2
    irq_task.kill()
    dut._log.info("PASS dma-rtl: 1 + 100 real PULP iDMA descriptors and 2 IRQs")
