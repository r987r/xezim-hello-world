"""Apply ONLY four width-typed tie-offs to immutable upstream verilog-pcie.

Icarus originally emitted "ERROR cocotb ... warning: Port ... got 32" for
four unsized zero literals in pcie_axi_master.v. This is an exact-source,
fail-closed build-time compatibility patch; it does not edit pinned upstream.
"""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / ".tools/verilog_pcie"
LOCK = ROOT / "dv/pcie0/upstream.lock.json"
OUTPUT = ROOT / ".tools/pcie0/normalized/pcie_axi_master.v"
TIE_OFFS = ("in_tlp_strb", "in_tlp_bar_id", "in_tlp_func_num", "in_tlp_error")


def prepare_bridge_source():
    cfg = json.loads(LOCK.read_text())
    if cfg["commit"] != subprocess.check_output(
        ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip():
        raise ValueError("refuse to patch unpinned PCIe upstream RTL")
    src = (UPSTREAM / "rtl/pcie_axi_master.v").read_text()
    patched = src
    for port in TIE_OFFS:
        anchor = f".{port}(0),"
        if patched.count(anchor) != 1:
            raise ValueError(f"pinned upstream changed width-tie anchor {anchor!r}")
        patched = patched.replace(anchor, f".{port}('0),")
    assert patched != src
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(patched)
    return OUTPUT


def assert_iverilog_clean():
    import shutil
    out = prepare_bridge_source()
    files = [out] + [
        UPSTREAM / name for name in json.loads(LOCK.read_text())["rtl_modules"]
        if name != "rtl/pcie_axi_master.v"
    ]
    dest = out.parent / "pcie_bridge_check.vvp"
    process = subprocess.run(
        ["iverilog", "-g2012", "-s", "pcie_axi_master", "-o", str(dest),
         *map(str, files)],
        capture_output=True, text=True, check=False,
    )
    detail = process.stdout + process.stderr
    if process.returncode or re.search(r"\b(?:warning|error)\s*:", detail, re.I):
        raise RuntimeError("PCIe RTL compile diagnostic gate FAILED:\n" + detail[-7000:])
    return out


if __name__ == "__main__":
    print("PCIe width/diagnostic gate PASS:", assert_iverilog_clean())
