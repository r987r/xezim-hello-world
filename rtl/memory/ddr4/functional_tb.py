"""Isolated functional smoke: pinned LiteDRAM RTL + DFI simulation PHY.

Drives generated Wishbone CSR interface and upstream DDR4 init commands.
AXI data accesses must pass against actual controller/PHY, not AXI RAM.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
from cocotbext.axi import AxiBus, AxiMaster, AxiResp
from init_plan import wishbone_script
from latency_report import configured_clock_period_ps
from traffic_observer import TrafficObserver, observe_forever

OUTPUT = Path(os.environ["DDR4_GENERATED_DIR"])
PLAN = json.loads((OUTPUT / "ddr4_init_plan.json").read_text())
CSR = json.loads((OUTPUT / "csr.json").read_text())


async def tick(dut, count=1):
    for _ in range(count):
        await RisingEdge(dut.clk)
    await Timer(1, units="ns")


async def wb_write(dut, addr, value):
    assert addr % 4 == 0
    await FallingEdge(dut.clk)
    dut.wb_ctrl_adr.value = addr // 4
    dut.wb_ctrl_dat_w.value = value
    dut.wb_ctrl_sel.value = 15
    dut.wb_ctrl_cti.value = 0
    dut.wb_ctrl_bte.value = 0
    dut.wb_ctrl_we.value = 1
    dut.wb_ctrl_stb.value = 1
    dut.wb_ctrl_cyc.value = 1
    try:
        for _ in range(64):
            await tick(dut)
            if int(dut.wb_ctrl_ack.value):
                assert not int(dut.wb_ctrl_err.value), f"Wishbone write error at {addr:#x}"
                return
        raise AssertionError(f"Wishbone write timeout at CSR {addr:#x}")
    finally:
        await FallingEdge(dut.clk)
        dut.wb_ctrl_cyc.value = 0
        dut.wb_ctrl_stb.value = 0
        dut.wb_ctrl_we.value = 0
        await tick(dut)


async def wb_read(dut, addr):
    assert addr % 4 == 0
    await FallingEdge(dut.clk)
    dut.wb_ctrl_adr.value = addr // 4
    dut.wb_ctrl_dat_w.value = 0
    dut.wb_ctrl_sel.value = 15
    dut.wb_ctrl_cti.value = 0
    dut.wb_ctrl_bte.value = 0
    dut.wb_ctrl_we.value = 0
    dut.wb_ctrl_stb.value = 1
    dut.wb_ctrl_cyc.value = 1
    try:
        for _ in range(64):
            await tick(dut)
            if int(dut.wb_ctrl_ack.value):
                assert not int(dut.wb_ctrl_err.value), f"Wishbone read error at {addr:#x}"
                return int(dut.wb_ctrl_dat_r.value)
        raise AssertionError(f"Wishbone read timeout at CSR {addr:#x}")
    finally:
        await FallingEdge(dut.clk)
        dut.wb_ctrl_cyc.value = 0
        dut.wb_ctrl_stb.value = 0
        await tick(dut)


async def initialize(dut):
    script = wishbone_script(PLAN, CSR, delay_multiplier=2)
    for i, op in enumerate(script):
        if op["op"] == "write":
            await wb_write(dut, op["byte_address"], op["value"])
        elif op["op"] == "wait":
            await tick(dut, op["cycles"])
        else:
            raise AssertionError(f"unknown initialization step {i}: {op}")
    await tick(dut, 32)
    assert int(dut.init_done.value), "LiteX init_done not asserted"
    assert not int(dut.init_error.value), "LiteX init_error asserted"
    regs = CSR["csr_registers"]
    assert await wb_read(dut, regs["ddrctrl_init_done"]["addr"]) & 1
    assert not (await wb_read(dut, regs["ddrctrl_init_error"]["addr"]) & 1)
    assert await wb_read(dut, regs["sdram_dfii_control"]["addr"]) & 1, "DFII handoff missing"
    dut._log.info("DDR4 DFII initialization and software status handoff complete")


def axi_snapshot(dut):
    # Top-level pin observations only; do not rely on simulator-private
    # internal objects or suppress upstream assertions.
    names = (
        "user_port_axi_0_awvalid", "user_port_axi_0_awready",
        "user_port_axi_0_wvalid", "user_port_axi_0_wready",
        "user_port_axi_0_bvalid", "user_port_axi_0_bready",
        "user_port_axi_0_arvalid", "user_port_axi_0_arready",
        "user_port_axi_0_rvalid", "user_port_axi_0_rready",
        "init_done", "init_error", "user_rst",
    )
    return {name: int(getattr(dut, name).value) for name in names}


async def transfer(master, dut, address, data, ident):
    wr = await with_timeout(master.write(address, data, awid=ident), 80, "us")
    assert wr.resp == AxiResp.OKAY, f"AXI B error {address:#x}: {wr}"
    rd = await with_timeout(master.read(address, len(data), arid=ident), 80, "us")
    assert rd.resp == AxiResp.OKAY, f"AXI R error {address:#x}: {rd}"
    assert rd.data == data, f"controller/DFI read mismatch @{address:#x}: {rd.data.hex()} != {data.hex()}"
    dut._log.info("PASS DDR4 controller/DFI readback @0x%x size=%d id=%d",
                  address, len(data), ident)


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def ddr4_wishbone_init_axi_readwrite(dut):
    """One always-active passive observer from before clock start to teardown."""
    dut.clk.value = 0
    dut.sim_trace.value = 0
    for name in ("wb_ctrl_adr", "wb_ctrl_dat_w", "wb_ctrl_sel",
                 "wb_ctrl_cti", "wb_ctrl_bte", "wb_ctrl_cyc", "wb_ctrl_stb", "wb_ctrl_we"):
        getattr(dut, name).value = 0
    for name in ("user_port_axi_0_awvalid", "user_port_axi_0_wvalid",
                 "user_port_axi_0_arvalid", "user_port_axi_0_bready",
                 "user_port_axi_0_rready"):
        getattr(dut, name).value = 0

    # Unlike an ad hoc debug monitor, this begins BEFORE the first clock edge
    # and must run throughout initialization and ALL AXI operations. It is
    # independent of cocotbext-axi's protocol-aware BFM/response scoreboard.
    observer = TrafficObserver(OUTPUT)
    monitor = cocotb.start_soon(observe_forever(dut, observer))
    succeeded = False
    failure = None
    try:
        period_ps = configured_clock_period_ps()
        assert period_ps == 10000, "source clock and DDR4 100 MHz sim profile disagree"
        cocotb.start_soon(Clock(dut.clk, period_ps, units="ps").start())
        await tick(dut, 10)
        observer.assert_health(monitor, min_samples=9)
        assert not int(dut.user_rst.value), "simulation reset did not release"
        assert not int(dut.init_done.value), "DDR must be explicitly initialized"
        assert not int(dut.init_error.value), "unexpected initial DDR error"
        assert not int(dut.user_port_axi_0_awready.value), \
            "AXI must be gated before init"

        # LiteDRAM's SimPlatform CRG directly aliases user_clk to clk.
        # Use the source pin as the cocotb BFM sampling clock to eliminate
        # combinational clock-alias delta-cycle scheduling ambiguity while
        # continuing to drive real generated AXI/DFI RTL.
        master = AxiMaster(AxiBus.from_prefix(dut, "user_port_axi_0"),
                           dut.clk, dut.user_rst, reset_active_level=True)
        # Baseline must not depend on an optional RREADY pause experiment.
        # No passive observer or active bus checker is disabled.

        await tick(dut, 16)
        observer.next_phase("initialization")
        await initialize(dut)
        observer.assert_health(monitor)
        await tick(dut, 16)
        observer.next_phase("traffic")

        try:
            # Read before write isolates DFI/scheduler availability from
            # AW/W buffering. Uninitialized contents need not match a value.
            probe = await with_timeout(master.read(0x4000, 8, arid=0), 80, "us")
            assert probe.resp == AxiResp.OKAY, f"DDR4 initial read response: {probe}"
            dut._log.info("PASS DDR4 prewrite read: controller returned R channel data")
        except Exception:
            dut._log.error("DDR4 initial read timeout: pins=%s captured=%s "
                           "active_id=%s r_fifo=%s",
                           axi_snapshot(dut), observer.last_by_channel,
                           getattr(master.read_if, "active_id", None),
                           master.read_if.r_channel.count())
            raise
        observer.assert_health(monitor)

        await transfer(master, dut, 0x4000, bytes((i*17+3)&255 for i in range(64)), 1)
        await transfer(master, dut, 0x8000, bytes((i*37+7)&255 for i in range(32)), 2)
        initial = bytes([0xA5])*24
        await transfer(master, dut, 0x9000, initial, 3)
        wr = await with_timeout(master.write(0x9005, b"\x01\x23\x45\x67\x89", awid=3), 80, "us")
        assert wr.resp == AxiResp.OKAY
        expected = initial[:5] + b"\x01\x23\x45\x67\x89" + initial[10:]
        rd = await with_timeout(master.read(0x9000, len(initial), arid=3), 80, "us")
        assert rd.resp == AxiResp.OKAY and rd.data == expected, \
            f"DDR4 byte-strobe guard mismatch: {rd.data.hex()}"

        observer.assert_health(monitor)
        observer.next_phase("post_traffic")
        await tick(dut, 5)
        observer.assert_health(monitor)
        observer.assert_complete()
        succeeded = True
        dut._log.info("PASS actual LiteDRAM DDR4 AXI integrity with continuous monitoring")
    except Exception as exc:
        failure = exc
        dut._log.error("DDR4 functional failure; continuous monitor: "
                       "phase=%s cycles=%d channels=%s wb=%s last=%s",
                       observer.phase, observer.samples,
                       dict(observer.channels), dict(observer.wishbone),
                       observer.last_by_channel)
        raise
    finally:
        # Never end capture after just one transfer. Even failing tests write
        # a partial trace/summary before the exception is reported to CI.
        if not monitor.done():
            monitor.kill()
        observer.finish("pass" if succeeded else "fail",
                        error=None if succeeded else repr(failure))
