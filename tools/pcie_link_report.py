#!/usr/bin/env python3
"""Render *observed* PCIe LTSSM evidence, never a substitute for SoC reports.

The digital-link Verilator smoke has independent host/endpoint models and a
common physical PIPE link. It is NOT a full-chip AXI/TLP/byte scoreboard.
The existing tools/regress.py reports remain the authority for SoC traffic.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import re
import sys

STATE = re.compile(r"^PCIE_EP_STATE: ([0-9a-fA-F]+) -> ([0-9a-fA-F]+) at ([0-9]+)$")
BAR = re.compile(r"^PCIE_DEVICE_PRELINK: committed BAR0 size=([0-9a-fA-F]+) target=([0-9a-fA-F]+) mask=([0-9a-fA-F]+)$")
FAST = re.compile(r"^PCIE_EP_SIM_FAST_LTSSM: ENABLED timer_divider=([0-9]+) min_tx_ts1=([0-9]+) ")
HOST = "PCIE_HOST_L0: original InitLink(1) returned"
ENDPOINT = "PCIE_ENDPOINT_L0: original endpoint asserts link_up"
DETECT_REQ = "PCIE_TRACE: receiver-detect request"
DETECT_RESPONSE = "PCIE_TRACE: PHY receiver present"
PIPE = "PCIE_PIPE_WIDTH_MATCH: RC 16-bit and EP 16-bit PIPE @125MHz"
SELECTED = "PCIE_SCN_DRIVER: plan="
DRIVER_DONE = "stage=driver_done"
PRELINK = "PCIE_DEVICE_PRELINK: LTSSM enable released after BAR commit"


def summarize(text: str) -> dict:
    """Preserve exact observed log events. Never synthesize missing protocol."""
    events: list[dict] = []
    states: list[dict] = []
    milestones = {}
    duplicate = []
    plan_hash = None
    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        match = STATE.fullmatch(line)
        if match:
            src, dst, ps = match.groups()
            row = {"line": line_num, "kind": "endpoint_ltssm", "from": src,
                   "to": dst, "time_ps": int(ps)}
            states.append(row)
            events.append(row)
        match = BAR.fullmatch(line)
        if match:
            row = {"line":line_num,"kind":"device_prelink_bar_commit",
                   "bar_size_bytes":int(match.group(1),16),
                   "local_target":hex(int(match.group(2),16)),
                   "mask":hex(int(match.group(3),16)), "time_ps":None}
            events.append(row)
            if "bar_commit" in milestones: duplicate.append("bar_commit")
            milestones["bar_commit"] = line_num
        for key, prefix in (
            ("prelink_release", PRELINK),
            ("receiver_detect", DETECT_REQ),
            ("phy_receiver_present", DETECT_RESPONSE),
            ("pipe_width", PIPE),
            ("host_l0", HOST),
            ("endpoint_l0", ENDPOINT),
        ):
            if line.startswith(prefix):
                if key in milestones: duplicate.append(key)
                milestones[key] = line_num
                events.append({"line":line_num,"kind":key,"time_ps":None})
        m = FAST.match(line)
        if m:
            if "fast_parameters" in milestones: duplicate.append("fast_parameters")
            milestones["fast_parameters"] = line_num
            events.append({"line":line_num,"kind":"sim_timer_mode",
                           "divider":int(m.group(1)),"minimum_transmitted_ts1":int(m.group(2)),
                           "time_ps":None})
        if line.startswith(SELECTED) and "stage=issued" in line:
            m = re.search(r"plan=([a-f0-9]{64}) action=train_link stage=issued",line)
            if m:
                if plan_hash is not None: duplicate.append("driver_issued")
                plan_hash = m.group(1)
                milestones["driver_issued"] = line_num
        if line.startswith(SELECTED) and DRIVER_DONE in line:
            m = re.search(r"plan=([a-f0-9]{64}) action=train_link stage=driver_done",line)
            if m:
                if "driver_done" in milestones: duplicate.append("driver_done")
                milestones["driver_done"] = line_num
                if plan_hash is not None and m.group(1)!=plan_hash: duplicate.append("plan_sha_mismatch")
    required = ("bar_commit", "prelink_release","receiver_detect",
                "phy_receiver_present","pipe_width","host_l0",
                "endpoint_l0","fast_parameters","driver_issued","driver_done")
    issues = [f"missing observed {key}" for key in required if key not in milestones]
    issues += [f"duplicate or mismatched {item}" for item in sorted(set(duplicate))]
    for a,b in (("bar_commit","prelink_release"),("prelink_release","receiver_detect"),
                ("receiver_detect","phy_receiver_present"),
                ("phy_receiver_present","endpoint_l0"),
                ("driver_issued","driver_done")):
        if a in milestones and b in milestones and milestones[a]>=milestones[b]:
            issues.append(f"incorrect event order {a} -> {b}")
    if not states:
        issues.append("no actual endpoint LTSSM state trace")
    elif not any(int(row["to"],16)==0x22 for row in states):
        issues.append("no observed endpoint Polling.Active state")
    if states and not any(int(row["to"],16)==0x23 for row in states):
        issues.append("no observed endpoint Configuration state")
    if any(e.get("kind")=="sim_timer_mode" and
           (e["divider"]!=512 or e["minimum_transmitted_ts1"]!=16) for e in events):
        issues.append("unexpected simulation timer acceleration")
    if ("host_l0" in milestones and "endpoint_l0" in milestones and
            (milestones["host_l0"]<=milestones["receiver_detect"]
             if "receiver_detect" in milestones else True)):
        issues.append("host L0 before receiver detection")
    if "endpoint_l0" in milestones and states and milestones["endpoint_l0"]<=states[-1]["line"]:
        issues.append("endpoint L0 trace before final observed state transition")
    return {
        "schema_version":1,"kind":"pcie_isolated_link_diagnostic",
        "source":"original_verilator_transcript",
        "scenario_plan_sha256":plan_hash,
        "qualified_digital_link_l0":not issues,
        "issues":issues,"events":events,
        "observed_endpoint_state_transitions":len(states),
        "host_l0_observed":"host_l0" in milestones,
        "endpoint_l0_observed":"endpoint_l0" in milestones,
        "capabilities":{
            "ltssm_digital_link":"observed" if not issues else "not_qualified",
            "host_bar_enumeration":"unmeasured",
            "pcie_tlp_completion":"unmeasured",
            "noc_axi_transfer":"unmeasured",
            "memory_bytes":"unmeasured",
            "analog_phy":"not_applicable",
        },
        "note":"Diagnostics only: no independently checked host BAR TLPs, AXI NoC transactions or bytes.",
    }


def render(data:dict) -> str:
    rows=[]
    for e in data["events"]:
        t=e.get("time_ps")
        label=e["kind"]
        if label=="endpoint_ltssm":
            label+=f' {e["from"]} -> {e["to"]}'
        elif label=="sim_timer_mode":
            label+=f' {e["divider"]}x / {e["minimum_transmitted_ts1"]} TS1'
        elif label=="device_prelink_bar_commit":
            label+=f' {e["bar_size_bytes"]} bytes -> {e["local_target"]}'
        rows.append(f"<tr><td>{e['line']}</td><td>{escape(label)}</td>"
                    f"<td>{escape(str(t) if t is not None else 'unmeasured')}</td></tr>")
    qual="L0 OBSERVED" if data["qualified_digital_link_l0"] else "UNQUALIFIED"
    issues="".join(f"<li>{escape(s)}</li>" for s in data["issues"])
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PCIe digital-link diagnostic</title>
<style>body{background:#10151e;color:#e9ecf0;font:15px system-ui;max-width:900px;margin:auto;padding:1rem}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.55rem;border-bottom:1px solid #384453}
.wrap{overflow-x:auto}a{color:#91caff}small{color:#a9b7c7}</style>
<h1>PCIe Gen1 x1 — isolated digital-link diagnostic</h1>""" + (
    f"<p><strong>{qual}</strong></p><p>Host L0: {data['host_l0_observed']}; "
    f"endpoint L0: {data['endpoint_l0_observed']}</p>"
    "<p><small>Original simulator transcript only. Timestamp 'unmeasured' means "
    "no simulator timestamp was emitted for that event. No invented timings.</small></p>"
    "<div class='wrap'><table><thead><tr><th>Log line</th><th>Observed event</th><th>Time (ps)</th>"
    "</tr></thead><tbody>"+"".join(rows)+"</tbody></table></div>"
    "<h2>Unqualified interfaces</h2><p>Host BAR enumeration, TLP completions, "
    "NoC AXI transfer, memory bytes, and physical SerDes are NOT qualified by this test.</p>"
    "<h2>Issues</h2><ul>"+(issues or "<li>None for isolated L0</li>")+"</ul>"
    "<p>Use the existing tools/regress.py / Test Runs hub for full-chip TLP and AXI results. "
    "The old fast bridge mode remains separate and unchanged.</p></html>")


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("log",type=Path)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    if not args.log.is_file():
        p.error("simulation log not found")
    data=summarize(args.log.read_text(errors="replace"))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"pcie-link-evidence.json").write_text(json.dumps(data,indent=2)+"\n")
    (args.out/"pcie-link-report.html").write_text(render(data))
    print(f"{'PASS' if data['qualified_digital_link_l0'] else 'FAIL'} isolated PCIe L0 diagnostic: "
          f"{len(data['events'])} observations; {data['issues']}")
    return 0 if data["qualified_digital_link_l0"] else 1


if __name__=="__main__":
    sys.exit(main())
