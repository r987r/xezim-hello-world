"""Host phases observe real CPU0-coordinated firmware, never drive CPU results."""
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, with_timeout
from cocotb.result import SimTimeoutError
from cocotbext.axi import AxiBus, AxiMaster
from dv.common.axi_trace import attach_observers

ROOT = Path(__file__).resolve().parents[2]


async def phase(dut, signal, name):
    await with_timeout(RisingEdge(signal), 1000, 'us')
    dut._log.info('observed firmware phase %s complete', name)


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
    # Only a verification manager occupies the not-yet-integrated DMA port.
    # It never drives SRAM/boot mailboxes. Distinct values detect model aliasing.
    expected = []
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
    for target in memory:
        address = target['base'] + target['modeled_bytes']
        result = await memory_transaction(dut, probe.write(address, b'NOALIAS!'))
        assert result.resp == 2, f'fullchip {target["name"]} out-of-range write must return SLVERR'
        result = await memory_transaction(dut, probe.read(address, 8))
        assert result.resp == 2, f'fullchip {target["name"]} out-of-range read must return SLVERR'
    await Timer(1, 'ns')  # drain passive same-edge channel callbacks
    dut._log.info('PASS fullchip: CPU phases and independent bounded AXI memory models')
