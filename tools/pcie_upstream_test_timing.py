#!/usr/bin/env python3
"""Pin-qualified *standalone test-only* OpenPCIe Cocotb timing adapter.

The normal RTL default stays SIM_FAST_LINK=0. This alters ONLY the ignored
upstream FuseSoC self-test checkout; cross-provider tests get their own
explicit -GSIM_FORCE_FAST_LTSSM=1 already. Do not represent this as a
production IP patch, force state, or qualify host ↔ endpoint L0.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

SOURCES = {
    "pcie_phy.core": "283a8e4156f18368115037532dc19490a73d97bc",
    "verif/tests/test_pcie_core.py": "9592f1377c8ca42cde1dde08aa249190a4467593",
}
CORE_BEFORE = """  sim:
    flow: sim
    flow_options:
      tool : verilator
      cocotb_module : test_pcie_core
      timescale: 1ns/1ns
      verilator_options:
        - --trace-fst --trace-structs
        - -j 4
        - waiver.vlt
"""
CORE_AFTER = CORE_BEFORE.replace(
    "        - waiver.vlt\n",
    "        - waiver.vlt\n        - -GSIM_FAST_LINK=1\n")
TEST_BEFORE = "await with_timeout(self.test_all.start(),25000,'ns')"
TEST_AFTER = "await with_timeout(self.test_all.start(),250000,'ns')"


def replace_once(text: str, before: str, after: str, label: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"{label}: pinned upstream self-test source changed")
    return text.replace(before, after, 1)


def patched(path: str, source: str) -> str:
    if path == "pcie_phy.core":
        return replace_once(source,CORE_BEFORE,CORE_AFTER,path)
    if path == "verif/tests/test_pcie_core.py":
        return replace_once(source,TEST_BEFORE,TEST_AFTER,path)
    raise ValueError(f"unknown timing-source path {path}")


def apply(root:Path) -> None:
    for rel, expected in SOURCES.items():
        path=root/rel
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"original upstream timing input missing: {rel}")
        actual=subprocess.run(["git","-C",str(root),"hash-object",rel],
                              check=True,capture_output=True,text=True).stdout.strip()
        if actual!=expected:
            raise ValueError(f"original upstream {rel} drift: {actual} != {expected}")
        content=patched(rel,path.read_text())
        path.write_text(content)
        print(f"OPENPCIE_SELFTEST_TIMING: pinned {rel}: "
              "Gen1 LTSSM 512x acceleration, 250us explicit test timeout")
    print("OPENPCIE_SELFTEST_TIMING: TEST-ONLY; not production or dual-sided L0 evidence")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkout",required=True,type=Path)
    a=p.parse_args()
    apply(a.checkout)
