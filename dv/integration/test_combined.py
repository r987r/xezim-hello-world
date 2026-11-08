"""One #34 SoC simulation: Ethernet GMII -> real LiteDRAM -> iDMA -> PCIe.

Real RTL is generated once from the selected SoC. Real CPU0 C configures the
Ethernet queue and submits iDMA; the external VIP only drives RX and observes
TX, and the PCIe RootComplex only uses BAR TLPs. DFI/AXI/TLP/GMII evidence
shares ONE run plan, ONE source SHA and ONE protocol-event stream.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, First, Timer, with_timeout
from cocotb.utils import get_sim_time
from cocotbext.eth import GmiiFrame, GmiiSink, GmiiSource

from dv.common.axi_trace import attach_observers, trace_phase
from dv.common.protocol_trace import open_from_plan
from dv.common.test_flow import attach_from_plan, close_active
from dv.ethernet0.gmii_trace import GmiiEvidence, RX, TX
from dv.ethernet0.test_cpu_mvp import packet, wait_cpu_marker
from dv.full_chip.ddr_init import initialize_controller
from dv.full_chip.test_boot import phase, _ddr_progress
from dv.pcie0.host_adapter import PcieHostParticipant
from dv.pcie0.tlp_trace import LiveTlpCapture
from dv.integration.combined34_scoreboard import (
    check_accepted_axi, verify_controller, write_pass,
)
from rtl.memory.ddr4.dfi_probe import DFIProbe, observe_dfi
from rtl.memory.ddr4.dfi_to_protocol import export_fullchip_probe

READY = 0xe7000001
FINISH = 0xe700600d


class _Phase:
    def __init__(self, dut):
        self.dut = dut

    @property
    def phase(self):
        dut = self.dut
        for name,signal in (("check",dut.check_complete),
                            ("run",dut.run_complete),
                            ("init",dut.init_complete)):
            if int(signal.value):
                return name
        return "pre_init"


def _finish_dfi(probe, task):
    """After the actual AXI/completion gate, finalize ONLY the DFI probe.
    
    The continuous AXI passive observer is never stopped or canceled.
    """
    probe.assert_alive(task)
    task.kill()
    return probe.finish("pass")


async def _watch_cpu_error(dut):
    """Immediately fail on real CPU C error while waiting for external TX.

    A missing TX packet is otherwise a silent cocotbext Sink wait. The
    previous #34 run continued >65 wall minutes after CPU wrote e700f004.
    Do not treat a timeout or the status register as PASS evidence.
    """
    while True:
        await RisingEdge(dut.clk)
        code = int(dut.cpu_dma_evidence.value)
        if code & 0xfffff000 == 0xe700f000:
            raise AssertionError(f"CPU0 C combined hardware failure: {code:#010x}")


def _stop_tx_waiters(tx_task, error_task):
    """Stop only the two temporary receive/error tasks, never AXI observers.

    Lifetime of passive AXI monitoring is managed by attach_observers and
    ends with the test; the DFI probe is finalized separately at teardown.
    """
    for task in (tx_task, error_task):
        if not task.done():
            task.kill()


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def ethernet_ddr_idma_pcie_single_chip(dut):
    for key in ("SOC_COMBINED34_MODE", "SOC_DDR_REAL_MODE",
                "SOC_ETHERNET_CPU_MODE", "SOC_CPU_DMA_MODE",
                "SOC_PCIE_HOST_MODE", "SOC_PCIE_DMA_HOST_MODE"):
        assert os.environ.get(key) == "1", f"{key}: missing real integrated variant"
    plan_file = Path(os.environ["SOC_RUN_PLAN"])
    plan = json.loads(plan_file.read_text())
    assert plan["target"] == "chip-ethernet-ddr-pcie"
    manifest = json.loads((plan_file.parent / "variant/firmware.json").read_text())
    assert manifest.get("external_host"), "missing real on-chip CPU/host phase firmware"
    assert (plan_file.parent / "variant/manifest.json").is_file()
    trace = open_from_plan()
    assert trace is not None
    gmii = GmiiEvidence(trace)
    flow = attach_from_plan(lambda: int(get_sim_time(units="ps")))
    assert flow is not None
    host = PcieHostParticipant(flow, manifest)
    from pcie_if import PcieIfFrame

    dut.rst_n.value = 0
    dut.clk.value = 0
    dut.gmii_rx_clk.value = 0
    dut.gmii_tx_clk.value = 0
    dut.gmii_rx_rst.value = 1
    dut.gmii_tx_rst.value = 1
    dut.gmii_rxd.value = 0
    dut.gmii_rx_dv.value = 0
    dut.gmii_rx_er.value = 0
    dut.ddr_init_mode.value = 1
    dut.ddr_negative_mode.value = 0
    dut.completer_id.value = 0
    dut.max_payload_size.value = 0
    attach_observers(dut)
    probe = DFIProbe(plan_file.parent, scope="fullchip_litedram_dfi_sim")
    dfi_task = cocotb.start_soon(
        observe_dfi(dut, probe, _Phase(dut), 10000,
                    pins_dut=dut.dut.u_ddr_real, fullchip_aliases=True)
    )
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_rx_clk, 8, units="ns").start())
    cocotb.start_soon(Clock(dut.gmii_tx_clk, 8, units="ns").start())
    source = GmiiSource(dut.gmii_rxd, dut.gmii_rx_er, dut.gmii_rx_dv,
                        dut.gmii_rx_clk, dut.gmii_rx_rst)
    sink = GmiiSink(dut.gmii_txd, dut.gmii_tx_er, dut.gmii_tx_en,
                    dut.gmii_tx_clk, dut.gmii_tx_rst)
    for _ in range(15):
        await FallingEdge(dut.clk)
    dut.gmii_rx_rst.value = 0
    dut.gmii_tx_rst.value = 0
    dut.rst_n.value = 1
    trace_phase("COMBINED34 INIT real Config-NoC LiteDRAM/DFII")
    await initialize_controller(dut)
    cocotb.start_soon(_ddr_progress(dut))
    tlp = LiveTlpCapture(dut, frame_type=PcieIfFrame, trace=trace)
    await host.setup(dut)
    await host.before_phase("init")
    with flow.step("init", "cpu0", "init_complete", origin="checker"):
        await phase(dut, dut.init_complete, "init")

    trace_phase("COMBINED34 RUN CPU0 C queues GMII RX into >4GiB DDR")
    await wait_cpu_marker(dut, READY)
    frame = packet()
    assert len(frame) == 85, "host and CPU ABI must match GMII golden frame"
    with flow.step("run", "gmii0", "inject_frame", origin="stimulus",
                   details={"bytes":len(frame)}):
        await source.send(GmiiFrame.from_payload(frame))
        await source.wait()
        gmii.packet(RX, frame)
    with flow.step("run", "gmii0", "observe_transmit", origin="checker",
                   details={"bytes":len(frame)}):
        tx_task = cocotb.start_soon(sink.recv())
        error_task = cocotb.start_soon(_watch_cpu_error(dut))
        try:
            await with_timeout(First(tx_task, error_task), 3, "ms")
            if error_task.done():
                await error_task  # raises the actual CPU failure code
            assert tx_task.done(), "GMII TX did not finish"
            result = tx_task.result()
        finally:
            _stop_tx_waiters(tx_task, error_task)
        assert bytes(result.get_payload()) == frame, "DDR/iDMA->GMII TX byte mismatch"
        assert result.check_fcs() and result.error is None, "TX GMII FCS/error"
        gmii.packet(TX, result.get_payload(), fcs_valid=True, error=result.error)
    await wait_cpu_marker(dut, FINISH)
    await host.before_phase("run")  # modeled RC BAR-pulls EXACT RX payload
    with flow.step("run", "cpu0", "run_complete", origin="checker"):
        await phase(dut, dut.run_complete, "run")
    await host.before_phase("check")
    with flow.step("check", "cpu0", "check_complete", origin="checker"):
        await phase(dut, dut.check_complete, "check")
    await Timer(1, units="us")  # drain final accepted AXI and CQ responses

    assert int(dut.pass_flag.value) == 1
    assert int(dut.cpu_dma_success.value) == 1
    assert int(dut.cpu_dma_evidence.value) == FINISH
    assert int(dut.app_fetch.value) == 3  # both actual heterogeneous CPUs
    assert int(dut.eth_irq.value) == 0
    assert int(dut.eth_bad_fcs.value) == 0
    assert int(dut.eth_tx_failed.value) == 0
    assert int(dut.eth_drop.value) == 0
    gmii.finish()
    host.finish()
    tlp_counts = tlp.finish(close_trace=False)
    assert tlp_counts.get("pcie0.rx_req/mem_read", 0) > 0
    assert tlp_counts.get("pcie0.tx_cpl/completion", 0) > 0
    axi_counts = check_accepted_axi(plan_file)

    summary = _finish_dfi(probe, dfi_task)
    dfi_counts = export_fullchip_probe(plan_file.parent, trace)
    controller_counts = verify_controller(dut.dut.u_ddr_real, dfi_counts)
    assert summary["sampled_cycles"] >= 1
    trace.close("pass")
    close_active()
    write_pass(plan_file.parent/"combined34_evidence.json",
               plan, axi_counts, controller_counts, tlp_counts, frame)
    dut._log.info("PASS COMBINED34: one full-chip GMII RX->real DDR/DFI->PULP iDMA"
                  "->PCIe BAR and Ethernet TX; CPU SRAM bytes/CQ/IRQ; %s",
                  axi_counts)
