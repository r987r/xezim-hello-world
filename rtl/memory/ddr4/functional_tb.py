"""Isolated functional smoke: pinned LiteDRAM RTL + DFI simulation PHY.

Drives generated Wishbone CSR interface and upstream DDR4 init commands.
AXI data accesses must pass against actual controller/PHY, not AXI RAM.
"""
from __future__ import annotations
import itertools
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer, with_timeout
from cocotbext.axi import AxiBus, AxiMaster, AxiResp
from init_plan import wishbone_script

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


async def observe_axi(dut, counts):
    names = ("aw", "w", "b", "ar", "r")
    while True:
        await RisingEdge(dut.clk)
        for channel in names:
            val = int(getattr(dut, f"user_port_axi_0_{channel}valid").value)
            ready = int(getattr(dut, f"user_port_axi_0_{channel}ready").value)
            if val:
                counts[f"{channel}_valid"] = counts.get(f"{channel}_valid", 0) + 1
            if ready:
                counts[f"{channel}_ready"] = counts.get(f"{channel}_ready", 0) + 1
            if val and ready:
                counts[f"{channel}_handshake"] = counts.get(f"{channel}_handshake", 0) + 1
                if channel == "r":
                    counts["r_last"] = counts.get("r_last", 0) + int(dut.user_port_axi_0_rlast.value)
                    counts["r_id_last"] = int(dut.user_port_axi_0_rid.value)
                    counts["r_resp_last"] = int(dut.user_port_axi_0_rresp.value)
                    counts["r_data_last"] = hex(int(dut.user_port_axi_0_rdata.value))
                if channel == "ar":
                    counts["ar_id_last"] = int(dut.user_port_axi_0_arid.value)
                    counts["ar_len_last"] = int(dut.user_port_axi_0_arlen.value)
                if channel == "b":
                    counts["b_id_last"] = int(dut.user_port_axi_0_bid.value)
                    counts["b_resp_last"] = int(dut.user_port_axi_0_bresp.value)


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
    dut.clk.value = 0
    dut.sim_trace.value = 0
    for name in ("wb_ctrl_adr", "wb_ctrl_dat_w", "wb_ctrl_sel",
                 "wb_ctrl_cti", "wb_ctrl_bte", "wb_ctrl_cyc", "wb_ctrl_stb", "wb_ctrl_we"):
        getattr(dut, name).value = 0
    for name in ("user_port_axi_0_awvalid", "user_port_axi_0_wvalid",
                 "user_port_axi_0_arvalid", "user_port_axi_0_bready",
                 "user_port_axi_0_rready"):
        getattr(dut, name).value = 0
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await tick(dut, 10)
    assert not int(dut.user_rst.value), "simulation reset did not release"
    assert not int(dut.init_done.value), "DDR must be explicitly initialized"
    assert not int(dut.init_error.value), "unexpected initial DDR error"
    assert not int(dut.user_port_axi_0_awready.value), "AXI must be gated before init"
    # Match other known-good cocotbext-axi testbenches: create the five
    # channel source/sink tasks near reset, not after 1.2ms of DDR init.
    master = AxiMaster(AxiBus.from_prefix(dut, "user_port_axi_0"),
                       dut.user_clk, dut.user_rst, reset_active_level=True)
    # Legitimate AXI read backpressure also avoids a single-cycle response
    # disappearing at the Verilator/VPI read-monitor scheduling boundary.
    # Keep the upstream AXI monitor and payload/response assertions enabled.
    master.read_if.r_channel.set_pause_generator(itertools.cycle([1, 1, 1, 0, 0]))
    await tick(dut, 16)
    await initialize(dut)
    await tick(dut, 16)
    counts = {}
    monitor = cocotb.start_soon(observe_axi(dut, counts))
    try:
        # A read before a write separates DFI/scheduler readiness from the
        # write-buffer path and the AW/W two-channel arbitration.
        probe = await with_timeout(master.read(0x4000, 8, arid=0), 80, "us")
        assert probe.resp == AxiResp.OKAY, f"DDR4 initial read response: {probe}"
        dut._log.info("PASS DDR4 prewrite read: controller returned R channel data")
    except Exception:
        dut._log.error("DDR4 read-side failure: pins=%s counts=%s active_id=%s r_fifo=%s",
                       axi_snapshot(dut), counts,
                       getattr(master.read_if, "active_id", None),
                       master.read_if.r_channel.count())
        raise
    try:
        await transfer(master, dut, 0x4000, bytes((i*17+3)&255 for i in range(64)), 1)
    except Exception:
        dut._log.error("DDR4 write-side failure: pins=%s counts=%s", axi_snapshot(dut), counts)
        raise
    finally:
        monitor.kill()
    await transfer(master, dut, 0x8000, bytes((i*37+7)&255 for i in range(32)), 2)
    initial = bytes([0xA5])*24
    await transfer(master, dut, 0x9000, initial, 3)
    wr = await with_timeout(master.write(0x9005, b"\x01\x23\x45\x67\x89", awid=3), 80, "us")
    assert wr.resp == AxiResp.OKAY
    expected = initial[:5] + b"\x01\x23\x45\x67\x89" + initial[10:]
    rd = await with_timeout(master.read(0x9000, len(initial), arid=3), 80, "us")
    assert rd.resp == AxiResp.OKAY and rd.data == expected, \
        f"DDR4 byte-strobe guard mismatch: {rd.data.hex()}"
    dut._log.info("PASS actual LiteDRAM DDR4 init and AXI burst/ID/WSTRB integrity")
