"""Unloaded one-beat performance run using the EXISTING upstream SuperNoC BFM.

This is a separate regression target, not another traffic framework. Hardware
owns all FlooNoC interfaces between the AXI agents; no direct RTL bus driving.
"""
import json
import os
from pathlib import Path

import cocotb
from dv.common.fabric_latency import execute
from dv.supernoc.test_supernoc import setup, bounded
from tools.fabric_benchmark import config, plan, intent

ROOT = Path(__file__).resolve().parents[2]


@cocotb.test(timeout_time=3000, timeout_unit="us")
async def unloaded_fabric_latency(dut):
    manifest = json.loads((ROOT/"gen/supernoc/manifest.json").read_text())
    profile = config(ROOT)
    cases = plan(manifest, profile)
    declaration = intent(cases, profile, "supernoc-latency")
    plan_file = os.environ.get("SOC_RUN_PLAN")
    if not plan_file:
        raise AssertionError("benchmark requires canonical regression plan")
    (Path(plan_file).parent/"fabric-benchmark-plan.json").write_text(
        json.dumps(declaration,indent=2,sort_keys=True)+"\n")

    masters, sinks, memory = await setup(dut)
    warmup_count, measured_count = await execute(
        cases, profile, masters, bounded, backing=memory)
    assert measured_count == declaration["measured_cases"]
    dut._log.info("PASS fabric-latency: %d warmup / %d measured source-route cases; "
                  "%d expected accepted read/write transactions",
                  warmup_count,measured_count,
                  declaration["expected_measured_transactions"])
