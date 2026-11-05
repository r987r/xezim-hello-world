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


def pair_dfi_model_writes(groups: dict[str, list[dict]]) -> list[dict]:
    """Pair DFI WRITE with a modeled storage enable on the *same bank*.

    This boundary does not need AXI IDs. Require a unique store before the
    next DFI WRITE for that bank. Never infer which AXI AW caused a command:
    LiteDRAM can return AXI B before issuing DFI WRITE.
    """
    writes = groups.get("dfi_write", [])
    stores = groups.get("bankmodel_storage_write", [])
    pairs = []
    for i, cmd in enumerate(writes):
        bank = cmd.get("bank")
        if type(bank) is not int:
            raise ValueError("DFI WRITE event missing bank identity")
        next_command = min(
            (other["time_ps"] for other in writes[i+1:]
             if other.get("bank") == bank),
            default=None,
        )
        matches = [store for store in stores
                   if store.get("bank") == bank
                   and cmd["time_ps"] <= store["time_ps"]
                   and (next_command is None or store["time_ps"] < next_command)]
        detail = {"dfi_write_ps": cmd["time_ps"], "bank": bank,
                  "candidate_storage_events": len(matches)}
        if len(matches) == 1:
            detail["status"] = "measured"
            detail["bank_storage_ps"] = matches[0]["time_ps"]
            detail["latency_ps"] = matches[0]["time_ps"] - cmd["time_ps"]
        else:
            detail["status"] = "unmeasured_ambiguous_bank_storage"
        pairs.append(detail)
    return pairs


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
    # Model-internal write activity may happen AFTER AXI B. Measure the
    # independent DFI->BankModel boundary directly, with bank identity.
    write_pairs = pair_dfi_model_writes(groups)
    stages["dfi_write_to_bankmodel_storage"] += [
        pair["latency_ps"] for pair in write_pairs
        if pair["status"] == "measured"
    ]
    # Preserve measured boundaries for the earlier serialized requests.
    # Concurrent AXI transactions *cannot* be mapped to DFI commands by ID.
    # Explicitly mark only the overlapping intervals unmeasured, including
    # their coincident neighbors. Do not throw away genuine prior serial
    # measurements or attribute the first command to an arbitrary request.
    intervals = []
    for txn in transactions:
        a, b = txn["start_cycle"] * period_ps, txn["end_cycle"] * period_ps
        if b < a:
            raise ValueError("AXI end predates start")
        intervals.append((a, b))
    ambiguous = set()
    for i, (a, b) in enumerate(intervals):
        for j in range(i):
            c, d = intervals[j]
            if a < d and c < b:
                ambiguous.add(i)
                ambiguous.add(j)
    # DFI and BankModel events correspond to the *real* model, but in
    # a pipelined controller a transaction can require multiple commands.
    # Report first-access latency only, NOT all-bank service duration.
    for index, (txn, (start, stop)) in enumerate(zip(transactions, intervals)):
        op = txn["operation"]
        sample = {"operation": op, "axi_id": txn["id"],
                  "address": txn["address"],
                  "axi_start_ps": start, "axi_end_ps": stop}
        if index in ambiguous:
            sample["status"] = "unmeasured_overlapping_axi_dfi"
            sample["reason"] = "overlapping AXI windows; DFI command has no AXI ID"
            details.append(sample)
            continue
        if op == "write":
            # AXI B is a controller/frontend completion, not DRAM commit.
            # As seen in real CI, deferred DFI writes frequently fall after
            # B and can land within a later AW->B interval. Reporting those
            # as per-ID stage delays creates incorrect *numeric* evidence.
            sample["status"] = "unmeasured_axi_dfi_write_attribution"
            sample["reason"] = "DFI WRITE has no AXI ID; AXI B may precede DFI/model storage"
            details.append(sample)
            continue

        matching = [e for e in groups.get("dfi_read", [])
                    if start <= e["time_ps"] <= stop
                    and e.get("test_phase") in ("traffic", "post_traffic")]
        sample["dfi_commands"] = len(matching)
        if not matching:
            sample["status"] = "unmeasured_no_dfi_command"
            details.append(sample)
            continue
        command = matching[0]
        first = command["time_ps"]
        sample["first_dfi_command_ps"] = first
        sample["status"] = "first_command_measured"
        stages["controller_ar_to_dfi_read"].append(first - start)
        bank_events = [e for e in groups.get("bankmodel_read", [])
                       if first <= e["time_ps"] <= stop
                       and e.get("bank") == command.get("bank")]
        if bank_events:
            first_bank = bank_events[0]["time_ps"]
            sample["first_bank_access_ps"] = first_bank
            stages["dfi_read_to_bankmodel_access"].append(first_bank - first)
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
        "internal_stages": {
            **{k: stats(v, period_ps) for k, v in stages.items()},
            "controller_aw_to_dfi_write": {
                "status": "unmeasured",
                "reason": "AXI B may precede DFI WRITE and DFI has no AXI ID; no verified queue attribution",
            },
        },
        "dfi_write_model_pairs": write_pairs,
        "events": {k: len(v) for k, v in groups.items()},
        "transactions": details,
        "overlapping_axi_attribution": {
            "status": "unmeasured" if ambiguous else "no_overlap",
            "ambiguous_transactions": len(ambiguous),
            "reason": "DFI has no AXI IDs; overlapping requests cannot be individually attributed",
        },
        "limitations": [
            "first modeled access per serialized AXI request, not full burst service",
            "no DFI AXI ID tagging; overlaps are not attributed to transactions",
            "PHY and BankModel intervals are simulation delays, not silicon timing",
            "AXI B can precede DFI WRITE and modeled storage; no AW-to-DFI per-ID interval is reported",
            "DFI WRITE to modeled-bank storage is paired independently by bank",
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
    # This standalone positive smoke test must actually measure its modeled
    # READ and bank-storage WRITE boundaries. AW->DFI remains unmeasured
    # by design because AXI B does not prove storage completion.
    for key in ("controller_ar_to_dfi_read", "dfi_read_to_dfi_valid",
                "dfi_write_to_bankmodel_storage"):
        if report["internal_stages"][key]["status"] != "measured":
            raise ValueError(f"DDR4 positive run missing measured {key}")
    pairs = report.get("dfi_write_model_pairs", [])
    if (len(pairs) != summary["counters"]["dfi_write"]
        or any(p["status"] != "measured" for p in pairs)):
        raise ValueError("DDR4 modeled DFI write/storage pairing incomplete")
    report["capture"] = {
        "cycles": summary["sampled_cycles"], "events": len(events),
        "status": "pass", "probe_contract": "ddr4_probe_contract.json",
    }
    (directory / "ddr4_internal_latency.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report
