"""Correlate *observed* PCIe TLPs, local AXI, and SRAM handshakes.

No invented link/PHY latency, no global NoC ID inference, no new bus monitor.
The scope is the current 64-bit PCIe0 bridge and its local SRAM. Multiple
overlapping same-address requests that cannot be uniquely traced fail closed.
"""
from collections import defaultdict
from html import escape
from pathlib import Path
import json
import statistics

READ_STAGES = (
    ("tlp_to_axi", "TLP request → bridge AXI AR"),
    ("noc_to_sram", "PCIe0 AXI AR → SRAM AR"),
    ("sram", "SRAM AR → SRAM RLAST"),
    ("noc_return", "SRAM RLAST → bridge AXI RLAST"),
    ("axi_to_cpl", "Bridge AXI RLAST → TLP completion EOP"),
    ("tlp_roundtrip", "TLP request → completion EOP"),
)
WRITE_STAGES = (
    ("posted_to_axi_b", "Posted TLP EOP → bridge AXI B"),
)


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def unique(rows, description, issues):
    if len(rows) != 1:
        issues.append(f"{description}: expected exactly one observed match, got {len(rows)}")
        return None
    return rows[0]


def complete(row, description, issues):
    if row["status"] != "complete" or number(row.get("response") or 0) != 0:
        issues.append(f"{description}: AXI transaction incomplete or non-OKAY")
        return False
    return True


def payload_read(axi, header_address, dwords):
    """Recover PCIe DWORD-aligned bytes from the observed 64-bit AXI beats."""
    start = header_address - (number(axi["address"]) & ~7)
    data = b"".join(number(b["data"]).to_bytes(8, "little")
                    for b in axi["beats"])
    return data[start:start + 4 * dwords]


def write_bytes_tlp(row):
    f = row["fields"]
    payload = bytes.fromhex(f["payload_hex"])
    base, count = number(f["address"]), f["length_dw"]
    found = {}
    for dw in range(count):
        enables = number(f["first_be"]) if dw == 0 else (
            number(f["last_be"]) if dw == count - 1 else 15)
        for lane in range(4):
            if enables & (1 << lane):
                found[base + dw * 4 + lane] = payload[dw * 4 + lane]
    return found


def write_bytes_axi(row):
    base = number(row["address"]) & ~7
    found = {}
    for beat_index, beat in enumerate(row["beats"]):
        word = number(beat["data"]).to_bytes(8, "little")
        enables = number(beat["strb"])
        for lane in range(8):
            if enables & (1 << lane):
                found[base + beat_index * 8 + lane] = word[lane]
    return found


def stats(values, clock_ps):
    if not values:
        return None
    values = sorted(values)
    if any(v < 0 for v in values):
        raise ValueError("negative interval in observed PCIe timing")
    return {
        "count": len(values),
        "min_ns": min(values) / 1000,
        "avg_ns": round(statistics.mean(values) / 1000, 3),
        "max_ns": max(values) / 1000,
        "avg_cycles": round(statistics.mean(values) / clock_ps, 3),
    }


def analyze(directory):
    directory = Path(directory)
    protocol = json.loads((directory / "protocol-transactions.json").read_text())
    packets = [r for r in protocol["records"] if r["protocol"] == "pcie"]
    if not packets:
        return None
    axi = json.loads((directory / "axi-transactions.json").read_text())
    clock_ps = axi["run"].get("clock_period_ps")
    if type(clock_ps) is not int or clock_ps <= 0:
        raise ValueError("PCIe timing requires measured clock period")
    rows = axi["sections"]["axi"]["transactions"]
    reads = [r for r in packets if r["source"] == "pcie0.rx_req"
             and r["operation"] == "mem_read"]
    writes = [r for r in packets if r["source"] == "pcie0.rx_req"
              and r["operation"] == "mem_write"]
    completions = [r for r in packets if r["source"] == "pcie0.tx_cpl"
                   and r["operation"] == "completion"]
    hosts = {op: [r for r in rows if r["monitor"] == "pcie0_local_data.host"
                  and r["operation"] == op] for op in ("read", "write")}
    srams = {op: [r for r in rows if r["monitor"] == "pcie0_local_data.sram"
                  and r["operation"] == op] for op in ("read", "write")}
    issues, used_axi, used_completion = [], set(), set()
    readings = defaultdict(list)
    vectors = []
    if not reads or not writes or not completions:
        issues.append("required RTL PCIe read/write/completion evidence is absent")
    if len(reads) != len(hosts["read"]) or len(reads) != len(completions):
        issues.append("PCIe read TLP, AXI host read and completion counts disagree")
    if len(writes) != len(hosts["write"]):
        issues.append("PCIe posted writes and AXI host writes counts disagree")
    for req in sorted(reads, key=lambda r: r["start_ps"]):
        header_addr = number(req["fields"]["address"])
        cpl = unique([
            c for c in completions
            if c["id"] == req["id"] and
            c["end_ps"] - c["fields"]["request_to_completion_ps"] == req["start_ps"]
        ], f"PCIe completion for {req['id']} at {req['start_ps']}", issues)
        if cpl is None:
            continue
        cpl_key = (cpl["id"], cpl["start_ps"], cpl["end_ps"])
        if cpl_key in used_completion:
            issues.append("PCIe completion reused for more than one request")
            continue
        used_completion.add(cpl_key)
        req_end, cpl_end = req["end_ps"], cpl["end_ps"]
        ax = unique([
            a for a in hosts["read"] if a["uid"] not in used_axi
            and req_end <= a["start_ps"] <= a["end_ps"] <= cpl_end
            and (number(a["address"]) & ~3) == header_addr
        ], f"PCIe0 bridge AXI read for {req['id']}", issues)
        if ax is None:
            continue
        used_axi.add(ax["uid"])
        target = unique([
            t for t in srams["read"]
            if ax["start_ps"] <= t["start_ps"] <= t["end_ps"] <= ax["end_ps"]
            and number(t["address"]) == number(ax["address"])
        ], f"PCIe0 SRAM read for {req['id']}", issues)
        if target is None:
            continue
        if not (complete(ax, "bridge AXI read", issues) and
                complete(target, "SRAM read", issues)):
            continue
        if req["fields"]["requested_bytes"] > len(bytes.fromhex(cpl["fields"]["payload_hex"])):
            issues.append(f"short completion payload for {req['id']}")
        observed = payload_read(ax, header_addr, req["fields"]["length_dw"])
        cpl_bytes = bytes.fromhex(cpl["fields"]["payload_hex"])
        if observed != cpl_bytes:
            issues.append(f"AXI/TLP read data mismatch for {req['id']}")
        if [b["data"] for b in ax["beats"]] != [b["data"] for b in target["beats"]]:
            issues.append(f"AXI/SRAM read data mismatch for {req['id']}")
        chain = {
            "tlp_to_axi": ax["start_ps"] - req_end,
            "noc_to_sram": target["start_ps"] - ax["start_ps"],
            "sram": target["end_ps"] - target["start_ps"],
            "noc_return": ax["end_ps"] - target["end_ps"],
            "axi_to_cpl": cpl_end - ax["end_ps"],
            "tlp_roundtrip": cpl_end - req["start_ps"],
        }
        if sum(chain[k] for k in ("tlp_to_axi", "noc_to_sram", "sram",
                                   "noc_return", "axi_to_cpl")) != cpl_end - req_end:
            issues.append("PCIe stage timings do not reconstruct accepted TLP duration")
        if any(value < 0 for value in chain.values()):
            issues.append(f"PCIe timing boundary order violated: {req['id']}")
        for key, value in chain.items():
            readings[key].append(value)
        vectors.append({"address": req["fields"]["address"], "request_tag": req["id"],
                        "start_ps": req["start_ps"], "end_ps": cpl_end,
                        "bytes": req["fields"]["requested_bytes"],
                        "latency_ns": chain["tlp_roundtrip"] / 1000,
                        "stages_ns": {k: v / 1000 for k, v in chain.items()}})
    for req in writes:
        address = number(req["fields"]["address"])
        ax = unique([a for a in hosts["write"] if a["uid"] not in used_axi
                     and (number(a["address"]) & ~3) == address
                     and req["start_ps"] <= a["start_ps"] <= req["end_ps"] + 100000],
                    f"posted write bridge AXI for {req['id']} at {req['start_ps']}", issues)
        if ax is None:
            continue
        used_axi.add(ax["uid"])
        target = unique([t for t in srams["write"]
                         if number(t["address"]) == number(ax["address"])
                         and ax["start_ps"] <= t["start_ps"] <= t["end_ps"] <= ax["end_ps"]],
                        f"PCIe0 SRAM write for {req['id']}", issues)
        if target is None:
            continue
        if not (complete(ax, "bridge AXI write", issues) and
                complete(target, "SRAM write", issues)):
            continue
        if write_bytes_tlp(req) != write_bytes_axi(ax):
            issues.append(f"TLP/AXI byte strobe or write payload mismatch at {hex(address)}")
        if write_bytes_axi(ax) != write_bytes_axi(target):
            issues.append(f"AXI/SRAM write mismatch at {hex(address)}")
        readings["posted_to_axi_b"].append(ax["end_ps"] - req["end_ps"])
    if len(used_completion) != len(completions):
        issues.append("not all completion packets were uniquely matched")
    if len(used_axi) != len(hosts["read"]) + len(hosts["write"]):
        issues.append("unmatched PCIe bridge AXI operations remain")
    flow = directory / "test-flow.json"
    host_steps = []
    if flow.is_file():
        for row in json.loads(flow.read_text()).get("rows", []):
            if row["actor"] == "host0" and row["step"].startswith("bar_read_"):
                readings["host_read_api"].append(row["duration_ps"])
                matched = [r for r in vectors if r["address"] ==
                           hex(number(row["details"]["address"]) & ~3)
                           and row["start_ps"] <= r["start_ps"] <= r["end_ps"] <= row["time_ps"]]
                if len(matched) != 1:
                    issues.append(f"BAR API/TLP read correlation ambiguous: {row['step']}")
                else:
                    host_steps.append({
                        "step": row["step"], "address": row["details"]["address"],
                        "bytes": row["details"]["bytes"],
                        "host_api_ns": row["duration_ps"] / 1000,
                        "rtl_tlp_ns": matched[0]["latency_ns"],
                        "request_tag": matched[0]["request_tag"],
                        "stages_ns": matched[0]["stages_ns"],
                    })
    if len(host_steps) != 4:
        issues.append("expected four independently correlated host BAR read vectors")
    all_stages = (*READ_STAGES, *WRITE_STAGES,
                  ("host_read_api", "Modeled host BAR read API → return"))
    result = {
        "schema_version": 1, "clock_period_ps": clock_ps,
        "model": "accepted RTL PCIe bridge + FlooNoC + SRAM; modeled RC/link, no PHY",
        "coverage": {"mem_reads": len(reads), "mem_writes": len(writes),
                     "completions": len(completions),
                     "correlated_read_paths": len(vectors),
                     "correlated_host_read_apis": len(host_steps),
                     "correlated_axi_operations": len(used_axi)},
        "stages": [{"key": key, "label": label, **(stats(readings[key], clock_ps) or {})}
                   for key, label in all_stages],
        "host_vectors": host_steps,
        "issues": issues,
        "passed": not issues,
    }
    (directory / "traffic-latency.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def render_panel(result):
    if result is None:
        return ""
    def h(value):
        return escape(str(value))
    def fmt(value):
        return "unmeasured" if value is None else str(value)
    rows = "".join(
        "<tr>" + "".join("<td>" + h(v) + "</td>" for v in (
            stage["label"], stage.get("count", 0),
            fmt(stage.get("min_ns")), fmt(stage.get("avg_ns")),
            fmt(stage.get("max_ns")), fmt(stage.get("avg_cycles"))
        )) + "</tr>" for stage in result["stages"])
    hosts = "".join(
        "<tr>" + "".join("<td>" + h(v) + "</td>" for v in (
            row["step"], row["address"], row["bytes"],
            row["host_api_ns"], row["rtl_tlp_ns"], row["request_tag"]
        )) + "</tr>" for row in result["host_vectors"])
    status = "PASS" if result["passed"] else "FAIL: " + "; ".join(result["issues"])
    return (
        '<div class="card"><h2>Measured PCIe controller, NoC, SRAM and host latency</h2>'
        '<p>Accepted TLP, AXI AR/RLAST/B and SRAM boundaries. Time is simulation ns;'
        ' cycles use measured local clock. Link/PHY latency is unmeasured.'
        ' Posted writes have no PCIe completion; their time ends at observed AXI B.'
        ' Host read API covers only the modeled Root Complex callback.</p>'
        "<p><strong>Correlation: " + h(status) + "</strong> · " +
        h(result["coverage"]["correlated_read_paths"]) + " read paths · " +
        h(result["coverage"]["mem_writes"]) + " posted writes</p>"
        '<div class="tablewrap"><table><thead><tr><th>Measured stage</th><th>N</th>'
        '<th>Min ns</th><th>Avg ns</th><th>Max ns</th><th>Avg cycles</th>'
        '</tr></thead><tbody>' + rows + '</tbody></table></div>'
        '<h3>Host BAR read vectors — modeled host vs observed RTL</h3>'
        '<div class="tablewrap"><table><thead><tr><th>Step</th><th>Address</th>'
        '<th>Bytes</th><th>Host API ns</th><th>RTL TLP ns</th><th>Requester/tag</th>'
        '</tr></thead><tbody>' + hosts + '</tbody></table></div>'
        '</div>')
