"""Unloaded one-beat performance run using the EXISTING upstream SuperNoC BFM.

This is a separate regression target, not another traffic framework. Hardware
owns all FlooNoC interfaces between the AXI agents; no direct RTL bus driving.
"""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import Timer
from cocotbext.axi import AxiResp

from dv.common.axi_trace import trace_phase
from dv.supernoc.test_supernoc import setup, bounded
from tools.fabric_benchmark import config, plan, intent

ROOT = Path(__file__).resolve().parents[2]


@cocotb.test(timeout_time=3000, timeout_unit="us")
async def unloaded_fabric_latency(dut):
    manifest = json.loads((ROOT/"gen/supernoc/manifest.json").read_text())
    profile = config(ROOT)
    cases = plan(manifest, profile)
    declaration = intent(cases, profile, "supernoc")
    plan_file = os.environ.get("SOC_RUN_PLAN")
    if not plan_file:
        raise AssertionError("benchmark requires canonical regression plan")
    (Path(plan_file).parent/"fabric-benchmark-plan.json").write_text(
        json.dumps(declaration,indent=2,sort_keys=True)+"\n")

    masters, sinks, memory = await setup(dut)
    trace_phase("Fabric benchmark: warmup not measured")
    warmup_count = 0
    measured_count = 0
    for case in cases:
        if not case["warmup"] and not measured_count:
            trace_phase(profile["phase"])
        elif case["warmup"] and measured_count:
            raise AssertionError("warmup samples cannot follow measured samples")
        agent = masters[case["master"]]
        address = int(case["address"],16)
        data = bytes((address // case["bytes"] + i * 37) & 255
                     for i in range(case["bytes"]))
        if case["access"] == "read":
            # The ROM/flash model is read-only over AXI; seed its BFM-side
            # target backing, never pretend it is a CPU-cold-boot test.
            await memory[case["target"]].write(address,data)
        else:
            wr = await bounded(agent.write(address,data,awid=0),
                               case["case_id"]+" AW/W/B")
            assert wr.resp == AxiResp.OKAY, case["case_id"]+" bad B"
            assert await memory[case["target"]].read(address,len(data)) == data, (
                case["case_id"]+" incorrect target backing")
        rd = await bounded(agent.read(address,len(data),arid=0),
                           case["case_id"]+" AR/R")
        assert rd.resp == AxiResp.OKAY and rd.data == data, (
            case["case_id"]+" wrong readback")
        if case["warmup"]:
            warmup_count += 1
        else:
            measured_count += 1
    assert measured_count == declaration["measured_cases"]
    await Timer(1,units="ns")  # flush passive callbacks before simulator exit
    dut._log.info("PASS fabric-latency: %d warmup / %d measured source-route cases; "
                  "%d expected accepted read/write transactions",
                  warmup_count,measured_count,
                  declaration["expected_measured_transactions"])
