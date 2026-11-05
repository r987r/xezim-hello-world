"""Fail-closed, per-step INIT/RUN/CHECK report for any stimulus origin.

This reports action attempts separately from independent RTL/VIP evidence.
It never assumes that a Python action means the corresponding RTL occurred.
"""
from __future__ import annotations
from collections import Counter
from html import escape
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from dv.common.test_flow import PHASES, validate_event


def summarize(events, expected):
    if type(expected) is not dict or set(expected) != set(PHASES):
        raise ValueError("flow config must cover init, run, check")
    for phase in PHASES:
        if not isinstance(expected[phase], list) or not expected[phase] or len(set(expected[phase])) != len(expected[phase]):
            raise ValueError(f"{phase}: empty/duplicate required steps")
    active, rows, issues, previous_seq, previous_ps = {}, [], [], -1, -1
    allowed = set()
    for phase, step_ids in expected.items():
        for item in step_ids:
            if not isinstance(item, str) or "." not in item:
                raise ValueError("flow steps must be actor.step names")
            allowed.add((phase, item))
    seen_start = set()
    for event in events:
        validate_event(event)
        key = (event["phase"], event["actor"]+"."+event["step"])
        if event["seq"] != previous_seq+1 or event["time_ps"] < previous_ps:
            issues.append("missing/reordered sequence or non-monotonic timestamp")
        previous_seq, previous_ps = event["seq"], event["time_ps"]
        if event["status"] == "start":
            if key in active:
                issues.append(f"duplicate start {key}")
            active[key] = event
            seen_start.add(key)
        else:
            start = active.pop(key, None)
            if start is None:
                issues.append(f"completion without start {key}")
            else:
                rows.append({**event, "start_ps":start["time_ps"],
                             "duration_ps":event["time_ps"]-start["time_ps"]})
            if event["status"] == "fail":
                issues.append(f"failed step {key}")
        if key not in allowed:
            # Additional unplanned steps are useful to diagnose test drift,
            # but they must be explicitly declared before claiming coverage.
            issues.append(f"unregistered test step {key}")
    for key in active:
        issues.append(f"unfinished test step {key}")
    finished = {(r["phase"], r["actor"]+"."+r["step"])
                for r in rows if r["status"]=="pass"}
    for phase in PHASES:
        for step in expected[phase]:
            if (phase, step) not in finished:
                issues.append(f"missing required step {phase}/{step}")
    if not events:
        issues.append("missing test-flow events")
    return {"schema_version":1,"phases":list(PHASES),
            "rows":rows,"issues":issues,"passed":not issues,
            "expected_steps":expected,
            "totals":dict(Counter(r["status"] for r in rows))}



def firmware_mmio_events(directory, config):
    """Resolve C firmware marks ONLY from completed, accepted, OKAY AXI writes.

    The source code calling soc_flow_emit is NOT evidence. The real bus
    monitor must observe all 4 bytes and the registered target address.
    """
    from test_flow_codec import decode_c_marker
    source=directory/"axi-transactions.json"
    if not source.is_file():
        raise ValueError("firmware marker requires actual AXI capture")
    if not isinstance(config,dict) or set(config)!={"monitor","address","actors","steps"}:
        raise ValueError("invalid firmware marker source")
    monitor=config["monitor"]
    address=int(config["address"],0)
    actors={int(key):value for key,value in config["actors"].items()}
    steps={int(key):value for key,value in config["steps"].items()}
    payload=json.loads(source.read_text())
    if not payload["run"]["capture_bound"] or payload["run"]["capture_overflow"]:
        raise ValueError("firmware marker AXI capture incomplete")
    rows=payload["sections"]["axi"]["transactions"]
    observed=[]
    for row in rows:
        if row["monitor"]!=monitor or int(row["address"],0)!=address or row["operation"]!="write":
            continue
        if row["status"]!="complete" or int(row["response"],0)!=0:
            raise ValueError("non-OKAY or incomplete firmware test-flow marker write")
        if len(row["beats"])!=1:
            raise ValueError("firmware test-flow marker must be a single beat")
        beat=row["beats"][0]
        # AXI data/strb are aligned to a beat; locate the addressed 32-bit lane.
        lane=(address % (int(row["request"]["data_width"],0)//8)
              if "data_width" in row["request"] else address%8)
        if lane+4>8 or (int(beat["strb"],0)>>lane)&0xf!=0xf:
            raise ValueError("partial or unaligned test-flow marker")
        value=(int(beat["data"],0)>>(lane*8))&0xffffffff
        metadata=decode_c_marker(value,actors,steps)
        observed.append({"schema_version":1,"seq":0,
                         "time_ps":beat["time_ps"],"status":metadata["status"],
                         "phase":metadata["phase"],"actor":metadata["actor"],
                         "step":metadata["step"],"origin":"rtl_observed",
                         "details":{"phys_address":hex(address)}})
    if not observed:
        raise ValueError("no real AXI firmware test-flow marker writes")
    return observed

def write_report(directory, plan):
    directory = Path(directory)
    required = plan.get("report",{}).get("flow",{}).get("required_steps")
    if required is None:
        return None
    path = directory/"test-flow-events.jsonl"
    events=[]
    issues=[]
    if path.is_file():
        for index,line in enumerate(path.read_text().splitlines(),1):
            try:
                events.append(json.loads(line))
            except (ValueError, TypeError):
                issues.append(f"corrupt test-flow line {index}")
    else:
        issues.append("missing test-flow capture")
    # RTL firmware and SV checkers publish actual observed phase milestones.
    # They come from the simulator transcript, NEVER from Python action intent.
    from test_flow_codec import SV_RE
    sim=directory/"simulation.log"
    if sim.is_file():
        for line in sim.read_text(errors="replace").splitlines():
            marker=SV_RE.search(line)
            if marker:
                ns,phase,actor,step,status=marker.groups()
                events.append({"schema_version":1,"seq":0,
                               "time_ps":int(ns)*1000,"phase":phase,
                               "actor":actor,"step":step,"status":status,
                               "origin":"rtl_observed","details":{}})
    # Optional C/firmware source shares the exact same stream, but only after
    # a matching observed AXI write is correlated by the existing reporter.
    fw_source=plan["report"]["flow"].get("firmware_mmio")
    if fw_source is not None:
        try:
            events.extend(firmware_mmio_events(directory,fw_source))
        except (ValueError,TypeError,KeyError) as exc:
            issues.append(f"firmware AXI evidence invalid: {exc}")
    events.sort(key=lambda e:e.get("time_ps",0))
    # Canonical run-local sequence after cross-source timestamp merge.
    for i,e in enumerate(events):
        e["seq"]=i
    try:
        result = summarize(events, required)
    except (ValueError, TypeError, KeyError) as exc:
        result = {"schema_version":1, "rows":[], "issues":[f"invalid capture: {exc}"],
                  "passed":False, "phases":list(PHASES),"expected_steps":required, "totals":{}}
    result["issues"] = issues + result["issues"]
    result["passed"] = not result["issues"]
    (directory/"test-flow.json").write_text(json.dumps(result,indent=2)+"\n")
    rows = []
    for row in result["rows"]:
        values = (row["phase"], row["actor"], row["step"], row["origin"],
                  row["status"], str(row["start_ps"]), str(row["duration_ps"]),
                  json.dumps(row["details"], sort_keys=True))
        rows.append("<tr>"+"".join("<td>"+escape(v)+"</td>" for v in values)+"</tr>")
    problems = "".join("<li>"+escape(s)+"</li>" for s in result["issues"])
    html = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Test flow</title><style>
body{font:15px system-ui;margin:1.5rem;max-width:1200px;background:#10151e;color:#e9ecf0}
a{color:#91caff}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:.5rem;text-align:left;border-bottom:1px solid #394453}
th{position:sticky;top:0;background:#182332}tr:hover{background:#202c3b}
.pass{color:#88dfa7}.fail{color:#ff9b93}
</style><h1>INIT → RUN → CHECK / step evidence</h1>
<p>Statements of stimulus intent do not by themselves prove RTL activity.
Evidence provenance is explicit in the Origin column.</p>"""
    html += "<h2 class='"+("pass" if result["passed"] else "fail")+"'>"+("PASS" if result["passed"] else "FAIL")+"</h2>"
    html += "<ul>"+problems+"</ul>"
    html += "<table><thead><tr>"+"".join("<th>"+x+"</th>" for x in ("Phase","Actor","Step","Origin","Status","Start ps","Duration ps","Details"))+"</tr></thead><tbody>"
    html += "".join(rows)+"</tbody></table>"
    (directory/"test-flow.html").write_text(html)
    # Only augment existing canonical report; do not create second run hub.
    index=directory/"report.html"
    if index.is_file() and "test-flow.html" not in index.read_text():
        original=index.read_text()
        index.write_text(original.replace("<main>",'<main><p><a href="test-flow.html">INIT/RUN/CHECK step flow</a></p>',1))
    return result
