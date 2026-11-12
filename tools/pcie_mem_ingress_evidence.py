#!/usr/bin/env python3
"""Real pcievhost MemWr -> original OpenPCIe internal TLP receive provenance.

This is intentionally only a posted-TLP INGRESS proof. No AXI, NoC,
SRAM, completion or full-chip boot acceptance may be inferred here.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

from tools.pcie_bar0_evidence import check as check_config

HOST = re.compile(
    r"^PCIE_RC_BAR_MWR_TX: action=write_bar0 addr=([0-9a-fA-F]{8}) "
    r"data=([0-9a-fA-F]{8}) plan=([0-9a-fA-F]{64})$")
RC_DONE = re.compile(
    r"^PCIE_SCN_DRIVER: plan=([0-9a-fA-F]{64}) action=write_bar0 stage=driver_done$")
EP = re.compile(
    r"^PCIE_EP_INTERNAL_CFG_RX_BEAT: data=([0-9a-fA-F]{8}) "
    r"keep=([0-9a-fA-F]+) last=([01]) at ([0-9]+)$")
BACKPRESSURE = re.compile(
    r"^PCIE_EP_MEM_TLP_BACKPRESSURE: original endpoint valid ready=0 "
    r"data=([0-9a-fA-F]{8}) keep=([0-9a-fA-F]+) last=([01]) at ([0-9]+)$")


def bswap32(word: int) -> int:
    return int.from_bytes(word.to_bytes(4, "big"), "little")


def check(transcript: str) -> dict:
    lines = [line.strip() for line in transcript.splitlines()]
    issues = []
    bar = check_config(transcript)
    if not bar["qualified_over_link_bar0"]:
        issues.append("prior over-link ConfigRd/ConfigWr BAR evidence invalid")
    host = [(i, m) for i, line in enumerate(lines)
            if (m := HOST.fullmatch(line))]
    done = [(i, m) for i, line in enumerate(lines)
            if (m := RC_DONE.fullmatch(line))]
    backs = [(i, m) for i, line in enumerate(lines)
             if (m := BACKPRESSURE.fullmatch(line))]
    addr = data = None
    plan_sha = None
    captured = []
    if len(host) != 1:
        issues.append(f"expected exactly one original host posted MemWr, got {len(host)}")
    else:
        index, m = host[0]
        addr, data, plan_sha = int(m[1],16), int(m[2],16), m[3]
        end = done[0][0] if len(done)==1 and done[0][0] > index else len(lines)
        captured = [(i,int(g[1],16),int(g[2],16),int(g[3]),int(g[4]))
                    for i,line in enumerate(lines)
                    if index < i < end and (g := EP.fullmatch(line))]
        if len(done) != 1 or done[0][0] <= index or done[0][1][1] != plan_sha:
            issues.append("missing original host posted MemWr driver_done")
        if len(captured) != 4:
            issues.append(f"expected four actual endpoint TLP RX words, got {len(captured)}")
        else:
            words = [row[1] for row in captured]
            if [row[2] for row in captured] != [15]*4 or (
                    [row[3] for row in captured] != [0,0,0,1]):
                issues.append("original endpoint TLP keep/last framing mismatch")
            if bswap32(words[0]) != 0x40000001:
                issues.append("MemWr32 TLP type/one-DWORD length mismatch")
            if (bswap32(words[1]) & 0xf) != 0xf:
                issues.append("MemWr32 first byte-enable differs from full DWORD")
            if bswap32(words[2]) != addr:
                issues.append("actual TLP address differs from original host PCI bus address")
            # This pinned endpoint's internal RX stream preserves the original
            # payload word; do not compensate by swapping bytes in the checker.
            if words[3] != data:
                issues.append("actual endpoint received payload differs from host bytes")
    if len(backs) != 1:
        issues.append(f"expected one observed nonconfig TLP under ready=0, got {len(backs)}")
    elif len(captured) == 4:
        index, b = backs[0]
        if len(done) != 1 or index <= captured[0][0] or index >= done[0][0] or (
                int(b[1],16),int(b[2],16),int(b[3])) != (captured[0][1],15,0):
            issues.append("backpressured nonconfig first beat differs from actual inbound TLP")
    if any(x.startswith(("PCIE_RC_CFG_FAIL:", "PCIE_SCN_DRIVER_FAIL:"))
           for x in lines):
        issues.append("independent host reported a fatal configuration/driver error")
    return {
        "schema_version":1,
        "kind":"pcie_original_host_memwrite_ingress",
        "qualified_original_memwrite_ingress":not issues,
        "issues":issues,
        "original_host_bus_address":f"0x{addr:08x}" if addr is not None else None,
        "original_host_word":f"0x{data:08x}" if data is not None else None,
        "original_endpoint_tlp_rx_words":[f"0x{x[1]:08x}" for x in captured],
        "endpoint_nonconfig_ready":0,
        "axi_accepted":False,
        "noc_sram_bytes":"unmeasured",
        "pci_completion":"not_applicable_posted_write",
        "cpu_cold_boot":"unmeasured",
        "note":"Original host PCIe MemWr received by endpoint, held under backpressure. Never claim memory acceptance.",
    }


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log",type=Path)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    if not args.log.is_file():
        ap.error("original cross-provider transcript required")
    info=check(args.log.read_text(errors="replace"))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"pcie-mem-ingress-evidence.json").write_text(
        json.dumps(info,indent=2)+"\n")
    print(("PASS" if info["qualified_original_memwrite_ingress"] else "FAIL")+
          " original PCIe posted MemWr ingress: "+str(info["issues"]))
    return 0 if info["qualified_original_memwrite_ingress"] else 1


if __name__=="__main__":
    raise SystemExit(main())
