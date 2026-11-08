"""Host phases observe real CPU0-coordinated firmware, never drive CPU results."""
import json
import os
from pathlib import Path
import yaml
from tools.memory_plan import configured_regions

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, with_timeout
from cocotb.result import SimTimeoutError
from cocotbext.axi import AxiBus, AxiMaster
from dv.common.axi_trace import attach_observers, expect_axi_response, trace_phase
from dv.common.test_flow import attach_from_plan, close_active
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[2]


async def phase(dut, signal, name):
    # Full LiteDRAM DFI simulation is far slower than AXI RAM, and our
    # real CPU enters RUN only after >1 ms of genuine JEDEC/DFII init.
    # Keep the original 5 ms CPU-DMA deadline for the fast regression.
    timeout = (12 if os.environ.get('SOC_DDR_REAL_MODE') == '1'
               else 5 if os.environ.get('SOC_CPU_DMA_MODE') == '1' else 1)
    if int(signal.value) != 1:
        await with_timeout(RisingEdge(signal), timeout, 'ms')
    dut._log.info('observed firmware phase %s complete', name)
    trace_phase('CPU '+name+' complete')


async def _ddr_progress(dut):
    """Periodic passive checkpoints during the opt-in real DDR CPU run.

    No bus agent or force; sampling existing retired-operation counters
    prevents another 30-minute wall timeout with no phase diagnostics.
    """
    controller = dut.dut.u_ddr_real
    while True:
        await Timer(500, 'us')
        fields = (
            ("init", dut.init_complete), ("run", dut.run_complete),
            ("check", dut.check_complete), ("success", dut.cpu_dma_success),
            ("firmware", dut.cpu_dma_evidence),
            ("axi_aw", controller.controller_axi_aw_count),
            ("axi_b", controller.controller_axi_b_count),
            ("axi_ar", controller.controller_axi_ar_count),
            ("axi_rlast", controller.controller_axi_rlast_count),
            ("dfi_write", controller.dfi_write_count),
            ("dfi_read", controller.dfi_read_count),
            ("bank_write", controller.bank_storage_write_count),
        )
        summary = " ".join(f"{key}={int(signal.value):#x}" for key, signal in fields)
        dut._log.info("DDR_PROGRESS at %dus: %s", int(get_sim_time(units="us")), summary)


async def _cpu_dma_progress(dut):
    """Passive wall/simulation clock checkpoints for the expensive CPU/DMA RTL.

    Never drives a signal or turns incomplete INIT/RUN/CHECK into success.
    The original 1800s cap caught two runs at sim=177.17us; the normal
    passing reference took up to 27m23s. Record whether time advances at all.
    """
    import time
    start = time.monotonic()
    while True:
        await Timer(20, 'us')
        fields = (
            ("init", dut.init_complete), ("run", dut.run_complete),
            ("check", dut.check_complete), ("passed", dut.pass_flag),
            ("dma_success", dut.cpu_dma_success),
            ("address_seen", dut.cpu_dma_address_seen),
        )
        summary = " ".join(f"{key}={int(signal.value):#x}"
                           for key, signal in fields)
        dut._log.info("CPU_DMA_PROGRESS sim_us=%d wall_s=%d %s",
                      int(get_sim_time(units="us")),
                      int(time.monotonic() - start), summary)


async def memory_transaction(dut, operation):
    try:
        return await with_timeout(operation, 20, 'us')
    except SimTimeoutError:
        for scope in (dut, dut.dut.u_noc, dut.dut.u_memory_crossbar):
            for signal in scope:
                if signal._name.endswith(('valid', 'ready', 'addr', 'resp')):
                    try:
                        dut._log.error('AXI timeout %s = 0x%x', signal._path, int(signal.value))
                    except (ValueError, AttributeError):
                        pass
        raise


@cocotb.test()
async def coordinated_cold_boot(dut):
    await execute_cold_boot(dut)


async def execute_cold_boot(dut, *, external=None):
    if external not in (None,"pcie0"):
        raise ValueError("unsupported shared test participant")
    plan=os.environ.get("SOC_RUN_PLAN")
    if external:
        if not plan:
            raise AssertionError("no shared regression plan")
        firmware=Path(plan).parent/"variant"/"firmware.json"
    else:
        firmware=ROOT/"gen/chip/firmware.json"
    manifest=json.loads(firmware.read_text())
    # Only this opt-in real PeakRDL variant gains three checked CPU phase
    # milestones. Do not falsely instrument unrelated normal boot variants.
    peakrdl_reset = bool(plan and json.loads(Path(plan).read_text()).get("firmware_mode") == "peakrdl_reset")
    flow = (attach_from_plan(lambda:int(get_sim_time(units="ps")))
            if external or peakrdl_reset else None)
    host = None
    tlp_capture = None
    if external=="pcie0":
        from dv.pcie0.host_adapter import PcieHostParticipant
        host=PcieHostParticipant(flow,manifest)
    memory = json.loads((ROOT/'gen/chip/manifest.json').read_text())['memory_models']
    cpu_dma_mode = os.environ.get('SOC_CPU_DMA_MODE') == '1'
    real_ddr_mode = os.environ.get('SOC_DDR_REAL_MODE') == '1'
    # The probe outputs mirror the *real iDMA response* when DmaEnable=1
    # and ProbeEnable=0. Attaching AxiMaster in CPU mode would let its
    # unsolicited R-channel worker consume the DMA's valid descriptor R
    # (ID=7), raising cocotbext-axi "unexpected burst ID". In this mode
    # the probe is an observation port only: NEVER attach an active agent.
    probe = None
    if not cpu_dma_mode and host is None:
        probe = AxiMaster(AxiBus.from_prefix(dut, 'probe'), dut.clk,
                          dut.rst_n, reset_active_level=False)
    dut.rst_n.value = 0
    if real_ddr_mode:
        dut.ddr_init_mode.value = 1
    if host is not None:
        dut.completer_id.value=0
        dut.max_payload_size.value=0
    attach_observers(dut)
    if cpu_dma_mode and os.environ.get('SOC_CPU_DMA_PROGRESS') == '1':
        cocotb.start_soon(_cpu_dma_progress(dut))
    cocotb.start_soon(Clock(dut.clk, 10, 'ns').start())
    for _ in range(10):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    if real_ddr_mode:
        from dv.full_chip.ddr_init import initialize_controller
        await initialize_controller(dut)
        cocotb.start_soon(_ddr_progress(dut))
    if host is not None:
        from dv.pcie0.tlp_trace import LiveTlpCapture
        # The pinned helper already provides PcieIfFrame / Tlp decoding.
        from pcie_if import PcieIfFrame
        tlp_capture = LiveTlpCapture(dut, frame_type=PcieIfFrame)
        await host.setup(dut)
    for name, signal in (("init",dut.init_complete),("run",dut.run_complete),
                         ("check",dut.check_complete)):
        if host is not None:
            await host.before_phase(name)
            with flow.step(name,"cpu0",name+"_complete",origin="checker"):
                await phase(dut,signal,name)
        elif peakrdl_reset:
            # Actual RTL completion signal observed through the shared checker;
            # not a software action or evidence manufactured by a test plan.
            with flow.step(name,"cpu0",name+"_complete",origin="checker"):
                await phase(dut,signal,name)
        else:
            await phase(dut,signal,name)
    # Real CPUs can still be retiring final mailbox stores when CHECK rises.
    # Give actual AXI B handshakes time to drain before the passive reporter
    # closes; the strict AXI report will still reject any outstanding burst.
    await Timer(1, 'us' if host is not None or cpu_dma_mode else 'ns')
    assert int(dut.pass_flag.value) == 1
    mask = (1 << len(manifest['cores'])) - 1
    assert int(dut.init_mask.value) == mask
    assert int(dut.hello_mask.value) == mask
    assert int(dut.check_mask.value) == mask
    assert int(dut.app_fetch.value) == mask
    if host is not None and not cpu_dma_mode:
        assert probe is None, "PCIe mode must not instantiate active CPU0 AXI BFM"
        host.finish()
        tlp_counts = tlp_capture.finish()
        dut._log.info("PCIE0_ACCEPTED_TLP_REPORT_COUNTS=%s", tlp_counts)
        close_active()
        return
    if cpu_dma_mode:
        assert probe is None  # a CPU-DMA run must never own the BFM port
        # Same testbench and INIT/RUN/CHECK checker; no AXI BFM drives the
        # CPU or memory. Real PicoRV32 has already called compiled C, which
        # sends both engines' traffic through the configured NoCs.
        assert int(dut.cpu_dma_success.value) == 1, (
            "real CPU did not finish C DMA/checks")
        assert int(dut.cpu_dma_evidence.value) == 0x600dc0de
        plan = os.environ.get("SOC_RUN_PLAN")
        assert plan, "missing shared AXI capture configuration"
        events_file = Path(plan).parent / "axi-events.jsonl"
        assert events_file.is_file(), "missing passive NoC AXI events"
        scenario_path = os.environ.get("SOC_SCENARIO_PLAN")
        if scenario_path:
            # SCN-2: actual CPU0 executes the C variant compiled from the
            # same immutable scenario as the authorized reset-isolated BFM.
            # No active AxiMaster may attach to CPU/DMA mirrored buses.
            from dv.common.scenario_dma import load_contract_from_plan
            from tools.axi_report import read_events
            contract = load_contract_from_plan(Path(scenario_path))
            assert int(dut.cpu_dma_address_seen.value) == 0x3f, (
                "SCN-2 missing CPU0 actual allocation mailbox stores")
            packed = int(dut.cpu_dma_addresses.value)
            words = [(packed >> (32 * k)) & 0xffffffff for k in range(6)]
            observed = (words[0], words[1], words[2] | (words[3] << 32))
            expected = (contract["source_phys"], contract["return_phys"],
                        contract["ddr_phys"])
            assert observed == expected, (
                f"SCN-2 CPU allocations {observed} differ from resolved plan {expected}")
            events, bad = read_events(events_file)
            assert not bad, f"SCN-2 invalid real passive AXI events: {bad[:3]}"
            counts = {"src_ar": 0, "ddr_aw": 0, "ddr_ar": 0, "return_aw": 0}
            for event in events:
                if event.get("monitor") != "compute0_local_data.dma" or event.get("channel") not in ("ar", "aw"):
                    continue
                phys = int(event["fields"]["addr"], 0)
                if (event["channel"] == "ar" and
                        contract["source_phys"] <= phys < contract["source_phys"] + contract["length"]):
                    counts["src_ar"] += 1
                if (event["channel"] == "aw" and
                        contract["ddr_phys"] <= phys < contract["ddr_phys"] + contract["length"]):
                    counts["ddr_aw"] += 1
                if (event["channel"] == "ar" and
                        contract["ddr_phys"] <= phys < contract["ddr_phys"] + contract["length"]):
                    counts["ddr_ar"] += 1
                if (event["channel"] == "aw" and
                        contract["return_phys"] <= phys < contract["return_phys"] + contract["length"]):
                    counts["return_aw"] += 1
            assert all(counts.values()), (
                f"SCN-2 accepted DMA traffic incomplete (not a real RTL pass): {counts}")
            # Firmware checked exact source pattern and descriptor writebacks
            # before asserting the actual cpu_dma_success pass signal.
            evidence = {"scenario_id": contract["scenario_id"],
                        "plan_sha256": contract["plan_sha256"],
                        "profile": "real_cpu0_compiled_c",
                        "execution_state": "rtl_observed",
                        "observed_cpu_allocations": list(observed),
                        "observed_dma_axi_counts": counts,
                        "cpu_result_checked": True,
                        "intent_is_not_evidence": True}
            (Path(plan).parent / "scenario-execution.json").write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n")
            trace_phase("SCN-2 CPU C real NoC DDR roundtrip: " +
                        contract["scenario_id"])
            dut._log.info("PASS scenario-cpu: CPU0 C + iDMA real DDR modeled AXI, %s", counts)
            return
        regions = configured_regions(yaml.safe_load(
            (ROOT/"config/soc.yaml").read_text()))
        from tools.memory_plan import validate_cpu_allocation
        # C writes its *actual* allocated physical addresses into the
        # reserved mailbox telemetry. Decode observed RTL SRAM stores and
        # compare them with an independently allocated Python virtual plan.
        assert int(dut.cpu_dma_address_seen.value) == 0x3f
        actual_addresses = int(dut.cpu_dma_addresses.value)
        recorded = [(actual_addresses >> (32*i)) & 0xffffffff
                    for i in range(6)]
        predicted = [
            regions["compute0.sram.payload"].allocate(
                64, 64, owner="cpu0", phase="run"),
            regions["compute1.sram.payload"].allocate(
                64, 64, owner="cpu0", phase="run"),
            regions["memory0.ddr0"].allocate(
                64, 64, owner="dma0", phase="run"),
            regions["memory0.hbm0"].allocate(
                64, 64, owner="dma0", phase="run")]
        for observed, expected in zip(
                (recorded[0], recorded[1],
                 recorded[2] | (recorded[3] << 32),
                 recorded[4] | (recorded[5] << 32)), predicted):
            validate_cpu_allocation(observed, expected)
        from tools.axi_report import read_events
        events, issues = read_events(events_file)
        assert not issues, f"bad AXI trace: {issues[:3]}"
        # The minimal combined host smoke uses DDR + PCIe SRAM. The
        # original separate CPU C/DMA regression still requires DDR + HBM.
        targets = (("memory0.ddr0", "pcie0.sram") if host is not None else
                   ("memory0.ddr0", "memory0.hbm0"))
        actual = {target: {"ar": 0, "aw": 0} for target in targets}
        for event in events:
            if event.get("monitor") != "compute0_local_data.dma" or event.get("channel") not in ("ar","aw"):
                continue
            address = int(event["fields"]["addr"], 0)
            for target in actual:
                if target == "pcie0.sram":
                    base, capacity = host.sram_base, 16384
                else:
                    region = regions[target]
                    base, capacity = region.base, region.capacity
                if base <= address < base + capacity:
                    actual[target][event["channel"]] += 1
        for target, counts in actual.items():
            assert counts["aw"] > 0 and counts["ar"] > 0, (
                f"real CPU DMA missing full-NoC DDR/HBM accepted writes+reads: {target}, {counts}")
        if host is not None and os.environ.get("SOC_PCIE_OUTBOUND_MODE") == "1":
            from dv.common.selected_aperture import selected_aperture
            csr_base, csr_bytes = selected_aperture(
                "pcie0.ctrl", "config", plan_path=plan)
            assert csr_bytes >= 0x40
            seen = {"wr_doorbell":0, "rd_doorbell":0,
                    "wr_status":0, "rd_status":0,
                    "slave_write":0, "slave_read":0}
            for event in events:
                channel=event.get("channel")
                if channel not in ("aw","ar"):
                    continue
                addr=int(event["fields"]["addr"],0)
                monitor=event.get("monitor")
                if monitor=="compute0_local_config.cpu":
                    for key,expected_channel,offset in (
                        ("wr_doorbell","aw",0x14),
                        ("rd_doorbell","aw",0x34),
                        ("wr_status","ar",0x18),
                        ("rd_status","ar",0x38)):
                        if channel==expected_channel and addr==csr_base+offset:
                            seen[key]+=1
                if monitor=="pcie0_local_config.controller_regs" and (
                    csr_base <= addr < csr_base+0x40):
                    seen["slave_write" if channel=="aw" else "slave_read"]+=1
            assert all(value>0 for value in seen.values()), (
                "missing real CPU Config-NoC CSR or target handshakes: ",seen)
            dut._log.info("PCIE0_CPU_REQUESTER_CONFIG_NOC_AXI=%s",seen)
        trace_phase("CPU compiled C DMA complete: monitored " +
                    ("DDR + PCIe SRAM" if host is not None else "DDR + HBM"))
        dut._log.info("PASS fullchip: CPU-executed compiled C DMA, shared INIT/RUN/CHECK, "
                      "%s, SRAM allocator and passive AXI monitors",
                      "DDR+PCIe SRAM roundtrip" if host is not None else "DDR+HBM roundtrip")
        if host is None:
            return
        # Both external host and C-DMA now run in ONE real RTL configuration;
        # no second coordinator, and the host PASS is issued only after the
        # independent CPU DMA checks above have succeeded.
        host.finish()
        tlp_counts = tlp_capture.finish()
        dut._log.info("PCIE0_ACCEPTED_TLP_REPORT_COUNTS=%s", tlp_counts)
        close_active()
        return
    # Only a verification manager occupies the not-yet-integrated DMA port.
    # It never drives SRAM/boot mailboxes. Distinct values detect model aliasing.
    expected = []
    trace_phase('Verification BFM: memory burst/partial-write checks')
    for index, target in enumerate(memory):
        address = target['base'] + 0x40
        payload = bytearray((index*83 + i*7) % 256 for i in range(16))
        result = await memory_transaction(dut, probe.write(address, payload))
        assert result.resp == 0, f'fullchip {target["name"]} write response {result.resp}'
        result = await memory_transaction(dut, probe.write(address+5, b'AXI'))
        assert result.resp == 0, f'fullchip {target["name"]} partial write response {result.resp}'
        payload[5:8] = b'AXI'
        expected.append((target['name'], address, payload))
    for name, address, payload in expected:
        result = await memory_transaction(dut, probe.read(address, len(payload)))
        assert result.resp == 0, f'fullchip {name} read response {result.resp}'
        assert result.data == payload, f'fullchip {name} model readback/independence mismatch'
        dut._log.info('PASS fullchip AXI memory model %s at 0x%x', name, address)
    trace_phase('Verification BFM: capacity checks — expected SLVERR')
    monitor=manifest['coordinator']+'_local_data.dma'
    for target in memory:
        address = target['base'] + target['modeled_bytes']
        expect_axi_response(monitor,'write',address,2,'Deliberate write beyond the 64-KiB '+target['name']+' model')
        result = await memory_transaction(dut, probe.write(address, b'NOALIAS!'))
        assert result.resp == 2, f'fullchip {target["name"]} out-of-range write must return SLVERR'
        expect_axi_response(monitor,'read',address,2,'Deliberate read beyond the 64-KiB '+target['name']+' model')
        result = await memory_transaction(dut, probe.read(address, 8))
        assert result.resp == 2, f'fullchip {target["name"]} out-of-range read must return SLVERR'
    await Timer(1, 'ns')  # drain passive same-edge channel callbacks
    if peakrdl_reset:
        close_active()
    dut._log.info('PASS fullchip: CPU phases and independent bounded AXI memory models')
