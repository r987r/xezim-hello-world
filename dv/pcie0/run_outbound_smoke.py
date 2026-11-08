"""Isolated *real RTL* outbound PCIe requester smoke, not a second SoC runner.

The already-pinned verilog-pcie dma_if_pcie is clocked against the same modeled
Root Complex used by PCIe0.  Its segmented RAM port is modeled locally here;
a separate SoC/iDMA-to-segmented-RAM adapter remains to be implemented under #76.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / ".tools/verilog_pcie"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_rtl_smoke import source_contract


def run():
    from cocotb_test.simulator import run as cocotb_run

    pin = source_contract()
    expected = [
        "rtl/dma_if_pcie.v",
        "rtl/dma_if_pcie_rd.v",
        "rtl/dma_if_pcie_wr.v",
        "rtl/priority_encoder.v",
        "rtl/pulse_merge.v",
    ]
    if pin.get("outbound_rtl_modules") != expected:
        raise RuntimeError("outbound PCIe RTL must use the reviewed pinned module list")
    if pin.get("outbound_python_models") != ["tb/dma_if_pcie_wr/dma_psdp_ram.py"]:
        raise RuntimeError("outbound PCIe RAM model must be pinned")

    target = ROOT / ".tools/pcie0/outbound"
    target.mkdir(parents=True, exist_ok=True)
    sources = [str(VENDOR / f) for f in expected]
    parameters = {
        "TLP_DATA_WIDTH": 64,
        "TLP_STRB_WIDTH": 2,
        "TLP_HDR_WIDTH": 128,
        "TLP_SEG_COUNT": 1,
        "RAM_SEL_WIDTH": 2,
        "RAM_ADDR_WIDTH": 16,
        "PCIE_TAG_COUNT": 32,
        "READ_OP_TABLE_SIZE": 8,
        "WRITE_OP_TABLE_SIZE": 8,
        "READ_TX_LIMIT": 4,
        "WRITE_TX_LIMIT": 4,
        "TX_SEQ_NUM_ENABLE": 0,
        "LEN_WIDTH": 16,
        "TAG_WIDTH": 8,
    }
    (target / "rtl-sources.json").write_text(json.dumps({
        "upstream_sha": pin["commit"],
        "module": "dma_if_pcie",
        "rtl": expected,
        "parameters": parameters,
        "boundary": "isolated segmented device RAM; NOT iDMA or generated FlooNoC",
    }, indent=2) + "\n")
    cocotb_run(
        verilog_sources=sources,
        toplevel="dma_if_pcie",
        module="outbound_smoke",
        python_search=[str(HERE), str(VENDOR / "tb/pcie_axi_master"),
                       str(VENDOR / "tb/dma_if_pcie_wr")],
        parameters=parameters,
        sim_build=str(target / "sim_build"),
        extra_env={"SOC_PCIE_OUTBOUND_RESULT": str(target / "result.json")},
        timescale="1ns/1ps",
    )
    result = target / "result.json"
    if not result.is_file():
        raise RuntimeError("outbound requester simulation produced no independent host-memory evidence")
    evidence = json.loads(result.read_text())
    if not evidence.get("passed") or not all(evidence.get(k, 0) > 0 for k in
                                          ("tx_mem_write_tlps", "tx_mem_read_tlps",
                                           "rx_completion_tlps", "host_bytes_verified",
                                           "device_bytes_verified")):
        raise RuntimeError("outbound requester lacks positive TLP/byte evidence")
    print("PASS PCIE0_OUTBOUND_REQUESTER_REAL_TLP:", json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    run()
