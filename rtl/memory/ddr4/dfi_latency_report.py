"""Measured DDR4 DFI/model latency boundaries, never inferred physical timing.

Only report a per-request decomposition when the test is serialized and
every relevant internal boundary is actually observed. Otherwise retain
raw event counts and mark ambiguous/unavailable intervals unmeasured.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean


def stats(durations_ps: list[int], period_ps: int) -> dict:
    if not durations_ps:
        return {"status": "unmeasured", "reason": "no unambiguously paired observed events"}
    if any(x < 0 for x in durations_ps):
        raise ValueError("negative DDR4 measured stage interval")
    return {
        "status": "measured", "samples": len(durations_ps),
        "min_ps": min(durations_ps), "avg_ps": mean(durations_ps),
        "max_ps": max(durations_ps), "avg_cycles": mean(durations_ps) / period_ps,
    }


def calculate_internal(axi: dict, events: list[dict], period_ps: int) -> dict:
    if period_ps <= 0 or not axi.get("transactions"):
        raise ValueError("no independently verified AXI timing baseline")
    groups: dict[str, list[dict]] = {}
    for e in events:
        if e.get("kind") in (
            "dfi_read", "dfi_write", "dfi_rddata_valid", "dfi_rddata_en",
            "dfi_wrdata_en", "bankmodel_read", "bankmodel_storage_write",
            "dfi_activate", "dfi_precharge", "dfi_refresh"
        ):
            t = e.get("time_ps")
            if type(t) is not int or t < 0:
                raise ValueError("invalid model event timestamp")
            groups.setdefault(e["kind"], []).append(e)
    for events_for_kind in groups.values():
        if any(b["time_ps"] < a["time_ps"]
               for a, b in zip(events_for_kind, events_for_kind[1:])):
            raise ValueError("non-monotonic model event times")

    transactions = sorted(axi["transactions"], key=lambda x: x["start_cycle"])
    stages = {
        "controller_ar_to_dfi_read": [],
        "dfi_read_to_bankmodel_access": [],
        "bankmodel_access_to_dfi_valid": [],
        "dfi_valid_to_last_axi_r": [],
        "dfi_read_to_dfi_valid": [],
        "controller_aw_to_dfi_write": [],
        "dfi_write_to_bankmodel_storage": [],
    }
    details = []
    # These are serial smoke tests, with no overlapping AXI requests.
    # If overlap exists, matching DFI commands to AXI IDs by time is unsafe.
    intervals = []
    for txn in transactions:
        a, b = txn["start_cycle"] * period_ps, txn["end_cycle"] * period_ps
        if b < a:
            raise ValueError("AXI end predates start")
        if intervals and a < intervals[-1][1]:
            return {
                "status": "aggregate_only",
                "reason": "overlapping AXI requests; DFI has no AXI IDs",
                "internal_stages": {
                    k: {"status": "unmeasured", "reason": "ambiguous transaction attribution"}
                    for k in stages
                },
                "events": {k: len(v) for k, v in groups.items()},
                "transactions": [],
            }
        intervals.append((a, b))
    # DFI and BankModel events correspond to the *real* model, but in
    # a pipelined controller a transaction can require multiple commands.
    # Report first-access latency only, NOT all-bank service duration.
    for txn, (start, stop) in zip(transactions, intervals):
        op = txn["operation"]
        kind = "dfi_read" if op == "read" else "dfi_write"
        matching = [e for e in groups.get(kind, [])
                    if start <= e["time_ps"] <= stop
                    and e.get("test_phase") in ("traffic", "post_traffic")]
        sample = {"operation": op, "axi_id": txn["id"],
                  "address": txn["address"],
                  "axi_start_ps": start, "axi_end_ps": stop,
                  "dfi_commands": len(matching)}
        if not matching:
            sample["status"] = "unmeasured_no_dfi_command"
            details.append(sample)
            continue
        first = matching[0]["time_ps"]
        sample["first_dfi_command_ps"] = first
        sample["status"] = "first_command_measured"
        stages["controller_ar_to_dfi_read" if op == "read" else
               "controller_aw_to_dfi_write"].append(first - start)
        bankkind = "bankmodel_read" if op == "read" else "bankmodel_storage_write"
        bank_events = [e for e in groups.get(bankkind, [])
                       if first <= e["time_ps"] <= stop]
        if bank_events:
            first_bank = bank_events[0]["time_ps"]
            sample["first_bank_access_ps"] = first_bank
            stages["dfi_read_to_bankmodel_access" if op == "read" else
                   "dfi_write_to_bankmodel_storage"].append(first_bank - first)
        if op == "read":
            valids = [e for e in groups.get("dfi_rddata_valid", [])
                      if first <= e["time_ps"] <= stop]
            if valids:
                first_valid = valids[0]["time_ps"]
                sample["first_dfi_rddata_valid_ps"] = first_valid
                stages["dfi_read_to_dfi_valid"].append(first_valid - first)
                stages["dfi_valid_to_last_axi_r"].append(stop - first_valid)
                if bank_events and first_bank <= first_valid:
                    stages["bankmodel_access_to_dfi_valid"].append(first_valid - first_bank)
        details.append(sample)
    return {
        "status": "measured_model_events",
        "clock": {"period_ps": period_ps},
        "modeling": {
            "controller": "LiteDRAM RTL",
            "dfi": "DFI command/response nets in generated RTL",
            "phy": "LiteDRAM SDRAMPHYModel (behavioral, not silicon)",
            "dram": "LiteDRAM BankModel (behavioral, not physical DRAM)",
        },
        "internal_stages": {k: stats(v, period_ps) for k, v in stages.items()},
        "events": {k: len(v) for k, v in groups.items()},
        "transactions": details,
        "limitations": [
            "first modeled access per serialized AXI request, not full burst service",
            "no DFI AXI ID tagging; overlaps are not attributed to transactions",
            "PHY and BankModel intervals are simulation delays, not silicon timing",
            "write response and model storage commit may occur at different times",
            "actual model signals are required; no guessed component latency",
        ],
    }


def report_from_dfi(directory: Path, period_ps: int) -> dict:
    directory = Path(directory)
    summary = json.loads((directory / "ddr4_dfi_summary.json").read_text())
    if summary.get("status") != "pass" or summary.get("sampled_cycles", 0) <= 0:
        raise ValueError("incomplete DDR4 DFI probe coverage")
    raw = (directory / "ddr4_dfi_events.jsonl").read_text().splitlines()
    events = [json.loads(s) for s in raw]
    if not events or events[0].get("kind") != "probe_start" or events[-1].get("kind") != "probe_end":
        raise ValueError("truncated DDR4 DFI event trace")
    if events[-1].get("status") != "pass":
        raise ValueError("failed DDR4 internal event capture")
    # Require observed DFI and modeled-bank activity for both directions.
    for k in ("dfi_read", "dfi_write", "dfi_rddata_valid",
              "bankmodel_read", "bankmodel_storage_write"):
        if summary.get("counters", {}).get(k, 0) < 1:
            raise ValueError(f"DDR4 probe missing actual {k} event")
    axi = json.loads((directory / "ddr4_latency.json").read_text())
    report = calculate_internal(axi, events, period_ps)
    report["capture"] = {
        "cycles": summary["sampled_cycles"], "events": len(events),
        "status": "pass", "probe_contract": "ddr4_probe_contract.json",
    }
    (directory / "ddr4_internal_latency.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report
