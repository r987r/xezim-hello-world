"""One real eight-FlooNoC DUT with upstream AXI agents and sparse targets."""
import itertools
import json
import os
import resource
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, with_timeout
from cocotb.utils import get_sim_time
from cocotbext.axi import (
    AddressSpace, AxiBus, AxiMaster, AxiResp, AxiSlave, SparseMemoryRegion,
)
from dv.common.axi_trace import attach_observers, expect_axi_response, trace_phase
from tools.memory_plan import configured_regions, VirtualRegion
from tools.memory_service import (
    MemoryService, Pattern, AxiFrontdoor, HostSparseMemory, CombinedMemoryProvider,
)

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



async def same_id_local_global_ordering(dut, masters, sinks, memory):
    """Exercise AXI ordering at the FIRST split and again at the global split.

    Earlier AW/AR and later AW/AR carry the same source ID but route to
    different targets. Delaying the earlier target B/R forces an actual
    cross-destination race. Different B responses / read payloads make a
    swapped completion observable at the originating initiator.
    """
    trace_phase("Same-ID B/R ordering: local vs global, remote SRAM vs DDR")
    all_data = [x for x in CONTRACT["masters"] if x["plane"] == "data"]
    routes_by_source = {}
    b_cases = r_cases = 0

    for index, desc in enumerate(CONTRACT["masters"]):
        if desc["plane"] != "data":
            continue
        # Source-true route selection: require each Data-NoC initiator to
        # reach its own local SRAM, at least one other subsystem's SRAM,
        # and Memory0 DDR. Never silently skip an initiator.
        routes = []
        for region in desc["regions"]:
            if region["access"] != "read_write" or region["size"] < 0x4000:
                continue
            address = region["base"] + 0x2c00 + index * 0x40
            routes.append((address, expected_sink(desc, address, 8)))
        local = next((r for r in routes
                      if r[1] == f"s_{desc['network']}_sram"), None)
        remote = next((r for r in routes
                       if r[1].endswith("_sram") and r[1] != (local[1] if local else None)), None)
        ddr = next((r for r in routes
                    if r[0] >= 0x100000000 and r[0] < 0x140000000
                    and r[1] == "s_memory0_local_data_target_crossbar"), None)
        hbm = next((r for r in routes
                    if r[0] >= 0x140000000 and r[0] < 0x180000000
                    and r[1] == "s_memory0_local_data_target_crossbar"), None)
        assert all((local, remote, ddr, hbm)), (
            f"{desc['name']}: missing local/global/DDR/HBM path in generated manifest")
        routes_by_source[desc["name"]] = (desc, local, remote, ddr, hbm)
        master = masters[desc["name"]]
        monitor = desc["network"] + "." + desc["endpoint"]

        async def check_b_order(older, newer, label):
            old_addr, old_sink = older
            new_addr, new_sink = newer
            slave = sinks[old_sink]
            # Make the older B a deliberate SLVERR; the younger B is OKAY.
            # Thus even when the master sees the same BID in both responses,
            # a response-order inversion is detectable.
            slave.write_if.target = AddressSpace(size=1 << desc["addr_width"])
            slave.write_if.b_channel.set_pause_generator(
                itertools.chain(itertools.repeat(1, 120), itertools.repeat(0)))
            expect_axi_response(monitor, "write", old_addr, AxiResp.SLVERR,
                                "Expected older same-ID B error: " + label)
            try:
                first = cocotb.start_soon(master.write(old_addr, b"OLDERROR", awid=1))
                # Allow AW to launch before starting another AW with BID=1.
                for _ in range(6):
                    await RisingEdge(dut.clk_i)
                second = cocotb.start_soon(master.write(new_addr, b"NEWDATA!", awid=1))
                old_result = await bounded(first, label + " older B")
                new_result = await bounded(second, label + " newer B")
                assert old_result.resp == AxiResp.SLVERR, (
                    f"{label}: older same-ID B was overtaken (got {old_result.resp})")
                assert new_result.resp == AxiResp.OKAY, (
                    f"{label}: newer same-ID B did not return OKAY ({new_result.resp})")
                assert await memory[new_sink].read(new_addr, 8) == b"NEWDATA!", (
                    f"{label}: younger target data corrupted/misrouted")
            finally:
                slave.write_if.b_channel.set_pause_generator(itertools.repeat(0))
                slave.write_if.target = memory[old_sink]

        async def check_r_order(older, newer, label):
            old_addr, old_sink = older
            new_addr, new_sink = newer
            old_addr += 0x10
            new_addr += 0x10
            old_bytes = b"OLDER_R!"
            new_bytes = b"NEWER_R!"
            await memory[old_sink].write(old_addr, old_bytes)
            await memory[new_sink].write(new_addr, new_bytes)
            channel = sinks[old_sink].read_if.r_channel
            channel.set_pause_generator(
                itertools.chain(itertools.repeat(1, 120), itertools.repeat(0)))
            try:
                first = cocotb.start_soon(master.read(old_addr, 8, arid=1))
                for _ in range(6):
                    await RisingEdge(dut.clk_i)
                second = cocotb.start_soon(master.read(new_addr, 8, arid=1))
                old_result = await bounded(first, label + " older R")
                new_result = await bounded(second, label + " newer R")
                assert old_result.resp == new_result.resp == AxiResp.OKAY, (
                    f"{label}: non-OKAY same-ID R response")
                assert old_result.data == old_bytes, (
                    f"{label}: older same-ID R overtaken; got {old_result.data.hex()}")
                assert new_result.data == new_bytes, (
                    f"{label}: newer same-ID R mispaired; got {new_result.data.hex()}")
            finally:
                channel.set_pause_generator(itertools.repeat(0))

        # Two ordering boundaries with conflicting older/newer B statuses:
        # local vs global and two distinct global destinations.
        await check_b_order(local, ddr, desc["name"] + " local SRAM->DDR")
        await check_b_order(remote, ddr, desc["name"] + " remote SRAM->DDR")
        await check_b_order(ddr, local, desc["name"] + " DDR->local SRAM")
        b_cases += 3
        await check_r_order(local, ddr, desc["name"] + " local SRAM->DDR")
        await check_r_order(remote, ddr, desc["name"] + " remote SRAM->DDR")
        r_cases += 2

        # DDR and HBM share the Memory0 ingress endpoint in this particular
        # SuperNoC TB, so do not falsely claim it models internal DDR/HBM
        # controller scheduling. Still verify same-ID address non-aliasing.
        aw0 = cocotb.start_soon(master.write(ddr[0] + 0x20, b"DDRDATA!", awid=1))
        for _ in range(6):
            await RisingEdge(dut.clk_i)
        aw1 = cocotb.start_soon(master.write(hbm[0] + 0x20, b"HBMDATA!", awid=1))
        assert (await bounded(aw0, "DDR write B")).resp == AxiResp.OKAY
        assert (await bounded(aw1, "HBM write B")).resp == AxiResp.OKAY
        assert await memory[ddr[1]].read(ddr[0] + 0x20, 8) == b"DDRDATA!"
        assert await memory[hbm[1]].read(hbm[0] + 0x20, 8) == b"HBMDATA!"
        b_cases += 2
        dut._log.info("PASS same-ID B/R ordering for %s: local/global, remote/DDR, DDR/local, DDR/HBM",
                      desc["name"])

    # Same BID=1 is legal on two independent initiators. Test simultaneous
    # writes using separate source ports of the same local NoC (CPU and DMA),
    # where the two flows must not accidentally share response bookkeeping.
    paired = 0
    by_network = {}
    for desc in all_data:
        by_network.setdefault(desc["network"], []).append(desc)
    trace_phase("Same numeric ID across independent initiators")
    for network, group in by_network.items():
        if len(group) < 2:
            continue
        first_desc, second_desc = group[:2]
        first_master = masters[first_desc["name"]]
        second_master = masters[second_desc["name"]]
        _, _, first_remote, _, _ = routes_by_source[first_desc["name"]]
        _, _, _, second_ddr, _ = routes_by_source[second_desc["name"]]
        old_addr, old_sink = first_remote
        new_addr, new_sink = second_ddr
        # Source-specific scratch addresses were generated above, so this
        # second writer cannot alias an earlier matching target byte range.
        slave = sinks[old_sink]
        slave.write_if.target = AddressSpace(size=1 << first_desc["addr_width"])
        slave.write_if.b_channel.set_pause_generator(
            itertools.chain(itertools.repeat(1, 120), itertools.repeat(0)))
        expect_axi_response(first_desc["network"] + "." + first_desc["endpoint"],
                            "write", old_addr, AxiResp.SLVERR,
                            "Independent initiators reuse BID 1: " + network)
        try:
            first = cocotb.start_soon(first_master.write(old_addr, b"OLDERROR", awid=1))
            for _ in range(6):
                await RisingEdge(dut.clk_i)
            second = cocotb.start_soon(second_master.write(new_addr, b"NEWDATA!", awid=1))
            result_new = await bounded(second, network + " independent DMA B")
            result_old = await bounded(first, network + " independent CPU B")
            assert result_old.resp == AxiResp.SLVERR, (
                f"{network}: response status escaped independent master")
            assert result_new.resp == AxiResp.OKAY, (
                f"{network}: same numeric BID confused independent master")
            assert await memory[new_sink].read(new_addr, 8) == b"NEWDATA!"
        finally:
            slave.write_if.b_channel.set_pause_generator(itertools.repeat(0))
            slave.write_if.target = memory[old_sink]
        paired += 1
    assert len(routes_by_source) == len(all_data) and paired, (
        f"missing directed same-ID coverage: sources={len(routes_by_source)}/"
        f"{len(all_data)} independent_pairs={paired}")
    dut._log.info("PASS supernoc same-ID source ordering: %d B, %d R, %d independent-source pairs",
                  b_cases, r_cases, paired)

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

    # One-at-a-time AXI4 single-beat transfers, BEFORE the pause generators
    # and concurrent stress start. Unique per-source/target/sample addresses
    # allow passive source/link/target traces to be paired without presuming
    # IDs survive NoC remapping. Each response is awaited before the next.
    trace_phase('Fabric baseline: single-outstanding one-beat')
    baseline_cases = 0
    for index, desc in enumerate(CONTRACT["masters"]):
        word_bytes = desc["data_width"] // 8
        for wi, region in enumerate(desc["regions"]):
            for sample in range(3):
                address = region["base"] + 0x200 + index * 0x100 + sample * 0x10
                payload = bytes((index * 23 + wi * 41 + sample * 13 + b) & 255
                                for b in range(word_bytes))
                await transfer(masters[desc["name"]], desc, memory, address,
                               payload, txn_id=sample & 1,
                               readonly=region["access"] == "read")
                baseline_cases += 1
    dut._log.info("PASS controlled one-beat baseline: %d serial route samples, no injected channel pauses",
                  baseline_cases)

    await same_id_local_global_ordering(dut, masters, sinks, memory)

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

    # Reuse the SAME upstream BFM and sparse backing as routed NoC traffic.
    # This is the first actual RTL validation of strict/fast/hybrid providers,
    # not a second testbench or a CPU cold-SRAM preload. Active AXI master
    # ownership is already established by setup(); monitors remain passive.
    trace_phase("Memory INIT/CHECK: reciprocal AXI/backdoor proof")
    # Select from configured modeled regions and actual generated route contract.
    # Never assume a compute0 master, HBM first or 1-GiB backing capacity.
    import yaml
    cfg = yaml.safe_load((ROOT/"config/soc.yaml").read_text())
    models = configured_regions(cfg)
    target_names = {target["name"] for target in cfg["memory_targets"]}
    routes = []
    for physical in models.values():
        if physical.name not in target_names or physical.capacity < 0x5000:
            continue
        offset = ((max(0x4000, physical.capacity // 2) + 63) // 64) * 64
        if offset + 512 > physical.capacity:
            continue
        address = physical.base + offset
        for desc in CONTRACT["masters"]:
            if desc["plane"] != "data":
                continue
            if any(w["access"] == "read_write" and
                   w["base"] <= address and address+512 <= w["base"]+w["size"]
                   for w in desc["regions"]):
                routes.append((physical.name, physical, desc, address))
    assert routes, "no mapped modeled target with independent memory test scratch"
    region_name, physical, desc, address = sorted(
        routes, key=lambda x: (x[0], x[2]["name"]))[0]
    target = expected_sink(desc, address, 512)
    provider = CombinedMemoryProvider(
        AxiFrontdoor(masters[desc["name"]]),
        HostSparseMemory(memory[target], physical_base=0))
    await bounded(provider.validate_backdoor(
        address, consumers_quiesced=True), "memory provider reciprocal proof")
    rss_at_start = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    region = VirtualRegion(region_name+".test", physical.kind,
                           address, 512, False)
    service = MemoryService({region.name: region}, chunk_bytes=64,
                            cycle_counter=lambda: int(get_sim_time(units="ps")) // 10000)
    service.register(region.name, provider)
    allocation = service.allocate(region.name, 256, 64,
                                  owner="supernoc_verification", phase="run")
    recipe = Pattern("address_xor", 0x5a71)
    for policy in ("strict", "fast", "hybrid"):
        await bounded(service.initialize(allocation, recipe, policy=policy),
                      "memory "+policy+" initialize")
        await bounded(service.check(allocation, recipe, policy=policy),
                      "memory "+policy+" check")
    service.release(allocation, consumers_quiesced=True)
    plan_file = os.environ.get("SOC_RUN_PLAN")
    if plan_file:
        result = {
            "schema_version": 1, "source": "real_floonoc_host_sparse",
            "scope": "noc_bfm", "region": region_name,
            "route_initiator": desc["name"], "memory_target": target,
            "address": hex(address), "size_bytes": 256,
            "clock_period_ps": 10000,
            "host_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "host_peak_rss_delta_kib": max(
                0, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss_at_start),
            "validation": "two-way AXI/backdoor proof plus scratch restoration",
            "events": [event.as_dict() for event in service.events],
        }
        (Path(plan_file).parent/"memory-operations.json").write_text(
            json.dumps(result, indent=2, sort_keys=True)+"\n")
    trace_phase("Memory INIT/CHECK: strict fast hybrid verified")
    dut._log.info("PASS memory provider: strict fast hybrid, %s to %s at %#x",
                  desc["name"], target, address)

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
