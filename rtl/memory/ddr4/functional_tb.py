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
from dfi_probe import DFIProbe, observe_dfi
from traffic_observer import TrafficObserver, observe_forever
from stress_matrix import Burst, build_matrix, enabled_lane_runs, expected_write, pattern_byte

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



async def exercise_controller_stress(master, dut, observer, monitor):
    """Real LiteDRAM AXI+DFI stress, not a pure-Python oracle pass.

    The existing passive AXI/Wishbone and 72-net DFI monitors stay active.
    cocotbext-axi 0.1.28 produces a WSTRB mask for unaligned contiguous
    byte writes; sparse masks are decomposed into separate legal writes.
    No external BFM or fake memory backend is substituted.
    """
    cases = build_matrix(aperture_bytes=32 * 1024 * 1024, data_bits=64,
                         id_bits=4, seed=0x2d41)
    writes = [case for case in cases if case.kind == "write"]
    reads = [case for case in cases if case.kind == "read"]
    assert len(writes) == len(reads) == 4
    completed = 0
    for case, rd_case in zip(writes, reads):
        assert (case.address, case.beats, case.id) == (
            rd_case.address, rd_case.beats, rd_case.id)
        size = case.beats * 8
        initial = bytes([0x5a] * size)
        resp = await with_timeout(master.write(case.address, initial,
                                                awid=case.id), 80, "us")
        assert resp.resp == AxiResp.OKAY, f"DDR4 stress init B error {case}"
        # First confirm the long burst is intact. A previously passing
        # functional smoke does not cover 1/4/8/16-beat transfers.
        base = await with_timeout(master.read(case.address, size, arid=case.id),
                                  80, "us")
        assert base.resp == AxiResp.OKAY and base.data == initial, (
            f"DDR4 stress baseline mismatch @{case.address:#x}")
        # Exercise one selected AXI beat's actual hardware strobe lanes.
        # The untouched beats make an independent protection guard.
        selected = case.beats - 1
        beat_addr = case.address + selected * 8
        change = Burst(beat_addr, 1, case.id, case.strobe, case.pattern, "write")
        expected_beat = expected_write(initial[selected * 8:selected * 8 + 8],
                                       change, 8)
        for first, end in enabled_lane_runs(case.strobe, 8):
            payload = bytes(pattern_byte(beat_addr + lane, case.pattern)
                            for lane in range(first, end))
            result = await with_timeout(
                master.write(beat_addr + first, payload, awid=case.id),
                80, "us")
            assert result.resp == AxiResp.OKAY, (
                f"DDR4 stress masked B error @{beat_addr + first:#x}")
        expected = (initial[:selected * 8] + expected_beat +
                    initial[(selected + 1) * 8:])
        final = await with_timeout(master.read(case.address, size, arid=case.id),
                                   80, "us")
        assert final.resp == AxiResp.OKAY and final.data == expected, (
            f"DDR4 stress masked data/alias mismatch @{case.address:#x}: "
            f"{final.data.hex()} != {expected.hex()}")
        observer.assert_health(monitor)
        completed += 1
    assert completed == 4, "DDR4 stress cases were skipped"
    dut._log.info("PASS real LiteDRAM stress: 4 address regions, "
                  "1/4/8/16 AXI beats, IDs 0/15, actual byte strobes and "
                  "full-burst readback; DFI and AXI observers active")



async def exercise_concurrent_axi_ids(master, dut, observer, monitor):
    """Concurrent real RTL requests across independent DDR addresses and IDs.

    Tasks start before any completion is awaited, so the cocotbext-axi
    master can keep more than one request outstanding. Independent data
    readback and the passive AW/W/B/AR/R/DFI observer remain mandatory.
    This does not imply a measured minimum number of simultaneous
    controller-internal outstanding transactions or forced backpressure.
    """
    addresses = (0x18000, 0x28000, 0x38000, 0x48000)
    ids = (0, 5, 10, 15)
    payloads = tuple(bytes(((i * 41 + j * 13 + 7) & 0xff)
                           for j in range(128)) for i in range(4))
    writes = [cocotb.start_soon(master.write(addr, data, awid=ident))
              for addr, data, ident in zip(addresses, payloads, ids)]
    for index, task in enumerate(writes):
        response = await with_timeout(task, 120, "us")
        assert response.resp == AxiResp.OKAY, (
            f"concurrent DDR4 write {index} B response {response.resp}")
    reads = [cocotb.start_soon(master.read(addr, len(data), arid=ident))
             for addr, data, ident in zip(addresses, payloads, ids)]
    for index, task in enumerate(reads):
        response = await with_timeout(task, 120, "us")
        assert response.resp == AxiResp.OKAY, (
            f"concurrent DDR4 read {index} R response {response.resp}")
        assert response.data == payloads[index], (
            f"concurrent DDR4 data mismatch id={ids[index]} "
            f"addr={addresses[index]:#x}")
    observer.assert_health(monitor)
    dut._log.info("PASS real LiteDRAM concurrent AXI: four queued "
                  "writes + four queued reads, IDs 0/5/10/15, "
                  "128-byte independent readback and passive DFI capture")



async def exercise_real_axi_response_backpressure(master, dut, observer, monitor):
    """Hold real BREADY/RREADY low and check stable pin-level DDR responses.

    This intentionally uses the existing pinned cocotbext-axi sink pause
    API, not a new bus driver. Observing BVALID/RVALID while !READY is
    required; merely toggling pause without seeing a real stall is a FAIL.
    """
    address = 0x5c000
    ident = 9
    payload = bytes((i * 19 + 0x27) & 0xff for i in range(64))

    async def hold_until_valid(channel, cycles=1200):
        ready = getattr(dut, f"user_port_axi_0_{channel}ready")
        valid = getattr(dut, f"user_port_axi_0_{channel}valid")
        for _ in range(cycles):
            await tick(dut)
            if int(valid.value) and not int(ready.value):
                return
        raise AssertionError(
            f"DDR4 {channel.upper()} response never stalled with VALID && !READY")

    # AW/W can legally arrive in either order; the passive AXI correlator
    # reconciles accepted W beats and enforces AWLEN/WLAST/BID.
    master.write_if.b_channel.pause = True
    write_task = cocotb.start_soon(master.write(address, payload, awid=ident))
    try:
        await hold_until_valid("b")
        stable = tuple(int(getattr(dut, f"user_port_axi_0_b{name}").value)
                       for name in ("id", "resp"))
        for _ in range(20):
            await tick(dut)
            assert int(dut.user_port_axi_0_bvalid.value), (
                "LiteDRAM BVALID dropped under BREADY backpressure")
            assert not int(dut.user_port_axi_0_bready.value), (
                "DDR4 BREADY unexpectedly asserted during forced stall")
            assert stable == tuple(int(getattr(dut, f"user_port_axi_0_b{name}").value)
                                   for name in ("id", "resp")), (
                "LiteDRAM BID/BRESP changed under stall")
        assert stable == (ident, int(AxiResp.OKAY)), (
            f"DDR4 stalled write response differs: {stable}")
    finally:
        master.write_if.b_channel.pause = False
    write = await with_timeout(write_task, 120, "us")
    assert write.resp == AxiResp.OKAY, "stalled LiteDRAM B did not complete"

    master.read_if.r_channel.pause = True
    read_task = cocotb.start_soon(master.read(address, len(payload), arid=ident))
    try:
        await hold_until_valid("r")
        stable = tuple(int(getattr(dut, f"user_port_axi_0_r{name}").value)
                       for name in ("id", "data", "resp", "last"))
        for _ in range(20):
            await tick(dut)
            assert int(dut.user_port_axi_0_rvalid.value), (
                "LiteDRAM RVALID dropped under RREADY backpressure")
            assert not int(dut.user_port_axi_0_rready.value), (
                "DDR4 RREADY unexpectedly asserted during forced stall")
            assert stable == tuple(int(getattr(dut, f"user_port_axi_0_r{name}").value)
                                   for name in ("id", "data", "resp", "last")), (
                "LiteDRAM RID/RDATA/RRESP/RLAST changed under stall")
        assert stable[0] == ident and stable[2] == int(AxiResp.OKAY), (
            f"DDR4 stalled read ID/response mismatch: {stable}")
    finally:
        master.read_if.r_channel.pause = False
    read = await with_timeout(read_task, 120, "us")
    assert read.resp == AxiResp.OKAY and read.data == payload, (
        "LiteDRAM R after forced backpressure did not match golden data")
    observer.assert_health(monitor)
    dut._log.info("PASS real LiteDRAM B/R backpressure: actual VALID && !READY, "
                  "20 stable cycles per response, original ID/data, "
                  "complete B/R and independent passive AXI/DFI capture")


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
    internal = DFIProbe(OUTPUT)
    internal_task = cocotb.start_soon(
        observe_dfi(dut, internal, observer, configured_clock_period_ps())
    )
    succeeded = False
    failure = None
    try:
        period_ps = configured_clock_period_ps()
        assert period_ps == 10000, "source clock and DDR4 100 MHz sim profile disagree"
        cocotb.start_soon(Clock(dut.clk, period_ps, units="ps").start())
        await tick(dut, 10)
        observer.assert_health(monitor, min_samples=9)
        internal.assert_alive(internal_task)
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

        # Check reduced geometry did not silently alias high DDR addresses.
        # The generated model has 32 MiB backed storage, not the 1 GiB
        # architectural aperture. Exercise both ends and a bank-sized offset,
        # then reread earlier locations AFTER later writes to detect aliasing.
        geometry_vectors = (
            (0x0000000, bytes((i * 13 + 0x31) & 255 for i in range(64)), 4),
            (0x07fffc0, bytes((i * 19 + 0x57) & 255 for i in range(64)), 5),
            (0x1ffffc0, bytes((i * 29 + 0x83) & 255 for i in range(64)), 6),
        )
        for address, payload, ident in geometry_vectors:
            write_result = await with_timeout(master.write(address, payload, awid=ident), 80, "us")
            assert write_result.resp == AxiResp.OKAY, "DDR geometry write response mismatch"
        for address, payload, ident in geometry_vectors:
            read_result = await with_timeout(master.read(address, len(payload), arid=ident), 80, "us")
            assert read_result.resp == AxiResp.OKAY, "DDR geometry read response mismatch"
            assert read_result.data == payload, (
                f"DDR geometry alias/truncation at {address:#x}: "
                f"{read_result.data.hex()} != {payload.hex()}")
        dut._log.info("PASS DDR4 modeled 32MiB low/mid/high address alias guard")

        await exercise_controller_stress(master, dut, observer, monitor)
        await exercise_concurrent_axi_ids(master, dut, observer, monitor)
        await exercise_real_axi_response_backpressure(master, dut, observer, monitor)
        observer.assert_health(monitor)
        observer.next_phase("post_traffic")
        await tick(dut, 5)
        observer.assert_health(monitor)
        observer.assert_complete()
        internal.assert_alive(internal_task)
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
        if not internal_task.done():
            internal_task.kill()
        observer.finish("pass" if succeeded else "fail",
                        error=None if succeeded else repr(failure))
        internal.finish("pass" if succeeded else "fail",
                        error=None if succeeded else repr(failure))
