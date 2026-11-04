"""One real eight-FlooNoC DUT with upstream AXI agents and sparse targets."""
import itertools
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
from cocotbext.axi import (
    AddressSpace, AxiBus, AxiMaster, AxiResp, AxiSlave, SparseMemoryRegion,
)
from dv.common.axi_trace import attach_observers, expect_axi_response, trace_phase

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "gen/supernoc/manifest.json").read_text())


def expected_sink(desc, address, length):
    matches = [s for s in CONTRACT["slaves"] if s["plane"] == desc["plane"]
               and any(r["base"] <= address and address + length <= r["base"] + r["size"]
                       for r in s["regions"])]
    assert len(matches) == 1, f"ambiguous/missing target for {desc['name']} @ {address:x}"
    return matches[0]["name"]


async def bounded(operation, context):
    try:
        return await with_timeout(operation, 20, "us")
    except cocotb.result.SimTimeoutError as exc:
        raise AssertionError(f"AXI timeout: {context}") from exc


async def setup(dut):
    dut.rst_ni.value = 0
    dut.clk_i.value = 0
    attach_observers(dut)
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    sinks, memory, masters = {}, {}, {}
    for entry in CONTRACT["slaves"]:
        name = entry["name"]
        # The upstream mapped sparse target avoids AxiRam's 2**64 len()
        # overflow and rejects accesses outside this endpoint's windows.
        memory[name] = AddressSpace(size=1 << entry["addr_width"])
        for region in entry["regions"]:
            memory[name].register_region(SparseMemoryRegion(region["size"]), region["base"])
        sinks[name] = AxiSlave(AxiBus.from_prefix(dut, name), dut.clk_i, dut.rst_ni,
                              reset_active_level=False, target=memory[name])
    for entry in CONTRACT["masters"]:
        name = entry["name"]
        masters[name] = AxiMaster(AxiBus.from_prefix(dut, name), dut.clk_i, dut.rst_ni,
                                  reset_active_level=False)
    for _ in range(12):
        await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk_i)
    return masters, sinks, memory


async def transfer(agent, desc, memory, address, pattern, txn_id=0, readonly=False):
    context = f"{desc['name']} @ 0x{address:x} id={txn_id} bytes={len(pattern)}"
    target = expected_sink(desc, address, len(pattern))
    if readonly:
        # Seed only this NoC BFM's boot window. The separate CPU cold-boot
        # regression must still start with uninitialized SRAM.
        await memory[target].write(address, pattern)
    else:
        wr = await bounded(agent.write(address, pattern, awid=txn_id), context + " write")
        assert wr.resp == AxiResp.OKAY, f"bad B: {context}: {wr}"
        actual = await memory[target].read(address, len(pattern))
        assert actual == pattern, f"wrong destination/storage: {context} expected {target}"
    rd = await bounded(agent.read(address, len(pattern), arid=txn_id), context + " read")
    assert rd.resp == AxiResp.OKAY, f"bad R: {context}: {rd}"
    assert rd.data == pattern, f"AXI data mismatch: {context} expected {pattern.hex()}, got {rd.data.hex()}"
    return target


@cocotb.test(timeout_time=500, timeout_unit="us")
async def routed_data_and_config_all_local_global_nocs(dut):
    masters, sinks, memory = await setup(dut)
    trace_phase('Mapped-route read/write checks')
    visits = set()
    for index, desc in enumerate(CONTRACT["masters"]):
        word_bytes = desc["data_width"] // 8
        for window_index, region in enumerate(desc["regions"]):
            address = region["base"] + 0x100 + index * 16
            pattern = (0xA5A50000 ^ (index << 12) ^ (window_index << 4)).to_bytes(word_bytes, "little")
            target = await transfer(masters[desc["name"]], desc, memory, address, pattern,
                                    readonly=region["access"] == "read")
            visits.add((desc["name"], region["base"]))
            dut._log.info("PASS route %s -> %s @ 0x%x", desc["name"], target, address)
    expected = {(d["name"], r["base"]) for d in CONTRACT["masters"] for r in d["regions"]}
    assert visits == expected, f"missing routes: {expected - visits}"
    reached = {expected_sink(d, r["base"], 1) for d in CONTRACT["masters"] for r in d["regions"]}
    assert reached == set(sinks), f"unvisited leaf endpoints: {set(sinks) - reached}"

    trace_phase('Burst, byte-strobe and channel-stall stress')
    # All five channels stall through upstream pause generators.
    for sink in sinks.values():
        for channel in (sink.write_if.aw_channel, sink.write_if.w_channel,
                        sink.write_if.b_channel, sink.read_if.ar_channel, sink.read_if.r_channel):
            channel.set_pause_generator(itertools.cycle([1, 1, 0, 0, 0]))
    for master in masters.values():
        for channel in (master.write_if.aw_channel, master.write_if.w_channel,
                        master.write_if.b_channel, master.read_if.ar_channel, master.read_if.r_channel):
            channel.set_pause_generator(itertools.cycle([0, 1, 0, 0]))

    async def stress(index, desc, lane=0):
        agent = masters[desc["name"]]
        word_bytes = desc["data_width"] // 8
        writable = [r for r in desc["regions"] if r["access"] == "read_write"]
        cases = [(0, word_bytes)] if desc["plane"] == "config" else [
            (0, word_bytes), (1, word_bytes - 2), (0x20, 4 * word_bytes),
            (0x60, 16 * word_bytes),
        ]
        for ri, region in enumerate(writable):
            # Disjoint manager slots, including when destinations are shared.
            address = region["base"] + 0x400 + index * 0x100 + lane * 0x1000
            for ci, (offset, length) in enumerate(cases):
                # Distinct lane payloads expose swapped same-ID responses;
                # matching data in the two streams would hide that failure.
                pattern = bytes((index * 31 + lane * 71 + ri * 13 + ci + b) & 255
                                for b in range(length))
                # Partial writes must preserve both surrounding sentinels.
                start = address + offset - (address + offset) % word_bytes
                span = ((address + offset + length - start + word_bytes - 1) // word_bytes) * word_bytes
                await transfer(agent, desc, memory, start, b"\xCC" * span)
                await transfer(agent, desc, memory, address + offset, pattern, txn_id=ci % 2)
                actual = await bounded(agent.read(start, span), f"{desc['name']} byte guards")
                expected_data = bytearray(b"\xCC" * span)
                expected_data[address + offset - start:address + offset - start + length] = pattern
                assert actual.resp == AxiResp.OKAY and actual.data == expected_data, "byte-strobe guards changed"
        return len(writable) * len(cases)

    # Two data streams share each manager and reuse IDs across destinations,
    # exercising multiple outstanding transactions and same-ID ordering.
    tasks = [cocotb.start_soon(stress(i, d, lane))
             for i, d in enumerate(CONTRACT["masters"])
             for lane in range(2 if d["plane"] == "data" else 1)]
    operations = sum([await task for task in tasks])
    dut._log.info("PASS concurrent traffic: %d managers, %d burst/partial/single-beat cases with stalls",
                  len(masters), operations)

    # Upstream AxiSlave + an empty upstream AddressSpace produces SLVERR.
    # Mapped target faults are distinct from unmapped NoC addresses, for
    # which pinned FlooNoC asserts DecodeError rather than returning DECERR.
    trace_phase('Injected mapped-target faults — expected SLVERR')
    errors = 0
    for desc in CONTRACT["masters"]:
        for region in desc["regions"]:
            if region["access"] != "read_write":
                continue
            address = region["base"] + 0x80
            name = expected_sink(desc, address, 1)
            sink = sinks[name]
            sink.write_if.target = sink.read_if.target = AddressSpace(size=1 << desc["addr_width"])
            try:
                agent = masters[desc["name"]]
                monitor=desc['network']+'.'+desc['endpoint']
                expect_axi_response(monitor,'write',address,2,'Deliberate mapped-target write fault')
                wr = await bounded(agent.write(address, b"\x01"), "SLVERR write")
                expect_axi_response(monitor,'read',address,2,'Deliberate mapped-target read fault')
                rd = await bounded(agent.read(address, 1), "SLVERR read")
                assert wr.resp == rd.resp == AxiResp.SLVERR, f"lost downstream SLVERR: {desc['name']}"
                errors += 1
            finally:
                sink.write_if.target = sink.read_if.target = memory[name]
    dut._log.info("PASS downstream errors: %d routed B/R SLVERR pairs", errors)

    # Opt-in negative run must fail on an actual routed corrupt readback.
    if os.getenv("SUPERNOC_NEGATIVE") == "1":
        trace_phase('Injected readback corruption — expected test failure')
        desc = CONTRACT["masters"][0]
        address = desc["regions"][0]["base"] + 0x40
        target = expected_sink(desc, address, 4)
        await transfer(masters[desc["name"]], desc, memory, address, b"GOOD")
        await memory[target].write(address, b"FAIL")
        rd = await bounded(masters[desc["name"]].read(address, 4), "injected mismatch")
        await Timer(1, units='ns')  # drain passive same-edge channel callbacks
        assert rd.data == b"GOOD", "FAIL supernoc injected data mismatch detected"

    await Timer(1, units='ns')
    dut._log.info("PASS supernoc: %d real FlooNoC meshes, %d local/global links, %d AXI4 routes",
                  CONTRACT["meshes"], CONTRACT["links"], len(visits))
