"""Run a pinned real PCIe TLP-to-AXI4 bridge in Icarus/Cocotb.

The Root Complex, Endpoint link and AXI RAM are simulation models.
No PCIe PHY, FlooNoC integration or real SRAM is claimed.
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "dv/pcie0/upstream.lock.json"
VENDOR = ROOT / ".tools/verilog_pcie"
TEST_DIR = ROOT / "dv/pcie0"


def source_contract():
    cfg = json.loads(LOCK.read_text())
    if cfg.get("schema_version") != 1 or cfg.get("name") != "verilog_pcie":
        raise ValueError("unsupported PCIe vendor lock")
    sha = cfg.get("commit", "")
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        raise ValueError("PCIe RTL must be locked to a full SHA-1")
    if cfg.get("license") != "MIT" or cfg.get("module") != "pcie_axi_master":
        raise ValueError("unsupported PCIe module/license contract")
    if not (VENDOR / ".git").exists():
        raise ValueError("pinned verilog-pcie checkout missing under .tools/verilog_pcie")
    actual = subprocess.check_output(
        ["git", "-C", str(VENDOR), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != sha:
        raise ValueError(f"PCIe RTL revision mismatch: expected {sha}, got {actual}")
    for path in cfg["rtl_modules"] + cfg["python_models"]:
        if not path.startswith(("rtl/", "tb/")) or ".." in Path(path).parts:
            raise ValueError(f"unsafe upstream path: {path}")
        if not (VENDOR / path).is_file():
            raise ValueError(f"pinned PCIe IP file missing: {path}")
    return cfg


def run():
    cfg = source_contract()
    from cocotb_test.simulator import run as cocotb_run
    sources = [str(VENDOR / p) for p in cfg["rtl_modules"]]
    params = dict(
        TLP_DATA_WIDTH=64,
        TLP_STRB_WIDTH=2,
        TLP_HDR_WIDTH=128,
        TLP_SEG_COUNT=1,
        AXI_DATA_WIDTH=64,
        AXI_ADDR_WIDTH=64,
        AXI_STRB_WIDTH=8,
        AXI_ID_WIDTH=8,
        AXI_MAX_BURST_LEN=256,
        TLP_FORCE_64_BIT_ADDR=0,
    )
    cocotb_run(
        verilog_sources=sources,
        toplevel=cfg["module"],
        module="rtl_smoke",
        python_search=[str(TEST_DIR), str(VENDOR / "tb/pcie_axi_master")],
        parameters=params,
        sim_build=str(ROOT / ".tools/pcie0/sim_build"),
        extra_env={"COCOTB_RESOLVE_X": "RANDOM"},
        timescale="1ns/1ps",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-pin", action="store_true")
    args = parser.parse_args()
    if args.check_pin:
        cfg = source_contract()
        print(f"PCIe upstream pin PASS: {cfg['name']} {cfg['commit']}")
    else:
        run()
