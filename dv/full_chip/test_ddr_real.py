"""One real CPU0/PULP iDMA INIT/RUN/CHECK against actual pinned LiteDRAM RTL.

The source-true generated NoCs and existing C firmware/monitor checker are
reused. The new independent evidence strictly requires controller AXI B/R
completion, DFI read/write signals and behavioral BankModel storage writes.
"""
import json
import os
from pathlib import Path

import cocotb
from cocotb.triggers import Timer, with_timeout
from cocotbext.axi import AxiBus, AxiMaster, AxiResp
from dv.common.axi_trace import expect_axi_response, trace_phase
from dv.full_chip.test_boot import execute_cold_boot


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def cpu_dma_real_ddr_roundtrip(dut):
    assert os.environ.get("SOC_DDR_REAL_MODE") == "1"
    assert os.environ.get("SOC_CPU_DMA_MODE") == "1"
    await execute_cold_boot(dut)
    dd = dut.dut.u_ddr_real
    # The real CPU and pinned PULP iDMA have already completed CHECK.
    # Reusing the existing data probe is safe only after real controller
    # transactions drain; RTL gates both request and response ownership.
    assert int(dut.pass_flag.value) == 1 and int(dut.cpu_dma_success.value) == 1
    assert int(dut.ddr_init_mode.value) == 0
    assert int(dut.ddr_negative_mode.value) == 0
    assert int(dd.controller_axi_aw_count.value) == int(dd.controller_axi_b_count.value)
    assert int(dd.controller_axi_ar_count.value) == int(dd.controller_axi_rlast_count.value)
    dut.ddr_negative_mode.value = 1
    await Timer(50, "ns")
    probe = AxiMaster(AxiBus.from_prefix(dut, "probe"), dut.clk, dut.rst_n,
                      reset_active_level=False)
    ddr_base = 0x1_4000_0000
    modeled_bytes = 32 * 1024 * 1024
    valid = ddr_base + 0x1000
    invalid = valid + modeled_bytes
    pattern = b"DDR-NO-ALIAS-OK!"
    poison = b"ALIAS-CORRUPTION"
    trace_phase("DDR routed invalid-aperture negative test via compute0 DMA NoC")
    good_write = await with_timeout(probe.write(valid, pattern), 250, "us")
    assert good_write.resp == AxiResp.OKAY, good_write
    before = await with_timeout(probe.read(valid, len(pattern)), 250, "us")
    assert before.resp == AxiResp.OKAY and before.data == pattern, before
    counts_before = (int(dd.controller_axi_aw_count.value),
                     int(dd.controller_axi_ar_count.value))
    # Exactly one 32-MiB offset: a controller that incorrectly truncates
    # physical addresses would overwrite the same low 25-bit data.
    expect_axi_response("compute0_local_data.dma", "write", invalid, 3,
                        "DDR 32MiB off-end write must DECERR without alias")
    bad_write = await with_timeout(probe.write(invalid, poison), 250, "us")
    assert bad_write.resp == AxiResp.DECERR, bad_write
    expect_axi_response("compute0_local_data.dma", "read", invalid, 3,
                        "DDR 32MiB off-end read must DECERR without alias")
    bad_read = await with_timeout(probe.read(invalid, len(poison)), 250, "us")
    assert bad_read.resp == AxiResp.DECERR, bad_read
    counts_after = (int(dd.controller_axi_aw_count.value),
                    int(dd.controller_axi_ar_count.value))
    assert counts_before == counts_after, (
        "illegal DDR addresses reached real controller AXI pins",
        counts_before, counts_after)
    after = await with_timeout(probe.read(valid, len(pattern)), 250, "us")
    assert after.resp == AxiResp.OKAY and after.data == pattern, (
        "invalid DDR write aliased valid modeled storage", after)
    trace_phase("DDR routed DECERR and nonalias CHECK complete")

    evidence = {
        "schema_version": 1,
        "scope": "fullchip_real_cpu_idma_litedram_behavioral_dfi",
        "controller": "pinned LiteDRAM RTL; upstream SDRAMPHYModel/BankModel",
        "physical_phy": "NOT_MODELED",
        "init_done": int(dd.ddr_init_done_o.value),
        "init_error": int(dd.ddr_init_error_o.value),
        "axi_aw": int(dd.controller_axi_aw_count.value),
        "axi_b": int(dd.controller_axi_b_count.value),
        "axi_ar": int(dd.controller_axi_ar_count.value),
        "axi_rlast": int(dd.controller_axi_rlast_count.value),
        "dfi_read": int(dd.dfi_read_count.value),
        "dfi_write": int(dd.dfi_write_count.value),
        "bank_storage_write": int(dd.bank_storage_write_count.value),
        "cpu_dma_success": int(dut.cpu_dma_success.value),
        "routed_negative": {
            "source": "compute0_local_data.dma",
            "mode": "verification_only_after_CPU_CHECK",
            "modeled_bytes": modeled_bytes,
            "valid_address": hex(valid),
            "invalid_address": hex(invalid),
            "bad_write_resp": int(bad_write.resp),
            "bad_read_resp": int(bad_read.resp),
            "no_controller_forwarding": counts_before == counts_after,
            "nonaliased_valid_readback": after.data == pattern,
            "status": "pass"
        }
    }
    assert evidence["init_done"] == 1 and evidence["init_error"] == 0
    assert evidence["cpu_dma_success"] == 1
    assert min(evidence[k] for k in
               ("axi_aw", "axi_b", "axi_ar", "axi_rlast",
                "dfi_read", "dfi_write", "bank_storage_write")) > 0, evidence
    assert evidence["axi_aw"] == evidence["axi_b"], evidence
    assert evidence["axi_ar"] == evidence["axi_rlast"], evidence
    evidence["status"] = "pass"
    path = Path(os.environ["SOC_RUN_PLAN"]).parent / "ddr4_fullchip_evidence.json"
    path.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
    dut._log.info("PASS DDR-B full-chip real CPU0 + PULP iDMA + pinned LiteDRAM "
                  "AXI/DFI/bank model and routed DECERR/no-alias evidence %s", evidence)
