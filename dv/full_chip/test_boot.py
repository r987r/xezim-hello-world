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

ROOT = Path(__file__).resolve().parents[2]


async def phase(dut, signal, name):
    timeout = 5 if os.environ.get('SOC_CPU_DMA_MODE') == '1' else 1
    await with_timeout(RisingEdge(signal), timeout, 'ms')
    dut._log.info('observed firmware phase %s complete', name)
    trace_phase('CPU '+name+' complete')


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
    manifest = json.loads((ROOT/'gen/chip/firmware.json').read_text())
    memory = json.loads((ROOT/'gen/chip/manifest.json').read_text())['memory_models']
    probe = AxiMaster(AxiBus.from_prefix(dut, 'probe'), dut.clk, dut.rst_n, reset_active_level=False)
    dut.rst_n.value = 0
    attach_observers(dut)
    cocotb.start_soon(Clock(dut.clk, 10, 'ns').start())
    for _ in range(10):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await phase(dut, dut.init_complete, 'init')
    await phase(dut, dut.run_complete, 'run')
    await phase(dut, dut.check_complete, 'check')
    await Timer(1, 'ns')
    assert int(dut.pass_flag.value) == 1
    mask = (1 << len(manifest['cores'])) - 1
    assert int(dut.init_mask.value) == mask
    assert int(dut.hello_mask.value) == mask
    assert int(dut.check_mask.value) == mask
    assert int(dut.app_fetch.value) == mask
    if os.environ.get('SOC_CPU_DMA_MODE') == '1':
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
        regions = configured_regions(yaml.safe_load(
            (ROOT/"config/soc.yaml").read_text()))
        from tools.axi_report import read_events
        events, issues = read_events(events_file)
        assert not issues, f"bad AXI trace: {issues[:3]}"
        actual = {target: {"ar": 0, "aw": 0}
                  for target in ("memory0.ddr0","memory0.hbm0")}
        for event in events:
            if event.get("monitor") != "compute0_local_data.dma" or event.get("channel") not in ("ar","aw"):
                continue
            address = int(event["fields"]["addr"], 0)
            for target in actual:
                region = regions[target]
                if region.base <= address < region.base + region.capacity:
                    actual[target][event["channel"]] += 1
        for target, counts in actual.items():
            assert counts["aw"] > 0 and counts["ar"] > 0, (
                f"real CPU DMA missing full-NoC DDR/HBM accepted writes+reads: {target}, {counts}")
        trace_phase("CPU compiled C DMA complete: monitored DDR+HBM roundtrips")
        dut._log.info("PASS fullchip: CPU-executed compiled C DMA, shared INIT/RUN/CHECK, "
                      "DDR+HBM roundtrip, SRAM allocator and passive AXI monitors")
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
    dut._log.info('PASS fullchip: CPU phases and independent bounded AXI memory models')
