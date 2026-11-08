"""Source-derived serial AXI latency case plan and fail-closed passive evidence.

The same manifest and case identities drive standalone NoC and permitted full-chip
BFM profiles. Stimulus uses upstream AXI agents; this module drives no DUT pins,
writes no synthetic observations, and never infers physical memory latency.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class BenchmarkError(ValueError):
    pass


def config(root=ROOT, profile="unloaded"):
    spec = yaml.safe_load((Path(root)/"config/fabric_latency.yaml").read_text())
    if spec.get("schema_version") != 1 or profile not in spec.get("profiles", {}):
        raise BenchmarkError("unknown/unsupported latency benchmark profile")
    p = spec["profiles"][profile]
    for key in ("warmup_per_route", "measured_per_route", "memory_offset",
                "max_outstanding", "operation_beats", "full_chip_scratch_offset"):
        if type(p.get(key)) is not int or p[key] < (0 if key == "warmup_per_route" else 1):
            raise BenchmarkError("invalid benchmark setting: "+key)
    if (p["max_outstanding"] != 1 or p["operation_beats"] != 1
            or p.get("pause_channels") is not False
            or not isinstance(p.get("phase"), str) or not p["phase"]):
        raise BenchmarkError("unloaded profile must serialize one beat without pauses")
    return p


def plan(manifest, spec, *, selected_masters=None, writable_only=False,
         selected_region_bases=None):
    """Enumerate every allowed source/window; unique address per target/case.

    Globally unique addresses within each target permit unambiguous pairing
    across local/global NoC AXI taps despite AXI-ID remapping. No fixed
    subsystem names, fixed seeds, assumed RTL ownership or silent case skips.
    """
    if not isinstance(manifest.get("masters"), list) or not manifest["masters"]:
        raise BenchmarkError("manifest has no AXI masters")
    if not isinstance(manifest.get("slaves"), list) or not manifest["slaves"]:
        raise BenchmarkError("manifest has no AXI slaves")
    slots = defaultdict(int)
    cases = []
    target_bases = set(selected_region_bases) if selected_region_bases is not None else None
    if target_bases is not None and (
            not target_bases or any(type(base) is not int or base < 0 for base in target_bases)):
        raise BenchmarkError("empty or malformed selected live RTL memory regions")
    seen_bases = set()
    permitted = set(selected_masters) if selected_masters is not None else None
    if permitted is not None and (
            not permitted or permitted - {m["name"] for m in manifest["masters"]}):
        raise BenchmarkError("requested AXI actor not in generated master catalog")
    n = spec["warmup_per_route"] + spec["measured_per_route"]
    for master in manifest["masters"]:
        if permitted is not None and master["name"] not in permitted:
            continue
        width = master["data_width"] // 8
        if width < 1 or master["data_width"] % 8:
            raise BenchmarkError("invalid AXI data width")
        for region in master["regions"]:
            if writable_only and region["access"] != "read_write":
                continue
            if target_bases is not None and region["base"] not in target_bases:
                continue
            if target_bases is not None:
                seen_bases.add(region["base"])
            matches = [(slave, area) for slave in manifest["slaves"]
                       if slave["plane"] == master["plane"]
                       for area in slave["regions"]
                       if area["base"] <= region["base"]
                       and region["base"] + region["size"] <= area["base"] + area["size"]]
            if len(matches) != 1:
                raise BenchmarkError("ambiguous or missing target for "+master["name"])
            slave, area = matches[0]
            index_key = (slave["name"], area["base"])
            offset = spec["memory_offset"] + slots[index_key] * n * width
            slots[index_key] += 1
            if offset % width or offset + n * width > region["size"]:
                raise BenchmarkError("benchmark address capacity exceeded: "+slave["name"])
            for sample in range(n):
                warmup = sample < spec["warmup_per_route"]
                address = region["base"] + offset + sample * width
                if address + width > area["base"] + area["size"]:
                    raise BenchmarkError("benchmark address outside target")
                case_id = f"{master['name']}:{slave['name']}:{region['base']:x}:{sample}"
                cases.append({
                    "case_id": case_id, "master": master["name"],
                    "monitor": master["network"]+"."+master["endpoint"],
                    "target": slave["name"], "plane": master["plane"],
                    "address": hex(address), "bytes": width,
                    "access": region["access"], "warmup": warmup,
                    "operations": (["read"] if region["access"] == "read"
                                   else ["write", "read"]),
                })
    if target_bases is not None and seen_bases != target_bases:
        raise BenchmarkError("live RTL memory model missing from authorized AXI windows")
    if not cases:
        raise BenchmarkError("no eligible benchmark cases for selected actors")
    if len({c["case_id"] for c in cases}) != len(cases):
        raise BenchmarkError("duplicate benchmark case identity")
    if len({(c["plane"], c["address"]) for c in cases}) != len(cases):
        raise BenchmarkError("duplicate target addresses make stage correlation ambiguous")
    return cases


def intent(cases, spec, target):
    return {
        "schema_version": 1, "scope": target, "profile": "unloaded",
        "phase": spec["phase"], "max_outstanding": 1,
        "warmup_cases": sum(c["warmup"] for c in cases),
        "measured_cases": sum(not c["warmup"] for c in cases),
        "expected_measured_transactions": sum(
            len(c["operations"]) for c in cases if not c["warmup"]),
        "cases": cases,
        "state": "planned_not_observed",
    }


def validate(data, expected):
    """Demand exactly one clean, completed AXI source transaction per case/op.

    All source keys must be present in the measured phase. No benefit from
    silently dropping a slow/failed/ambiguous sample. Downstream stage pairing
    remains independently checked by the canonical fabric_report collector.
    """
    run = data.get("run", {})
    if not run.get("capture_bound") or run.get("capture_overflow") or run.get("dirty") is not False:
        raise BenchmarkError("incomplete, dirty or unbound AXI capture")
    if type(run.get("clock_period_ps")) is not int or run["clock_period_ps"] <= 0:
        raise BenchmarkError("missing measured reference clock")
    axi = data.get("sections", {}).get("axi", {})
    if axi.get("issues"):
        raise BenchmarkError("AXI correlator reported issues")
    phase = expected["phase"]
    required = Counter(
        (case["monitor"], case["plane"], op, int(case["address"],16))
        for case in expected["cases"] if not case["warmup"]
        for op in case["operations"])
    # A cold-boot full-chip run has *real CPU0/CPU1* continuously reading
    # firmware while the reserved BFM tests data paths. Those initiators are
    # captured and must remain complete, but must not be counted as BFM cases.
    # Actor ownership is resolved exclusively from the source-authored plan.
    source_monitors = {key[0] for key in required}
    observed = Counter()
    background = Counter()
    for tx in axi.get("transactions", []):
        if tx.get("phase") != phase or tx.get("role") != "initiator":
            continue
        if (tx.get("status") != "complete" or tx.get("issues")
                or tx.get("start_ps") is None or tx.get("end_ps") is None or
                tx["end_ps"] < tx["start_ps"]):
            raise BenchmarkError("incomplete or inconsistent AXI source transaction in benchmark phase")
        if tx.get("monitor") not in source_monitors:
            # Real CPU traffic stays in the canonical AXI trace and remains
            # subject to strict capture-wide completion/error checks.
            background[tx["monitor"]] += 1
            continue
        if (tx.get("expected_beats") != 1 or
                int(tx.get("response") or "0", 0) != 0):
            raise BenchmarkError("failed or non-one-beat benchmark AXI transaction")
        key = (tx["monitor"], tx["plane"], tx["operation"], int(tx["address"], 0))
        observed[key] += 1
    if required != observed:
        missing = list((required-observed).items())[:3]
        extra = list((observed-required).items())[:3]
        raise BenchmarkError(f"measured AXI source set mismatch; missing={missing} extra={extra}")
    return {
        "schema_version": 1, "status": "observed_axi_complete",
        "scope": expected["scope"], "phase": phase,
        "clock_period_ps": run["clock_period_ps"],
        "measured_cases": expected["measured_cases"],
        "measured_transactions": sum(observed.values()),
        "sampled_read": sum(v for k,v in observed.items() if k[2]=="read"),
        "sampled_write": sum(v for k,v in observed.items() if k[2]=="write"),
        "concurrent_nonbenchmark_initiator_transactions": sum(background.values()),
        "concurrent_nonbenchmark_initiators": dict(sorted(background.items())),
        "proof": "original passive accepted AXI; no simulated end-to-end PASS inferred",
    }


def validate_files(directory):
    path = Path(directory)
    expected = json.loads((path/"fabric-benchmark-plan.json").read_text())
    actual = json.loads((path/"axi-transactions.json").read_text())
    result = validate(actual, expected)
    (path/"fabric-benchmark-evidence.json").write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result
