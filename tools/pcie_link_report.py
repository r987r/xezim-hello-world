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
# These strings are emitted by the ORIGINAL pinned pcievhost src/ltssm.c,
# not inferred from the endpoint LTSSM (nor from an imagined RC state).
HOST_STAGE = re.compile(r"^---> (.+?) \(node ([0-9]+)\)$")
HOST_LANES = re.compile(r"^---> Active lanes = 0x([0-9a-fA-F]{4}) \(node 0\)$")
PIPE_SAMPLE = re.compile(
    r"^PCIE_PIPE_(RC_TO_EP|EP_TO_RC): data=([0-9a-fA-F]+) "
    r"k=([0-9a-fA-F]+) idle=([01]) valid=([01]) at ([0-9]+)$")
HOST_STAGE_ORDER = (
    "Detect Quiet", "Detect Active", "Polling Active", "Polling Config",
    "Configuration Start", "Configuration Linkwidth Accept",
    "Configuration Lanenum Wait", "Configuration Lanenum Accept",
    "Configuration Complete", "Configuration Idle",
    "Configuration exit to L0",
)
EP_STATE_NAMES = {
    0x000: "Idle / reset", 0x041: "Detect.Quiet", 0x061: "Detect.Active",
    0x002: "Polling", 0x022: "Polling.Active",
    0x042: "Polling.Configuration",
    0x023: "Configuration.Linkwidth.Start",
    0x043: "Configuration.Linkwidth.Accept",
    0x083: "Configuration.Lanenum.Wait",
    0x063: "Configuration.Lanenum.Accept",
    0x0a3: "Configuration.Complete", 0x0e3: "Configuration.Idle",
    0x005: "L0",
}

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
    host_stages: list[dict] = []
    pipe_samples: list[dict] = []
    milestones = {}
    duplicate = []
    plan_hash = None
    for line_num, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        match = STATE.fullmatch(line)
        if match:
            src, dst, ps = match.groups()
            row = {"line": line_num, "kind": "endpoint_ltssm", "from": src,
                   "to": dst, "time_ps": int(ps),
                   "stage": EP_STATE_NAMES.get(int(dst, 16) & 0xfffff,
                                                 f"Unknown LTSSM 0x{int(dst,16):05x}")}
            states.append(row)
            events.append(row)
            # Pinned OpenPCIe ST_L0 is 0x005. link_up_o may assert earlier
            # during Configuration.Idle 0x0e3 and is not proof by itself.
            if int(dst,16) == 0x005:
                if "endpoint_state_l0" in milestones:
                    duplicate.append("endpoint_state_l0")
                milestones["endpoint_state_l0"] = line_num
        host_state = HOST_STAGE.fullmatch(line)
        if host_state and int(host_state.group(2)) == 0:
            label = host_state.group(1)
            if label in HOST_STAGE_ORDER:
                row = {"line":line_num, "kind":"host_ltssm",
                       "stage":label, "time_ps":None,
                       "provenance":"original_pcievhost_ltssm_c_vprint"}
                host_stages.append(row)
                events.append(row)
        active = HOST_LANES.fullmatch(line)
        if active:
            events.append({"line":line_num, "kind":"host_active_lanes",
                           "lane_mask":int(active.group(1),16),
                           "time_ps":None})
        pipe = PIPE_SAMPLE.fullmatch(line)
        if pipe:
            direction, word, kflags, idle, valid, ps = pipe.groups()
            pipe_samples.append({
                "line":line_num, "direction":direction, "time_ps":int(ps),
                "data":f"0x{int(word,16):04x}", "k":f"0x{int(kflags,16):x}",
                "idle":bool(int(idle)), "valid":bool(int(valid))
            })
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
                "endpoint_l0","endpoint_state_l0","fast_parameters",
                "driver_issued","driver_done")
    issues = [f"missing observed {key}" for key in required if key not in milestones]
    issues += [f"duplicate or mismatched {item}" for item in sorted(set(duplicate))]
    for a,b in (("bar_commit","prelink_release"),("prelink_release","receiver_detect"),
                ("receiver_detect","phy_receiver_present"),
                ("phy_receiver_present","endpoint_l0"),
                ("driver_issued","driver_done")):
        if a in milestones and b in milestones and milestones[a]>=milestones[b]:
            issues.append(f"incorrect event order {a} -> {b}")
    # The host's source-observed LTSSM stages are visible separately from
    # the RTL endpoint states. The original VPrint does NOT emit simulator
    # timestamps, so they must never be plotted as if timed PIPE samples.
    stage_positions = {stage: [x["line"] for x in host_stages if x["stage"] == stage]
                       for stage in HOST_STAGE_ORDER}
    for stage, locations in stage_positions.items():
        if not locations:
            issues.append(f"missing original host LTSSM stage: {stage}")
    if all(stage_positions.values()):
        positions = [stage_positions[stage][0] for stage in HOST_STAGE_ORDER]
        if positions != sorted(positions) or len(set(positions)) != len(positions):
            issues.append("original host LTSSM stages are out of order")
        if "host_l0" in milestones and positions[-1] >= milestones["host_l0"]:
            issues.append("host L0 claim preceded original Configuration exit to L0")
    lanes = [e for e in events if e["kind"] == "host_active_lanes"]
    if len(lanes) != 1 or lanes[0]["lane_mask"] != 1:
        issues.append("original host did not report exactly one selected x1 lane")
    for direction in ("RC_TO_EP", "EP_TO_RC"):
        samples = [p for p in pipe_samples if p["direction"] == direction]
        if not samples or not any(s["valid"] and not s["idle"] for s in samples):
            issues.append(f"missing actual valid PIPE traffic in {direction} direction")
        if any(p["time_ps"] < 0 for p in samples):
            issues.append(f"invalid negative PIPE timestamp for {direction}")
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
    # The final 0x0e3 -> 0x005 transition is precisely what we want.
    # A subsequent exit into Recovery or Detect must not be hidden.
    if states and int(states[-1]["to"],16) != 0x005:
        issues.append("endpoint not in actual LTSSM ST_L0 (0x005) at finish")
    if ("endpoint_state_l0" in milestones and
            "phy_receiver_present" in milestones and
            milestones["endpoint_state_l0"] <= milestones["phy_receiver_present"]):
        issues.append("endpoint LTSSM ST_L0 observed before receiver detection")
    return {
        "schema_version":1,"kind":"pcie_isolated_link_diagnostic",
        "source":"original_verilator_transcript",
        "scenario_plan_sha256":plan_hash,
        "qualified_digital_link_l0":not issues,
        "issues":issues,"events":events,
        "observed_endpoint_state_transitions":len(states),
        "observed_host_ltssm_stages":len(host_stages),
        "host_ltssm_stage_trace_observed":len(host_stages)>0,
        "host_stage_clock":"not_emitted_by_upstream_model",
        "pipe_samples":pipe_samples,
        "pipe_traffic_samples":{"host_to_device":sum(p["direction"]=="RC_TO_EP" for p in pipe_samples),
                                "device_to_host":sum(p["direction"]=="EP_TO_RC" for p in pipe_samples)},
        "host_l0_observed":"host_l0" in milestones,
        "endpoint_l0_observed":"endpoint_l0" in milestones,
        "endpoint_ltssm_l0_observed":"endpoint_state_l0" in milestones,
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
    """Two observed, independent LTSSM lanes; no invented host timestamps."""
    rows=[]
    host_rows=[]
    device_rows=[]
    for e in data["events"]:
        t=e.get("time_ps")
        kind=e["kind"]
        label=kind
        if kind=="endpoint_ltssm":
            label=f'Endpoint: {e["stage"]} (0x{int(e["to"],16):03x})'
            device_rows.append(
                f'<tr><td>{e["line"]}</td><td>{escape(e["stage"])}</td>'
                f'<td>{e["time_ps"]/1000:.3f}</td></tr>')
        elif kind=="host_ltssm":
            label="Root Complex: "+e["stage"]
            host_rows.append(
                f'<tr><td>{e["line"]}</td><td>{escape(e["stage"])}</td>'
                '<td>Not emitted</td></tr>')
        elif kind=="host_active_lanes":
            label=f'Root Complex: active lanes 0x{e["lane_mask"]:04x}'
        elif kind=="sim_timer_mode":
            label+=f' {e["divider"]}x / {e["minimum_transmitted_ts1"]} TS1'
        elif kind=="device_prelink_bar_commit":
            label+=f' {e["bar_size_bytes"]} bytes -> {e["local_target"]}'
        rows.append(
            f"<tr><td>{e['line']}</td><td>{escape(label)}</td>"
            f"<td>{escape(str(t) if t is not None else 'unmeasured')}</td></tr>")
    qual="L0 OBSERVED" if data["qualified_digital_link_l0"] else "UNQUALIFIED"
    issues="".join(f"<li>{escape(v)}</li>" for v in data["issues"])
    pipe=data.get("pipe_samples",[])
    directions=(("RC_TO_EP","Host → Device"),("EP_TO_RC","Device → Host"))
    stream=[]
    for key,title in directions:
        samples=[x for x in pipe if x["direction"]==key]
        stream.append(
            '<section class="card"><h3>'+escape(title)+
            f'</h3><strong>{len(samples)} observed PIPE samples</strong>'
            '<div class="wrap"><table><thead><tr><th>Sim ns</th>'
            '<th>Data</th><th>K flags</th><th>Valid</th><th>Idle</th>'
            '</tr></thead><tbody>'+
            "".join(
                f'<tr><td>{x["time_ps"]/1000:.3f}</td>'
                f'<td>{escape(x["data"])}</td><td>{escape(x["k"])}</td>'
                f'<td>{x["valid"]}</td><td>{x["idle"]}</td></tr>'
                for x in samples)+
            '</tbody></table></div></section>')
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PCIe host and device LTSSM link-training evidence</title>
<style>
body{background:#10151e;color:#e9ecf0;font:15px system-ui;max-width:1150px;margin:auto;padding:1rem}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.55rem;border-bottom:1px solid #384453}
.wrap{overflow-x:auto;max-height:520px}a{color:#91caff}small{color:#a9b7c7}
.lanes{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.card{min-width:0;border:1px solid #384453;border-radius:10px;padding:12px;background:#17212d}
h1{font-size:clamp(1.35rem,3.5vw,2rem)}h2{font-size:1.15rem}
h3{font-size:1rem;margin:.3rem 0 1rem}
.pass{color:#92e1b6}.fail{color:#ffc08c}
@media(max-width:750px){.lanes{grid-template-columns:1fr}body{padding:10px}}
</style>
<h1>PCIe Gen1 x1 — host and device link-training evidence</h1>""" + (
    f'<p class="{("pass" if data["qualified_digital_link_l0"] else "fail")}">'
    f"<strong>{qual}</strong></p>"
    f"<p>Host InitLink returned: <strong>{data['host_l0_observed']}</strong>; "
    f"Endpoint link_up observed: <strong>{data['endpoint_l0_observed']}</strong>; "
    f"Endpoint actual ST_L0: <strong>{data['endpoint_ltssm_l0_observed']}</strong></p>"
    "<p><small>Both participants independently train over physical PIPE. "
    "The host's original C LTSSM prints ordered stages without simulation timestamps; "
    "we show log line rather than inventing host times. Endpoint RTL transitions carry "
    "actual simulator timestamps. link_up may assert before endpoint ST_L0. "
    "No invented timings.</small></p>"
    '<div class="lanes"><section class="card"><h2>Root Complex / host LTSSM</h2>'
    '<p>Original pcievhost src/ltssm.c VPrint (node 0)</p>'
    '<div class="wrap"><table><thead><tr><th>Log line</th><th>Actual stage</th>'
    '<th>Simulator time</th></tr></thead><tbody>'+''.join(host_rows)+
    '</tbody></table></div></section><section class="card"><h2>Endpoint RTL LTSSM</h2>'
    '<p>Original OpenPCIe ltssm_debug_state transitions</p>'
    '<div class="wrap"><table><thead><tr><th>Log line</th><th>Decoded stage</th>'
    '<th>Sim ns</th></tr></thead><tbody>'+''.join(device_rows)+
    '</tbody></table></div></section></div>'
    '<h2>Bidirectional observed PIPE data (not inferred TS packets)</h2>'
    '<p><small>Real sampled 16-bit PHY words on each participant’s PIPE port; '
    'K flags and idle/valid are retained. No TS1/TS2 decoding is fabricated.</small></p>'
    '<div class="lanes">'+''.join(stream)+'</div>'
    '<h2>Full ordered simulator evidence</h2><div class="wrap"><table><thead>'
    '<tr><th>Log line</th><th>Observed event</th><th>Time (ps)</th>'
    '</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    '<h2>Unqualified interfaces</h2><p>Host BAR enumeration, TLP completions, '
    'NoC AXI transfer, memory bytes, and analog SerDes are NOT qualified '
    'by this isolated L0 test.</p><h2>Issues</h2><ul>'+
    (issues or '<li>None for isolated L0</li>')+'</ul>'
    '<p>Existing Test Runs hub remains authoritative for full-chip TLP/AXI results. '
    'The original modeled-TLP fast bridge mode remains distinct and unchanged.</p></html>'
)



def render_actions_summary(data:dict) -> str:
    """GitHub Actions Summary: browser-readable evidence, no downloads."""
    outcome = "L0 observed" if data["qualified_digital_link_l0"] else "UNQUALIFIED"
    lines = ["## PCIe Gen1 x1 — independent host/device LTSSM",
             f"**{outcome}** · original Verilator transcript", "",
             "The host and device run independently and exchange real PIPE words. "
             "Original pcievhost logs LTSSM stages without simulator times. "
             "OpenPCIe logs its RTL states with simulator timestamps. "
             "Endpoint link_up may assert before the final ST_L0.", "",
             "| Host stage (original C model) | Source log line | Simulator timestamp |",
             "|---|---:|---|"]
    for e in data["events"]:
        if e["kind"]=="host_ltssm":
            lines.append(f'| {e["stage"]} | {e["line"]} | Not emitted |')
    lines.extend(["", "| Endpoint stage (original RTL) | Source log line | Simulation ns |",
                  "|---|---:|---:|"])
    for e in data["events"]:
        if e["kind"]=="endpoint_ltssm":
            lines.append(f'| {e["stage"]} | {e["line"]} | {e["time_ps"]/1000:.3f} |')
    samples=data.get("pipe_traffic_samples",{})
    lines.extend(["",
        f"**Observed PIPE samples:** Host to Device {samples.get('host_to_device',0)}; "
        f"Device to Host {samples.get('device_to_host',0)}.",
        f"**Original host InitLink returned:** {data['host_l0_observed']} · "
        f"**Endpoint actual ST_L0 observed:** {data['endpoint_ltssm_l0_observed']}.",
        "",
        "**Scope:** isolated Gen1 digital link, not full-chip boot, BAR memory "
        "transfer, NoC SRAM writes or PCIe read completion. The CI artifact "
        "pcie-link-report.html includes the responsive two-lane view and observed "
        "PIPE words.", ""])
    if data["issues"]:
        lines.extend(["### Qualification failures",*("- "+v for v in data["issues"]),""])
    return "\n".join(lines)


def export_shared_protocol_timeline(data:dict, output:Path, *, bar_evidence=None, mode="l0") -> dict:
    """Reuse the EXISTING protocol event exporter and HTML explorer.

    Only endpoint LTSSM state transitions have observed simulator ps stamps;
    host return, local BAR setup and software events without timestamps stay
    in the separate diagnostic JSON/HTML and are never promoted to protocol
    events or TLP completions. Optional BAR0 rows are an independently checked
    *original host* configuration request, real endpoint RX/AXI-Lite
    acceptance, returned Cpl/CplD and RC callback. Their times are ONLY
    endpoint RTL accepted pin timestamps, never the RC's unrelated clock.
    This does not connect the non-config bridge or qualify SoC boot.
    """
    try:
        from . import protocol_report
    except ImportError:
        import protocol_report
    from dv.common.protocol_trace import ProtocolTrace

    sources={
        "pcie0.ltssm": {
            "protocol":"pcie",
            "clock_domain":"pipe_125mhz",
            "role":"link",
            "implementation":"original_openpcie_ltssm",
            "modeling":"behavioral_digital_phy",
        }
    }
    if mode not in ("l0","bar0","mem_ingress"):
        raise ValueError("unknown source-selected PCIe lane")
    if (mode=="l0") != (bar_evidence is None):
        raise ValueError("real BAR0 Config TLP evidence required for enumeration lanes")
    if bar_evidence is not None:
        transactions=bar_evidence.get("transactions")
        if (bar_evidence.get("qualified_over_link_bar0") is not True
                or not isinstance(transactions,list) or len(transactions)!=6):
            raise ValueError("unqualified source-checked real BAR0 enumeration")
        sources["pcie0.config"]={
            "protocol":"pcie", "clock_domain":"pipe_125mhz",
            "role":"link", "implementation":"original_openpcie_cfg_tlp_axi_lite",
            "modeling":"behavioral_digital_phy",
        }
    trace=ProtocolTrace(output/"protocol-events.jsonl",sources)
    try:
        for event in data["events"]:
            if event["kind"]=="endpoint_ltssm":
                trace.event(
                    "pcie0.ltssm", "ltssm_transition", event["time_ps"],
                    {"from": event["from"], "to": event["to"],
                     "original_log_line": event["line"]})
        if bar_evidence is not None:
            for row in transactions:
                start=row.get("endpoint_first_rx_ps")
                finish=row.get("endpoint_last_cpl_ps")
                if (type(start) is not int or type(finish) is not int
                        or start < 0 or finish < start
                        or row.get("host_completion_observed") is not True
                        or row.get("actual_completion_kind") not in ("Cpl","CplD")):
                    raise ValueError("BAR0 transaction lacks real accepted pins and RC completion")
                if row.get("kind") not in ("CfgWr0","CfgRd0"):
                    raise ValueError("unexpected original configuration TLP")
                trace.transaction(
                    "pcie0.config", "cfg_wr0" if row["kind"]=="CfgWr0" else "cfg_rd0",
                    start_ps=start, end_ps=finish,
                    identifier=row["host_tag"], status="complete",
                    fields={
                        "address":row["address"], "host_value":row["host_value"],
                        "endpoint_received_payload":row.get("endpoint_received_payload"),
                        "axi_accepted_wdata":row.get("axi_accepted_wdata"),
                        "endpoint_cpld_payload":row.get("endpoint_cpld_payload"),
                        "completion_type":row["actual_completion_kind"],
                        "host_completion_observed":True,
                        "root_complex_cpl_timestamp_native":row["root_complex_cpl_timestamp_native"],
                        "time_scope":"endpoint_accepted_pins_ps",
                        "evidence_scope":"isolated_real_host_cfg_only",
                    })
        trace.close("pass" if data["qualified_digital_link_l0"] else "fail",
                    "; ".join(data["issues"]) if data["issues"] else None)
    except BaseException as exc:
        if not trace.closed:
            trace.close("fail",str(exc))
        raise
    # This is deliberately NOT a source-selected full-chip regress.py result,
    # and produces no result.json or fake AXI/TLP transactions.
    names={"l0":"pcie-link-isolated",
           "bar0":"pcie-bar0-isolated",
           "mem_ingress":"pcie-mem-ingress-isolated"}
    plan={"target":names[mode],"engine":"verilator",
          "report":{"protocols":{"sources":sources,"max_events":100000}}}
    return protocol_report.build(output,plan)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("log",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--github-summary",type=Path,help="Append browser-visible Actions summary")
    p.add_argument("--bar-evidence",type=Path,
                   help="Source-verified real BAR0 ConfigRd/ConfigWr evidence JSON")
    p.add_argument("--mode",choices=["l0","bar0","mem_ingress"],default="l0",
                   help="Use a unique source-qualified target per CI lane")
    args=p.parse_args()
    if not args.log.is_file():
        p.error("simulation log not found")
    data=summarize(args.log.read_text(errors="replace"))
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"pcie-link-evidence.json").write_text(json.dumps(data,indent=2)+"\n")
    (args.out/"pcie-link-report.html").write_text(render(data))
    if args.github_summary:
        with args.github_summary.open("a",encoding="utf-8") as handle:
            handle.write(render_actions_summary(data))
    # Same passive-protocol explorer renderer as our existing TLP/AXI reports.
    bar_evidence=json.loads(args.bar_evidence.read_text()) if args.bar_evidence else None
    export_shared_protocol_timeline(data,args.out,bar_evidence=bar_evidence,mode=args.mode)
    print(f"{'PASS' if data['qualified_digital_link_l0'] else 'FAIL'} isolated PCIe L0 diagnostic: "
          f"{len(data['events'])} observations; {data['issues']}")
    return 0 if data["qualified_digital_link_l0"] else 1


if __name__=="__main__":
    sys.exit(main())
