"""One cocotbext-axi directed full eight-NoC AXI4 readback regression.

No custom BFM/NoC. The generated SystemVerilog wrapper connects all eight
real FlooGen routers and exports true AXI4 endpoint ports.
"""
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotbext.axi import AxiBus, AxiMaster, AxiRam, AxiResp

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT/"gen/supernoc/manifest.json").read_text())

@cocotb.test(timeout_time=250, timeout_unit="us")
async def routed_data_and_config_all_local_global_nocs(dut):
    dut.rst_ni.value = 0
    dut.clk_i.value = 0
    cocotb.start_soon(Clock(dut.clk_i, 10, unit="ns").start())
    sinks = {}
    for entry in CONTRACT["slaves"]:
        name = entry["name"]
        # AxiRam is sparse and has the standard 64-bit address aperture.
        # No custom memory responder or hand-authored AXI handshake.
        sinks[name] = AxiRam(
            AxiBus.from_prefix(dut, name), dut.clk_i, dut.rst_ni,
            reset_active_level=False
        )
    masters = {}
    for entry in CONTRACT["masters"]:
        name = entry["name"]
        masters[name] = AxiMaster(
            AxiBus.from_prefix(dut, name), dut.clk_i, dut.rst_ni,
            reset_active_level=False
        )
    for _ in range(12):
        await RisingEdge(dut.clk_i)
    dut.rst_ni.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk_i)

    visits = []
    # Sequential baseline avoids scoreboard cross-master address collisions.
    # Each originating AXI manager visits ALL address windows from its own
    # FlooGen SAM (local, remote SRAM, memory ingress, and CSR).
    for index, desc in enumerate(CONTRACT["masters"]):
        agent = masters[desc["name"]]
        word_bytes = desc["data_width"] // 8
        for window_index, region in enumerate(desc["regions"]):
            # per-origin disjoint location, even across shared targets
            addr = region["base"] + 0x100 + index * 16
            pattern = (
                0xA5A50000 ^ (index << 12) ^ (window_index << 4)
            ).to_bytes(word_bytes, "little")
            wr = await agent.write(addr, pattern)
            assert wr.resp == AxiResp.OKAY, f"{desc['name']} bad B at {addr:x}: {wr}"
            rd = await agent.read(addr, len(pattern))
            assert rd.resp == AxiResp.OKAY, f"{desc['name']} bad R at {addr:x}: {rd}"
            assert rd.data == pattern, (
                f"{desc['name']} route at {addr:x} expected {pattern.hex()}, got {rd.data.hex()}"
            )
            visits.append((desc["name"], addr))
            dut._log.info("PASS %s -> 0x%x: write/readback", desc["name"], addr)

    assert len(visits) >= len(CONTRACT["masters"]), "missing routed stimulus"
    dut._log.info(
        "PASS supernoc: %d real FlooNoC meshes, %d local/global links, %d AXI4 routes",
        CONTRACT["meshes"], CONTRACT["links"], len(visits)
    )
