#!/usr/bin/env python3
"""Cross-check genuine over-link PCIe BAR0 traffic, not a modeled success.

The fast TLP-only full-chip regression still owns canonical AXI/NoC evidence.
Here we compare three INDEPENDENT original-link observations: RC transmit,
endpoint internal received packet, and accepted endpoint AXI-Lite WDATA;
we also inspect actual completion TLP bytes and the RC receive callback.
No data transformation, hidden endian auto-repair or inferred completions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

BEGIN = re.compile(r"^PCIE_RC_CFG_BEGIN: .*?aperture=([0-9]+) base=([0-9a-fA-F]{8})$")
TX = re.compile(r"^PCIE_RC_CFG_TX: Cfg(Wr|Rd)0 addr=([0-9a-fA-F]{3})(?: data=([0-9a-fA-F]{8}))? tag=([0-9]+)$")
EP_RX = re.compile(r"^PCIE_EP_INTERNAL_CFG_RX_BEAT: data=([0-9a-fA-F]{8}) keep=([0-9a-fA-F]+) last=([01]) at ([0-9]+)$")
AXI = re.compile(r"^PCIE_EP_BAR_CFG_AXI: AW=([01]) W=([01]) AR=([01]) awaddr=([0-9a-fA-F]+) araddr=([0-9a-fA-F]+) wdata=([0-9a-fA-F]{8})\b")
EP_CPL = re.compile(r"^PCIE_EP_INTERNAL_CFG_CPL_TX_BEAT: data=([0-9a-fA-F]{8}) keep=([0-9a-fA-F]+) last=([01]) at ([0-9]+)$")
RC_CPL = re.compile(r"^PCIE_RC_CFG_RX_CPL: tag=([0-9]+) status=([0-9]+) type=([0-9a-fA-F]{2}) bytes=([0-9]+) timestamp=([0-9]+)$")
RC_RESULT = re.compile(r"^PCIE_RC_CFG_RESULT: tag=([0-9]+) seen=([01]) status=([0-9]+) bytes=([0-9]+) ok=([01])$")
# A genuinely later posted Memory Write is a DIFFERENT packet, not
# an extra final beat of the last ConfigRd0. Bound packet provenance by
# the original host's next TLP launch, not end-of-simulation.
HOST_MWR = re.compile(r"^PCIE_RC_BAR_MWR_TX: action=[A-Za-z0-9_.-]+ addr=[0-9a-fA-F]{8} data=[0-9a-fA-F]{8} plan=[0-9a-fA-F]{64}$")


def check(text: str) -> dict:
    """Fail closed on a missing/swapped TLP payload at ANY observed boundary."""
    lines = [s.strip() for s in text.splitlines()]
    issues: list[str] = []
    begins = [m for s in lines if (m := BEGIN.fullmatch(s))]
    if len(begins) != 1:
        issues.append(f"expected one host BAR0 scenario, saw {len(begins)}")
        aperture, base = 0, 0
    else:
        aperture, base = int(begins[0][1]), int(begins[0][2], 16)
        if aperture < 4096 or aperture & (aperture - 1) or base & (aperture - 1):
            issues.append("invalid selected BAR aperture/base")
    mask = (~(aperture - 1)) & 0xfffffff0 if aperture else 0
    expected = [
        ("Wr", 0x010, 0xffffffff, None),
        ("Rd", 0x010, None, mask),
        ("Wr", 0x010, base, None),
        ("Rd", 0x010, None, base),
        ("Wr", 0x004, 0x00000002, None),
        ("Rd", 0x004, None, 0x00000002),
    ]
    positions = [(i,m) for i,s in enumerate(lines) if (m:=TX.fullmatch(s))]
    memory_launches = [i for i,s in enumerate(lines) if HOST_MWR.fullmatch(s)]
    # Configuration must complete before the original RC issues BAR MWr.
    final_result = [i for i,s in enumerate(lines) if
                    (m := RC_RESULT.fullmatch(s)) and int(m[1]) == 5]
    if memory_launches and (len(final_result) != 1 or
                           memory_launches[0] <= final_result[0] or
                           len(memory_launches) != 1):
        issues.append("BAR Memory Write launched before final host Config completion or repeated")
    if len(positions) != len(expected):
        issues.append(f"expected six real host configuration TLPs, got {len(positions)}")
    records: list[dict] = []
    seen_tags: set[int] = set()
    for index, (start, match) in enumerate(positions):
        op, addr, word, tag = match.groups()
        addr = int(addr, 16)
        val = int(word,16) if word is not None else None
        tag = int(tag)
        stop = positions[index+1][0] if index+1 < len(positions) else len(lines)
        # Do not attribute subsequent *independent* MemWr32 RX beats to
        # CfgRd0 tag 5. Still fail closed if the memory transaction starts
        # before its actual host CplD was received and checked.
        if memory_launches:
            later_memory = [n for n in memory_launches if n > start]
            if later_memory:
                stop = min(stop, later_memory[0])
        window=lines[start:stop]
        row={"index":index, "kind":"Cfg"+op+"0", "address":hex(addr),
             "host_tag":tag, "host_value":hex(val) if val is not None else None}
        records.append(row)
        if tag in seen_tags:
            issues.append(f"duplicated host tag {tag}")
        seen_tags.add(tag)
        if index >= len(expected):
            issues.append(f"unexpected host request tag {tag}")
            continue
        xop, xaddr, xword, xread = expected[index]
        if (op,addr,val)!=(xop,xaddr,xword):
            issues.append(f"request {index} host values mismatch: {(op,addr,val)} != {(xop,xaddr,xword)}")
        # Timestamp only *accepted endpoint pins* in the original RTL
        # clock domain. The root complex callback's native timestamp has
        # a different timebase, and is retained separately without guessing.
        rx_beats=[(int(m[1],16),int(m[2],16),int(m[4]))
                  for s in window if (m:=EP_RX.fullmatch(s))]
        ep_words=[(int(m[1],16),int(m[2],16)) for s in window
                  if (m:=EP_RX.fullmatch(s)) and m[3]=="1"]
        row["endpoint_first_rx_ps"]=rx_beats[0][2] if rx_beats else None
        if len(ep_words)!=1:
            issues.append(f"tag {tag}: expected one genuine endpoint final RX beat, got {len(ep_words)}")
        # AXI-Lite AW/W/AR may handshake independently: compare only
        # accepted valid&&ready, never use attempted but unaccepted data.
        ax=[(int(m[1]),int(m[2]),int(m[3]),int(m[4],16),
             int(m[5],16),int(m[6],16)) for s in window if (m:=AXI.search(s))]
        aw=[x for x in ax if x[0]]
        wd=[x for x in ax if x[1]]
        ar=[x for x in ax if x[2]]
        rx_cpl=[m for s in window if (m:=RC_CPL.fullmatch(s))]
        rx_result=[m for s in window if (m:=RC_RESULT.fullmatch(s))]
        cpl_beats=[(int(m[1],16),int(m[2],16),int(m[4]))
                   for s in window if (m:=EP_CPL.fullmatch(s))]
        ep_cpl=[(int(m[1],16),int(m[2],16)) for s in window
                if (m:=EP_CPL.fullmatch(s)) and m[3]=="1"]
        row["endpoint_last_cpl_ps"]=cpl_beats[-1][2] if cpl_beats else None
        row["root_complex_cpl_timestamp_native"]=(
            int(rx_cpl[0][5]) if len(rx_cpl)==1 else None)
        if (row["endpoint_first_rx_ps"] is None
                or row["endpoint_last_cpl_ps"] is None
                or row["endpoint_last_cpl_ps"] < row["endpoint_first_rx_ps"]):
            issues.append(f"tag {tag}: invalid source-observed completion timing")
        if len(rx_cpl)!=1 or len(rx_result)!=1:
            issues.append(f"tag {tag}: missing/duplicate host completion or result")
        else:
            cpl, result = rx_cpl[0], rx_result[0]
            want_type="0a" if op=="Wr" else "4a"
            want_bytes=0 if op=="Wr" else 4
            if (int(cpl[1]),int(cpl[2]),cpl[3].lower(),int(cpl[4])) != (
                tag,0,want_type,want_bytes):
                issues.append(f"tag {tag}: wrong over-link Cpl status/type/count")
            if (int(result[1]),int(result[2]),int(result[3]),int(result[4]),int(result[5])) != (
                tag,1,0,want_bytes,1):
                issues.append(f"tag {tag}: RC reported invalid returned completion")
        if op=="Wr":
            if len(aw)!=1 or len(wd)!=1 or ar:
                issues.append(f"tag {tag}: expected one accepted AW and W, no AR")
            elif aw[0][3] != addr or wd[0][5] != val:
                issues.append(f"tag {tag}: accepted AXI address/data mismatch")
            if len(ep_words)==1 and ep_words[0]!=(val,0xf):
                issues.append(f"tag {tag}: received TLP payload differs from original host bytes")
            if len(ep_cpl)!=1:
                issues.append(f"tag {tag}: expected actual endpoint Cpl (no data)")
            row["endpoint_received_payload"]=hex(ep_words[0][0]) if len(ep_words)==1 else None
            row["axi_accepted_wdata"]=hex(wd[0][5]) if len(wd)==1 else None
            row["actual_completion_kind"]="Cpl"
        else:
            if aw or wd or len(ar)!=1 or ar[0][4]!=addr:
                issues.append(f"tag {tag}: expected one accepted AR, no AW/W")
            if len(ep_cpl)!=1 or ep_cpl[0]!=(xread,0xf):
                issues.append(f"tag {tag}: endpoint CplD data mismatch (byte order or register semantics)")
            row["endpoint_cpld_payload"]=hex(ep_cpl[0][0]) if len(ep_cpl)==1 else None
            row["actual_completion_kind"]="CplD"
        row["host_completion_observed"]=(len(rx_cpl)==1 and len(rx_result)==1)
    for phrase in (
        f"PCIE_RC_CFG_PROBE_OK: BAR0 mask={mask:08x}",
        f"PCIE_RC_CFG_BAR_ASSIGNED: BAR0 bus={base:08x}",
        "PCIE_RC_CFG_MSE_ENABLED: command=00000002 completions=6",
        "action=enumerate_bar0 stage=driver_done",
    ):
        if not any(phrase in s for s in lines):
            issues.append(f"missing host-confirmed milestone: {phrase}")
    if any(s.startswith(("PCIE_RC_CFG_FAIL:","PCIE_SCN_DRIVER_FAIL:")) for s in lines):
        issues.append("original host reported configuration failure")
    return {
        "schema_version":1, "kind":"pcie_isolated_bar0_provenance",
        "qualified_over_link_bar0":not issues, "issues":issues,
        "selected_aperture_bytes":aperture, "selected_host_bus_base":hex(base),
        "expected_bar0_mask":hex(mask), "transactions":records,
        "evidence":["host_original_cfg_tx","endpoint_internal_rx_tlp",
                    "endpoint_accepted_axi_lite","endpoint_internal_cpl",
                    "root_complex_original_cpl_callback"],
        "noc_axi_transfer":"unmeasured","memory_bytes":"unmeasured",
        "note":"Source-selected isolated real PCIe BAR0 config evidence only. No NoC memory PASS."
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("log",type=Path)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if not args.log.is_file():
        p.error("original simulator transcript missing")
    info=check(args.log.read_text(errors="replace"))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"pcie-bar0-evidence.json").write_text(json.dumps(info,indent=2)+"\n")
    print(f"{'PASS' if info['qualified_over_link_bar0'] else 'FAIL'} over-link BAR0 provenance: "
          f"{len(info['transactions'])} requests; {info['issues']}")
    return 0 if info["qualified_over_link_bar0"] else 1


if __name__=="__main__":
    sys.exit(main())
