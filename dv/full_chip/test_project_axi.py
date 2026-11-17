"""Real AXI4 DDR/model data-path readback on a catalog-selected full chip.

Only the reserved compute0 DMA verification port is BFM-owned. Real CPU
boots from immutable ROM/flash and completes INIT/RUN/CHECK first. The DUT
contains actual generated FlooNoCs, not a behavioral bypass to RAM.
"""
import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, with_timeout
from cocotbext.axi import AxiBus, AxiMaster

ROOT = Path(__file__).resolve().parents[2]


@cocotb.test()
async def selected_chip_axi_memory_roundtrip(dut):
    project_id = os.environ["SOC_PROJECT_ID"]
    build = ROOT / ".tools/projects" / project_id
    identity = json.loads((build / "manifest.json").read_text())
    chip = json.loads((build / "chip/manifest.json").read_text())
    assert identity["project_id"] == project_id
    assert not identity["routed_axi_test_passed"], "generation cannot claim verified traffic"
    assert chip["testbench"] == "full_chip_tb"
    memory = chip["memory_models"]
    assert memory, "no attached bounded RTL memory models"

    dut.rst_n.value = 0
    # The existing common generated top enables the reserved data-side
    # probe exclusively for Cocotb. No CPU data bus is hijacked.
    master = AxiMaster(AxiBus.from_prefix(dut, "probe"), dut.clk,
                       dut.rst_n, reset_active_level=False)
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for _ in range(10):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    for signal in (dut.init_complete, dut.run_complete, dut.check_complete):
        if int(signal.value) != 1:
            await with_timeout(RisingEdge(signal), 2, "ms")
    assert int(dut.pass_flag.value) == 1, "selected CPU/NoC boot did not complete"

    results = []
    for idx, target in enumerate(memory):
        base = int(target["base"])
        capacity = int(target["modeled_bytes"])
        assert capacity >= 0x800, "model too small for isolated AXI roundtrip"
        # Preserve all firmware+mailbox locations; test memory models only.
        address = base + 0x400
        original = bytes((idx * 41 + pos * 37 + 13) & 0xff for pos in range(32))
        amended = bytearray(original)
        amended[7:14] = b"AXI-DV!"
        w = await with_timeout(master.write(address, original), 40, "us")
        assert w.resp == 0, f"{target['name']} original AXI write failed: {w.resp}"
        w = await with_timeout(master.write(address + 7, b"AXI-DV!"), 40, "us")
        assert w.resp == 0, f"{target['name']} partial AXI write failed: {w.resp}"
        r = await with_timeout(master.read(address, len(amended)), 40, "us")
        assert r.resp == 0, f"{target['name']} AXI read failed: {r.resp}"
        assert bytes(r.data) == bytes(amended), (
            f"{target['name']} AXI readback mismatch; no bytes-checked PASS")
        results.append({"target": target["name"], "address": hex(address),
                        "bytes_checked": len(amended),
                        "write_responses": [w.resp], "read_resp": r.resp})
        dut._log.info("PASS selected-project real AXI4 bytes: %s %d bytes",
                      target["name"], len(amended))

    await Timer(10, units="ns")
    report = {
        "schema_version": 1, "project_id": project_id,
        "test": "full_chip_selected_axi_readback",
        "scope": "real generated FlooNoC via reserved AXI4 BFM to modeled memory",
        "cpu_boot_verified": True, "actual_axi_readback": True,
        "memory": results, "ethernet_qualified": False,
        "pcie_qualified": False, "real_ddr_controller_qualified": False,
    }
    out = ROOT / ".tools/project-axi" / project_id / "axi-result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
