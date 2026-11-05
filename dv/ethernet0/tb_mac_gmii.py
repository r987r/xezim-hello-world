"""Standalone REAL Ethernet0 GMII RX/TX RTL Cocotb regression.

Cocotbext models the external Ethernet peer. The DUT contains unmodified
upstream axis_gmii_rx/tx and dual-clock upstream axis_async_fifo RTL.
This is not a DMA, packet classifier, NoC, PHY, or SoC test.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
from cocotbext.axi import AxiStreamBus, AxiStreamSink, AxiStreamSource, AxiStreamFrame
from cocotbext.eth import GmiiSource, GmiiSink, GmiiFrame


async def setup(dut):
    dut.logic_rst.value = 1
    dut.gmii_tx_rst.value = 1
    dut.gmii_rx_rst.value = 1
    dut.tx_enable.value = 1
    dut.rx_enable.value = 1
    dut.gmii_rxd.value = 0
    dut.gmii_rx_dv.value = 0
    dut.gmii_rx_er.value = 0
    cocotb.start_soon(Clock(dut.gmii_tx_clk, 8, units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_rx_clk, 8, units="ns").start())
    cocotb.start_soon(Clock(dut.logic_clk, 10, units="ns").start())
    source = GmiiSource(dut.gmii_rxd, dut.gmii_rx_er, dut.gmii_rx_dv,
                        dut.gmii_rx_clk, dut.gmii_rx_rst)
    sink = GmiiSink(dut.gmii_txd, dut.gmii_tx_er, dut.gmii_tx_en,
                    dut.gmii_tx_clk, dut.gmii_tx_rst)
    axis_tx = AxiStreamSource(AxiStreamBus.from_prefix(dut, "tx_axis"),
                              dut.logic_clk, dut.logic_rst)
    axis_rx = AxiStreamSink(AxiStreamBus.from_prefix(dut, "rx_axis"),
                            dut.logic_clk, dut.logic_rst)
    await Timer(100, units="ns")
    dut.gmii_tx_rst.value = 0
    dut.gmii_rx_rst.value = 0
    dut.logic_rst.value = 0
    for _ in range(20):
        await RisingEdge(dut.logic_clk)
    return source, sink, axis_tx, axis_rx


async def bounded_recv(queue, what):
    try:
        return await with_timeout(queue.recv(), 350, "us")
    except cocotb.result.SimTimeoutError as exc:
        raise AssertionError(f"timeout receiving {what}") from exc


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def rx_and_tx_over_real_gmii_mac_and_async_fifos(dut):
    src, sink, axis_tx, axis_rx = await setup(dut)
    payloads = [
        bytes((i * 17 + j) & 0xff for j in range(length))
        for i, length in enumerate((60, 85, 127, 513, 1514))
    ]
    # RX: GMII BFM -> real MAC FCS check -> frame FIFO CDC -> logic AXIS
    for payload in payloads:
        await src.send(GmiiFrame.from_payload(payload))
        rx = await bounded_recv(axis_rx, f"AXIS RX payload len={len(payload)}")
        assert bytes(rx.tdata) == payload, f"real MAC RX mismatch len={len(payload)}"
        assert rx.tuser == 0, f"unexpected RX tuser error len={len(payload)}"
    assert axis_rx.empty(), "extra/duplicated Ethernet AXIS RX frame"

    # TX: logic AXIS -> frame FIFO CDC -> real MAC FCS insert -> GMII BFM
    for payload in payloads:
        await axis_tx.send(AxiStreamFrame(payload))
        tx = await bounded_recv(sink, f"GMII TX payload len={len(payload)}")
        assert bytes(tx.get_payload()) == payload, f"MAC TX mismatch len={len(payload)}"
        assert tx.check_fcs(), "real MAC failed to insert valid FCS"
        assert tx.error is None, f"GMII errors: {tx.error}"
    assert sink.empty(), "extra/duplicated GMII TX frame"
    # Underflow is a pulse: monitored throughout in extended stress tests,
    # not inferred from this single end-of-test sample.
    dut._log.info("PASS real GMII MAC RX/TX: %d frames each; distinct 8ns/10ns clocks",
                  len(payloads))


@cocotb.test(timeout_time=1, timeout_unit="ms")
async def corrupted_fcs_is_detected_and_not_delivered(dut):
    src, _sink, _axis_tx, axis_rx = await setup(dut)
    seen_bad_fcs = [0]
    seen_fifo_bad = [0]

    async def capture_fcs():
        while True:
            await RisingEdge(dut.gmii_rx_clk)
            if int(dut.rx_error_bad_fcs.value):
                seen_bad_fcs[0] += 1

    async def capture_fifo():
        while True:
            await RisingEdge(dut.logic_clk)
            if int(dut.rx_fifo_bad_frame.value):
                seen_fifo_bad[0] += 1

    bad_task = cocotb.start_soon(capture_fcs())
    fifo_task = cocotb.start_soon(capture_fifo())
    bad = GmiiFrame.from_payload(bytes(range(96)))
    bad.data[-1] ^= 0x80
    await src.send(bad)
    await src.wait()
    # Allow the invalid complete frame to be dropped across RX CDC; no
    # valid AXIS frame must escape, including one with a silently bad FCS.
    for _ in range(40):
        await RisingEdge(dut.logic_clk)
    assert seen_bad_fcs[0] >= 1, "real RX MAC did not detect corrupted FCS"
    assert seen_fifo_bad[0] >= 1, "RX frame FIFO did not report bad-frame drop"
    assert axis_rx.empty(), "bad FCS frame reached logic RX AXIS"
    bad_task.kill()
    fifo_task.kill()
    dut._log.info("PASS real GMII malformed frame rejection; MAC errors=%d FIFO drops=%d",
                  seen_bad_fcs[0], seen_fifo_bad[0])


@cocotb.test(timeout_time=6, timeout_unit="ms")
async def sustained_1gbe_rx_and_tx_without_width_bottleneck(dut):
    src, sink, axis_tx, axis_rx = await setup(dut)
    # Sending many frames with no artificial gaps would overrun an 8-bit
    # 100MHz logic interface; the 64-bit tkeep adapter must drain promptly.
    payloads = [bytes(((n * 31) + i * 7) & 0xff for i in range(1100 + n % 13))
                for n in range(24)]
    errors = {"bad_fcs": 0, "bad_frame": 0, "overflow": 0, "underflow": 0}

    async def watch_rx():
        while True:
            await RisingEdge(dut.gmii_rx_clk)
            errors["bad_fcs"] += int(dut.rx_error_bad_fcs.value)
            errors["bad_frame"] += int(dut.rx_error_bad_frame.value)

    async def watch_logic():
        while True:
            await RisingEdge(dut.logic_clk)
            errors["overflow"] += int(dut.rx_fifo_overflow.value)

    async def watch_tx():
        while True:
            await RisingEdge(dut.gmii_tx_clk)
            errors["underflow"] += int(dut.tx_error_underflow.value)

    monitors = [cocotb.start_soon(watch_rx()), cocotb.start_soon(watch_logic()),
                cocotb.start_soon(watch_tx())]
    for payload in payloads:
        await src.send(GmiiFrame.from_payload(payload))
        await axis_tx.send(AxiStreamFrame(payload))
    for payload in payloads:
        received = await bounded_recv(axis_rx, "64-bit RX frame")
        sent = await bounded_recv(sink, "GMII TX frame")
        assert bytes(received.tdata) == payload, "RX byte/keep corruption"
        assert received.tuser == 0, "unexpected RX error"
        assert bytes(sent.get_payload()) == payload, "TX tail/keep corruption"
        assert sent.check_fcs(), "bad transmitted FCS"
    for t in monitors:
        t.kill()
    assert not any(errors.values()), f"MAC/FIFO errors on good sustained traffic: {errors}"
    assert axis_rx.empty() and sink.empty(), "duplicate or unconsumed Ethernet frames"
    dut._log.info("PASS sustained GMII RX/TX: 24 frames both directions, 64-bit logic + 8-bit GMII, error counters=%r", errors)


@cocotb.test(timeout_time=3, timeout_unit="ms")
async def rx_backpressure_drops_whole_frames_without_partial_delivery(dut):
    """GMII has no ready; RX FIFO must drop complete frames under congestion."""
    src, _sink, _axis_tx, axis_rx = await setup(dut)
    axis_rx.pause = True
    payloads = [bytes(((i * 19) + j * 5) & 0xff for j in range(1200))
                for i in range(5)]
    status = {"overflow": 0, "bad_frame": 0, "bad_fcs": 0}

    async def watch_status():
        while True:
            await RisingEdge(dut.logic_clk)
            status["overflow"] += int(dut.rx_fifo_overflow.value)

    async def watch_fcs():
        while True:
            await RisingEdge(dut.gmii_rx_clk)
            status["bad_fcs"] += int(dut.rx_error_bad_fcs.value)

    monitors = [cocotb.start_soon(watch_status()), cocotb.start_soon(watch_fcs())]
    for payload in payloads:
        await src.send(GmiiFrame.from_payload(payload))
    await with_timeout(src.wait(), 250, "us")
    for _ in range(40):
        await RisingEdge(dut.logic_clk)
    assert axis_rx.empty(), "RX AXIS consumed data despite explicit backpressure"
    axis_rx.pause = False
    # Drain the FIFO before checking packet boundaries and error ownership.
    received = [await bounded_recv(axis_rx, "first retained backpressured frame")]
    for _ in range(200):
        await RisingEdge(dut.logic_clk)
    while not axis_rx.empty():
        received.append(await bounded_recv(axis_rx, "remaining retained frame"))
    assert 0 < len(received) < len(payloads), "expected bounded FIFO loss under RX stall"
    # RX FIFO should preserve FIFO order, with only complete frames accepted.
    for expected, frame in zip(payloads, received):
        assert bytes(frame.tdata) == expected, "partial, corrupted or reordered RX frame"
        assert frame.tuser == 0, "bad frame leaked into accepted RX data"
    assert status["overflow"] > 0, "no FIFO overflow recorded despite forced congestion"
    assert status["bad_fcs"] == 0, "valid test packets must retain good FCS"
    for monitor in monitors:
        monitor.kill()
    dut._log.info("PASS Ethernet full-frame RX drop: retained=%d dropped=%d errors=%r",
                  len(received), len(payloads)-len(received), status)
