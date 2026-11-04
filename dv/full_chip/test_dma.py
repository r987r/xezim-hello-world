"""Real iDMA0/iDMA1 -> generated local/global FlooNoCs -> SRAM/DDR/HBM.

This is a separate reset-isolated hardware regression. CPUs are held in
reset and their data/config AXI masters are replaced by the host BFMs solely
to prepare SRAM and submit real 32-bit CSR transactions through the fabric.
The independently required cold-boot regression remains unpreloaded.
"""
from pathlib import Path
import json
import yaml
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
from cocotbext.axi import AxiBus, AxiMaster
from dv.common.dma_vectors import build_dma_vector
from dv.common.axi_trace import attach_observers, trace_phase

ROOT = Path(__file__).resolve().parents[2]


async def bounded(coro, what, timeout=250):
    try:
        return await with_timeout(coro, timeout, "us")
    except cocotb.result.SimTimeoutError as exc:
        raise AssertionError(f"AXI timeout during {what}") from exc


async def check_ok(resp, what):
    assert resp.resp == 0, f"{what}: unexpected AXI response {resp.resp}"


async def prep_sram(host, case):
    """Seed only dedicated DMA descriptors/payloads via real NoC AXI writes.

    No CPU core performs 2,400 slow individual stores. Writes are split into
    16-beat/128-byte bursts, matching FlooNoC's configured burst capacity.
    """
    meta = case.manifest
    src = case.source_sram
    base = meta["source_sram_base"]
    desc = meta["descriptor_pool_start"]-base
    payload = meta["source_pool_start"]-base
    sections = [(desc, 32*meta["descriptor_count"]),
                (payload, meta["descriptor_count"]*meta["copies"][0]["length"])]
    for offset, size in sections:
        for p in range(0, size, 128):
            block = src[offset+p:offset+min(p+128, size)]
            res = await bounded(host.write(base+offset+p, block), "SRAM preload")
            await check_ok(res, "SRAM preload")


async def write_word(host, addr, value):
    resp = await bounded(host.write(addr, value.to_bytes(4, "little")),
                         f"CSR write {addr:#x}")
    await check_ok(resp, f"CSR write {addr:#x}")


async def read_word(host, addr):
    resp = await bounded(host.read(addr, 4), f"CSR read {addr:#x}")
    await check_ok(resp, f"CSR read {addr:#x}")
    return int.from_bytes(resp.data, "little")


@cocotb.test(timeout_time=15, timeout_unit="ms")
async def two_compute_dmas_through_all_fabrics(dut):
    cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())
    mem = json.loads((ROOT/"gen/chip/manifest.json").read_text())
    computes = [s["name"] for s in cfg["subsystems"] if s["type"]=="compute"]
    assert mem["dma_engines_instantiated"] == len(computes) == 2
    dut.rst_ni.value = 0
    dut.clk_i.value = 0
    attach_observers(dut)
    cocotb.start_soon(Clock(dut.clk_i, 10, "ns").start())
    # The existing 64-bit AXI probe now occupies CPU0's data manager slot
    # exclusively in this generated DmaTestMode. Real DMA owns the DMA slot.
    data = AxiMaster(AxiBus.from_prefix(dut, "probe"),
                     dut.clk_i, dut.rst_ni, reset_active_level=False)
    # The 32-bit config AXI probe reaches SS0 and SS1 through the genuine
    # config FlooNoCs (single-beat AXI4 transport, AXI-Lite CSR bridge).
    control = AxiMaster(AxiBus.from_prefix(dut, "cfgprobe"),
                        dut.clk_i, dut.rst_ni, reset_active_level=False)
    for _ in range(15):
        await FallingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    for _ in range(8):
        await RisingEdge(dut.clk_i)

    checks = [
        (computes[0], "memory0.ddr0", 100, 64),
        (computes[1], "memory0.hbm0", 4, 64),
    ]
    csr_by_name = {r["name"]: int(r["base"],0)
                   for r in cfg["address_map"]["config"]}
    for i, (compute, target, count, nbytes) in enumerate(checks):
        case = build_dma_vector(cfg, subsystem=compute, destination=target,
                                count=count, length=nbytes, profile="dma_only")
        head = case.manifest["descriptor_head"]
        trace_phase(f'{compute}: host populates descriptor/source SRAM over actual NoCs')
        await prep_sram(data, case)
        csr = csr_by_name[compute+".dma"]
        # Two 32-bit writes to shared SRAM-staged 64-bit descriptor pointer.
        # The following doorbell atomically commits that pointer to upstream
        # 64-bit iDMA APB. For SS1 these writes cross global config FlooNoC.
        await write_word(control, csr+0, head & 0xffffffff)
        await write_word(control, csr+4, head >> 32)
        assert await read_word(control, csr+0) == (head & 0xffffffff)
        trace_phase(f'{compute}: submit native iDMA head through 32-bit CSR NoC')
        await write_word(control, csr+8, 1)
        # Testbench observes sticky IRQ; CPUs do not spin/poll descriptors.
        for _ in range(60000):
            if int(dut.dma_irq_pending_o.value) & (1 << i):
                break
            await RisingEdge(dut.clk_i)
        else:
            raise AssertionError(f"DMA IRQ timeout in {compute} -> {target}")
        status = await read_word(control, csr+12)
        assert status & 2, f"DMA completion bit absent in {compute}: {status:#x}"
        assert not status & 4, f"DMA APB submission error in {compute}: {status:#x}"
        trace_phase(f'{compute}: verify real DMA destination + completion writebacks')
        for entry in case.manifest["copies"]:
            # Every payload byte is read back over the same real NoC graph,
            # not an internal SRAM memory handle or a mock DMA scoreboard.
            rd = await bounded(data.read(entry["dst"], entry["length"]),
                               f"readback {target}")
            await check_ok(rd, "DMA target readback")
            assert bytes(rd.data) == bytes.fromhex(entry["expected_hex"]), (
                f"{compute} descriptor {entry['descriptor']:#x} corrupted {target}")
            wb = await bounded(data.read(entry["descriptor"], 8),
                               "descriptor writeback")
            await check_ok(wb, "descriptor writeback")
            assert wb.data == b"\xff"*8, (
                f"{compute} descriptor completion writeback missing")
        await write_word(control, csr+8, 2)
        for _ in range(300):
            if not (int(dut.dma_irq_pending_o.value) & (1 << i)):
                break
            await RisingEdge(dut.clk_i)
        else:
            raise AssertionError(f"IRQ acknowledge did not clear for {compute}")
        dut._log.info("PASS chipdma: %s %d real descriptors -> %s over full NoC",
                      compute, count, target)
    dut._log.info("PASS chipdma: both compute DMA engines, 104 real transfers, "
                  "local/global data and configuration FlooNoCs, DDR/HBM")
