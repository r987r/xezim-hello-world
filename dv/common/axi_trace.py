"""Capture handshakes with upstream passive AXI channel monitors.

No signal writes, drivers, protocol model or global ID remapping here.
The host correlates accepted channel events after the simulator exits.
"""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import Edge, RisingEdge, Timer
from cocotb.utils import get_sim_time
from cocotbext.axi import axi_channels
from dv.common.axi_outstanding import AcceptedAxiInFlight
from dv.common.axi_event_sink import PassiveAxiEventSink

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
        # The long-running, explicitly source-selected SCN-2 CPU/BFM
        # profiles benefit from bounded batching of instruction-fetch traffic.
        # ALL OTHER regressions retain the historical immediate-flush behavior:
        # their CPUs/BFMs may finish on an arbitrary outstanding AXI handshake,
        # and a partially buffered final channel event would look incomplete
        # to the independent post-run transaction correlator.
        selected_batch = plan.get('target') in (
            'chip-cpu-scenario', 'chip-dma-scenario')
        self.output = (plan_path.parent/'axi-events.jsonl').open(
            'w', buffering=256*1024 if selected_batch else 1)
        self.sink = PassiveAxiEventSink(
            self.output, batch_events=128 if selected_batch else 1)
        self.count = 0
        self.limit = options.get('max_events', 500000)
        self.monitors = []
        self.in_flight = AcceptedAxiInFlight()
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
        self.emit({'channel':'capture_start', 'annotations_version':1,
                   'monitors':[m['id'] for m in catalog['monitors']]})
        cocotb.start_soon(self.resets(reset))
        cocotb.start_soon(self.sample_clock(clock))

    def emit(self, event):
        event['time_ps'] = int(get_sim_time(units='ps'))
        self.in_flight.observe(event)
        self.sink.write(event)

    async def sample_clock(self, clock):
        """Measure the simulation clock period, not an architectural frequency."""
        await RisingEdge(clock)
        first = int(get_sim_time(units='ps'))
        await RisingEdge(clock)
        period = int(get_sim_time(units='ps')) - first
        if period <= 0:
            raise ValueError('AXI capture clock has a nonpositive measured period')
        self.emit({'channel':'clock_period', 'period_ps':period})

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


def flush_active():
    """Persist every already-observed accepted channel event before test exit.

    This does NOT wait for, complete, synthesize or discard an outstanding
    transaction. The post-run AW/W/B/AR/R correlator remains the authority.
    In particular the selected SCN-2 bounded batch must be flushed while
    the Cocotb interpreter is still live; OS process teardown is not a
    guaranteed Python TextIO destructor path.
    """
    for observer in _active:
        observer.sink.flush()


def trace_phase(label):
    for observer in _active:
        observer.emit({'channel':'phase','label':label})


def expect_axi_response(monitor, operation, address, response, reason):
    """Declare one expected response before submitting its exact request."""
    for observer in _active:
        observer.emit({'channel':'expect_response','monitor':monitor,'operation':operation,
                       'address':hex(address),'response':hex(int(response)),'reason':reason})


async def wait_axi_quiescent(*, timeout_ns=1000, stable_ns=2):
    """Bounded passive drain of all AXI monitors before test completion.

    Never stops clocks, changes CPU execution, suppresses outstanding rows,
    or substitutes for the host's strict AXI transaction correlator. This
    is intended only for the selected benchmark with continuously polling
    boot CPUs. Its source BFMs have already completed independently.
    """
    if not _active:
        raise AssertionError('cannot qualify AXI idle without passive monitor capture')
    if type(timeout_ns) is not int or type(stable_ns) is not int or not (0 < stable_ns < timeout_ns):
        raise ValueError('invalid passive AXI drain timeout')
    idle_since = None
    for _ in range(timeout_ns):
        await Timer(1, units='ns')
        if all(observer.in_flight.is_idle() for observer in _active):
            if idle_since is None:
                idle_since = int(get_sim_time(units='ps'))
            if int(get_sim_time(units='ps')) - idle_since >= stable_ns * 1000:
                return
        else:
            idle_since = None
    details = [observer.in_flight.summary() for observer in _active]
    raise AssertionError('AXI passive capture did not drain: '+repr(details))
