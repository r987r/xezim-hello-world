"""One real CPU0/PULP iDMA INIT/RUN/CHECK against actual pinned LiteDRAM RTL.

The source-true generated NoCs and existing C firmware/monitor checker are
reused. The new independent evidence strictly requires controller AXI B/R
completion, DFI read/write signals and behavioral BankModel storage writes.
"""
import json
import os
from pathlib import Path

import cocotb
from dv.full_chip.test_boot import execute_cold_boot


@cocotb.test(timeout_time=20, timeout_unit="ms")
async def cpu_dma_real_ddr_roundtrip(dut):
    assert os.environ.get("SOC_DDR_REAL_MODE") == "1"
    assert os.environ.get("SOC_CPU_DMA_MODE") == "1"
    await execute_cold_boot(dut)
    dd = dut.dut.u_ddr_real
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
        "cpu_dma_success": int(dut.cpu_dma_success.value)
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
                  "AXI completions + DFI/bank model evidence %s", evidence)
