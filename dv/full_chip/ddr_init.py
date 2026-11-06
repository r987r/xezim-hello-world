"""Drive pinned LiteDRAM's existing JEDEC/DFII script through the real Config NoC.

No direct Wishbone force, deposited memory data, invented init ACK, or second
simulation/phase engine. The controller's own generated CSR JSON and upstream
init_plan.wishbone_script() are compiled by tools/ddr_chip.py at run setup.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from cocotb.triggers import Timer, with_timeout
from cocotbext.axi import AxiBus, AxiMaster, AxiResp


async def initialize_controller(dut):
    plan_path = os.environ.get("SOC_RUN_PLAN")
    assert plan_path, "DDR full-chip init must use the standard regression plan"
    script_file = Path(plan_path).parent / "ddr_noc" / "ddr4_init_script.json"
    script = json.loads(script_file.read_text())
    assert script["config_base"] == 0x40030000
    assert script["window_bytes"] == 16384
    assert script["requires_hardware_translator"]
    assert script["actions"], "no generated LiteDRAM DFII init steps"
    assert int(dut.ddr_init_mode.value) == 1, "CPU must be held until DDR init succeeds"
    cfg = AxiMaster(AxiBus.from_prefix(dut, "cfgprobe"), dut.clk, dut.rst_n,
                    reset_active_level=False)
    written = read = 0
    for op in script["actions"]:
        name = op["op"]
        if name == "wait_cycles":
            await Timer(op["cycles"] * 10, units="ns")
        elif name == "config_write32":
            resp = await with_timeout(
                cfg.write(op["config_addr"], int(op["value"]).to_bytes(4, "little")),
                80, "us")
            assert resp.resp == AxiResp.OKAY, (
                f"Real Config NoC DDR CSR write {op['csr']} failed: {resp}")
            written += 1
        elif name == "config_read32":
            resp = await with_timeout(cfg.read(op["config_addr"], 4), 80, "us")
            assert resp.resp == AxiResp.OKAY, (
                f"Real Config NoC DDR CSR read {op['csr']} failed: {resp}")
            value = int.from_bytes(resp.data, "little")
            assert value & op["expect_mask"] == op["expect_value"], (
                f"Real DDR controller CSR {op['csr']} read {value:#x} "
                f"expected {op['expect_value']:#x}")
            read += 1
        else:
            raise AssertionError(f"unknown generated DDR init command: {name}")
    assert written >= 10 and read == 3, (written, read)
    controller = dut.dut.u_ddr_real
    assert int(controller.ddr_init_done_o.value) == 1, "DDR init_done pin low"
    assert int(controller.ddr_init_error_o.value) == 0, "DDR init_error pin high"
    assert int(controller.ddr_user_rst.value) == 0, "DDR simulation user reset active"
    dut._log.info("PASS DDR_INIT_CONFIG_NOC real routed AXI->Wishbone->DFII, "
                  "%d actual CSR writes, %d checked CSR reads", written, read)
    # CPU0 takes control of the same Config NoC after script and status checks.
    # Keep the AXI config agent alive but disconnected by real RTL mux.
    dut.ddr_init_mode.value = 0
    return cfg
