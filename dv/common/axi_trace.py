"""Capture handshakes with upstream passive AXI channel monitors.

No signal writes, drivers, protocol model or global ID remapping here.
The host correlates accepted channel events after the simulator exits.
"""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import Edge
from cocotb.utils import get_sim_time
from cocotbext.axi import axi_channels

_active = []


def resolve(scope, path):
    for component in path.split('.'):
        scope = getattr(scope, component)
    return scope


class AxiTrace:
    def __init__(self, dut, plan_path):
        plan = json.loads(plan_path.read_text())
        options = plan['report']['axi']
        catalog = json.loads((Path(__file__).resolve().parents[2]/options['catalog']).read_text())
        scope = resolve(dut, options['scope'])
        clock, reset = resolve(dut, options['clock']), resolve(dut, options['reset'])
        self.output = (plan_path.parent/'axi-events.jsonl').open('w', buffering=1)
        self.count = 0
        self.limit = options.get('max_events', 500000)
        self.monitors = []
        self.emit({'channel':'reset', 'active':int(reset.value) == 0})
        # Construct all buses eagerly: a missing binding fails the test,
        # rather than producing a report with silently missing connections.
        for entry in catalog['monitors']:
            for channel in ('AW','W','B','AR','R'):
                bus_type = getattr(axi_channels, 'Axi'+channel+'Bus')
                monitor_type = getattr(axi_channels, 'Axi'+channel+'Monitor')
                bus = bus_type.from_prefix(scope, entry['prefix'])
                for field, width in (('id',entry['id_width']),('addr',entry['addr_width']),
                                     ('data',entry['data_width']),('strb',entry['data_width']//8)):
                    signal = getattr(bus,channel.lower()+field,None)
                    if signal is not None and len(signal) != width:
                        raise ValueError(f'AXI trace width mismatch: {entry["id"]} {channel}{field}')
                monitor = monitor_type(bus, clock, reset, reset_active_level=False)
                self.monitors.append(monitor)
                cocotb.start_soon(self.consume(entry['id'], channel.lower(), monitor))
        self.emit({'channel':'capture_start', 'monitors':[m['id'] for m in catalog['monitors']]})
        cocotb.start_soon(self.resets(reset))

    def emit(self, event):
        event['time_ps'] = int(get_sim_time(units='ps'))
        self.output.write(json.dumps(event, separators=(',',':'))+'\n')

    async def resets(self, reset):
        while True:
            await Edge(reset)
            self.emit({'channel':'reset', 'active':int(reset.value) == 0})

    async def consume(self, boundary, channel, monitor):
        while True:
            transaction = await monitor.recv()
            self.count += 1
            if self.count > self.limit:
                self.emit({'channel':'capture_overflow','limit':self.limit})
                raise AssertionError('AXI capture limit exceeded; report is incomplete')
            # Hex strings preserve arbitrary-width addresses/data/IDs in JSON
            # and JavaScript, including values above Number.MAX_SAFE_INTEGER.
            self.emit({'monitor':boundary,'channel':channel,
                       'fields':{name[len(channel):]:hex(int(value))
                                 for name,value in vars(transaction).items()}})


def attach_observers(dut):
    path = os.environ.get('SOC_RUN_PLAN')
    if not path:
        return
    plan_path = Path(path)
    plan = json.loads(plan_path.read_text())
    if 'axi' in plan.get('report', {}):
        _active.append(AxiTrace(dut, plan_path))
