"""Shared latency execution adapter for authorized upstream AXI BFM owners.

The case compiler is tools.fabric_benchmark; the runtime only invokes the
existing cocotbext-axi master methods. It cannot bypass the AXI protocol
driver, attach a BFM to another owner's pins, generate completion evidence,
or create a second regression/phase/report coordinator.
"""
from cocotb.triggers import Timer

from dv.common.axi_trace import trace_phase


async def execute(cases, profile, masters, bounded, *, backing=None):
    # Separate warmups from real measurements without mutating the single
    # source-owned plan's case set. One AXI operation is awaited at a time.
    warmup_count = measured_count = 0
    for warmup, label in ((True, "Fabric benchmark: warmup not measured"),
                          (False, profile["phase"])):
        trace_phase(label)
        for case in (c for c in cases if c["warmup"] == warmup):
            if case["master"] not in masters:
                raise AssertionError("unowned/unknown AXI initiator: "+case["master"])
            agent = masters[case["master"]]
            address = int(case["address"], 16)
            size = case["bytes"]
            payload = bytes(((address // size + b * 37) & 255) for b in range(size))
            context = case["case_id"]
            if case["access"] == "read":
                if backing is None or case["target"] not in backing:
                    raise AssertionError("read-only target requires explicit modeled-memory owner")
                # Only the standalone BFM model's backing is initialized:
                # never load a real CPU ROM or cold-boot SRAM behind the DUT.
                await backing[case["target"]].write(address,payload)
            else:
                written = await bounded(agent.write(address,payload,awid=0),
                                        context+" accepted write")
                if int(written.resp) != 0:
                    raise AssertionError(context+" unexpected AXI B response")
                if backing is not None:
                    if case["target"] not in backing or (
                            await backing[case["target"]].read(address,size)) != payload:
                        raise AssertionError(context+" wrong target storage")
            received = await bounded(agent.read(address,size,arid=0),
                                     context+" accepted read")
            if int(received.resp) != 0 or bytes(received.data) != payload:
                raise AssertionError(context+" AXI readback/bytes mismatch")
            if warmup:
                warmup_count += 1
            else:
                measured_count += 1
    await Timer(1,units="ns")
    return warmup_count, measured_count
