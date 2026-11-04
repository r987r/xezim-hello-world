"""DDR4 standalone timing contract and AXI-side latency evidence.

These are real AXI handshakes at the isolated controller frontend, not
controller-internal, silicon-PHY, or physical DRAM device measurements.
Keep unattached full-chip evidence and uninstrumented stages explicitly null.
"""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import json
from statistics import mean

import yaml

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "litedram_sim.yml"

MODEL_STAGES = {
    "controller_scheduling": {
        "status": "unmeasured", "boundary": "AXI acceptance to DFI READ/WRITE",
        "reason": "DFI command timing not yet exported in generated RTL",
    },
    "simulation_phy_pipeline": {
        "status": "unmeasured", "boundary": "DFI command/data to DFI rddata_valid or bank write",
        "reason": "SDRAMPHYModel internals not independently exposed",
    },
    "bank_model": {
        "status": "unmeasured", "boundary": "DFI bank operation to simulated storage access",
        "reason": "BankModel access signals not independently exposed",
    },
    "physical_phy": {
        "status": "not_modeled", "boundary": None,
        "reason": "This test uses LiteDRAM SDRAMPHYModel, not a physical DDR4 PHY",
    },
    "physical_dram_device": {
        "status": "not_modeled", "boundary": None,
        "reason": "This test uses LiteDRAM in-memory BankModel, not a physical DDR4 device",
    },
    "noc_and_soc": {
        "status": "not_connected", "boundary": None,
        "reason": "DDR4 RTL runs standalone; full-chip memory target is AXI SRAM",
    },
}


def clock_period_ps(profile: dict) -> int:
    """Fail if the simulation profile's core and source clocks disagree."""
    a, b = profile.get("input_clk_freq"), profile.get("sys_clk_freq")
    if type(a) is not int or type(b) is not int or a != b or a <= 0:
        raise ValueError("standalone SimPlatform input and system frequencies must match")
    if 10**12 % a:
        raise ValueError("simulation clock period must be an integer number of ps")
    return 10**12 // a


def configured_clock_period_ps() -> int:
    return clock_period_ps(yaml.safe_load(PROFILE.read_text()))


def summarize(samples: list[int], period_ps: int) -> dict:
    if not samples or any(type(s) is not int or s < 0 for s in samples):
        raise ValueError("latency samples must be nonempty nonnegative integer ps")
    ordered = sorted(samples)
    return {
        "samples": len(samples),
        "min_ps": ordered[0],
        "avg_ps": mean(ordered),
        "max_ps": ordered[-1],
        "min_cycles": ordered[0] / period_ps,
        "avg_cycles": mean(ordered) / period_ps,
        "max_cycles": ordered[-1] / period_ps,
    }


def calculate(events: list[dict], period_ps: int) -> dict:
    """Correlate accepted AXI transactions by channel and ID (not DFI tags).

    AW and W are independent AXI channels. This collector reports AW->B
    and AR->RLAST, not inferred DRAM operations. Incomplete responses,
    out-of-order same-ID completion, extra beats and non-OKAY responses
    fail rather than silently producing believable statistics.
    """
    if type(period_ps) is not int or period_ps <= 0:
        raise ValueError("positive measured simulation period required")
    reads = defaultdict(deque)
    writes = defaultdict(deque)
    pending_writes = deque()
    records = []
    w_seq = 0
    for event in events:
        if event.get("kind") != "axi_handshake" or event.get("phase") != "traffic":
            continue
        channel = event["channel"]
        fields = event["fields"]
        cycle = event["cycle"]
        if type(cycle) is not int or cycle < 0:
            raise ValueError("invalid AXI clock cycle")
        if channel == "ar":
            reads[fields["id"]].append({
                "operation": "read", "id": fields["id"], "address": fields["addr"],
                "start_cycle": cycle, "beats_expected": fields["len"] + 1,
                "beats_observed": 0,
            })
        elif channel == "aw":
            entry = {
                "operation": "write", "id": fields["id"], "address": fields["addr"],
                "start_cycle": cycle, "beats_expected": fields["len"] + 1,
                "beats_observed": 0, "data_done": False,
                "first_w_cycle": None,
            }
            writes[fields["id"]].append(entry)
            pending_writes.append(entry)
        elif channel == "w":
            if not pending_writes:
                raise ValueError("W beat without matching AW in controlled test")
            entry = pending_writes[0]
            entry["beats_observed"] += 1
            if entry["first_w_cycle"] is None:
                entry["first_w_cycle"] = cycle
            if entry["beats_observed"] > entry["beats_expected"]:
                raise ValueError("write has more W beats than AWLEN")
            expected_last = entry["beats_observed"] == entry["beats_expected"]
            if bool(fields["last"]) != expected_last:
                raise ValueError("WLAST disagrees with AWLEN")
            if expected_last:
                entry["data_done"] = True
                entry["last_w_cycle"] = cycle
                pending_writes.popleft()
            w_seq += 1
        elif channel in ("r", "b"):
            queue = reads if channel == "r" else writes
            identity = fields["id"]
            if not queue[identity]:
                raise ValueError(f"{channel.upper()} response has no accepted request")
            entry = queue[identity][0]
            if fields["resp"] != 0:
                raise ValueError(f"non-OKAY AXI response: {channel} {fields['resp']}")
            if channel == "r":
                entry["beats_observed"] += 1
                if entry["beats_observed"] > entry["beats_expected"]:
                    raise ValueError("read response exceeds ARLEN")
                expected_last = entry["beats_observed"] == entry["beats_expected"]
                if bool(fields["last"]) != expected_last:
                    raise ValueError("RLAST disagrees with ARLEN")
                if not expected_last:
                    continue
            else:
                if not entry["data_done"]:
                    raise ValueError("B response before complete W burst")
            if cycle < entry["start_cycle"]:
                raise ValueError("AXI response predates accepted address")
            queue[identity].popleft()
            entry["end_cycle"] = cycle
            entry["latency_cycles"] = cycle - entry["start_cycle"]
            entry["latency_ps"] = entry["latency_cycles"] * period_ps
            entry.pop("data_done", None)
            entry.pop("first_w_cycle", None)
            entry.pop("last_w_cycle", None)
            records.append(entry)
        else:
            raise ValueError(f"unknown AXI channel {channel}")
    pending_reads = {str(k): [dict(r) for r in v] for k, v in reads.items() if v}
    pending_responses = {str(k): [dict(r) for r in v] for k, v in writes.items() if v}
    if pending_writes or pending_reads or pending_responses:
        raise ValueError(
            "incomplete AXI request or missing completion: "
            f"AR={pending_reads} AW={pending_responses} WQ={list(pending_writes)} "
            f"completed={[(r['operation'], r['id'], r['address']) for r in records]}"
        )
    for op in ("read", "write"):
        if not any(x["operation"] == op for x in records):
            raise ValueError(f"no completed {op} traffic for timing")
    return {
        "schema_version": 1,
        "scope": "isolated_litedram_simulation",
        "backend": "litedram_controller_sdramphy_model_bankmodel",
        "interface": "user_port_axi_0",
        "reference_clock": {
            "period_ps": period_ps,
            "frequency_hz": 10**12 / period_ps,
            "domain": "standalone_sim_clk",
            "status": "configured_and_observed_in_cocotb",
        },
        "modeling": {
            "controller": "upstream LiteDRAM RTL",
            "phy": "LiteDRAM SDRAMPHYModel (DFI-level simulation)",
            "memory": "LiteDRAM BankModel with bounded 32 MiB geometry",
            "not_connected_to_full_chip": True,
        },
        "measured": {
            op: summarize([x["latency_ps"] for x in records if x["operation"] == op], period_ps)
            for op in ("read", "write")
        },
        "measured_boundary": {
            "read": "accepted AXI AR to accepted final AXI R",
            "write": "accepted AXI AW to accepted AXI B",
            "note": "AXI timing includes controller, simulation PHY/model, response queues and BFM stalls; not an internal-stage decomposition.",
        },
        "internal_stages": MODEL_STAGES,
        "transactions": records,
    }


def report_from_capture(directory: Path, expected_period_ps: int) -> dict:
    from traffic_observer import verify_capture
    capture = verify_capture(directory)
    lines = (Path(directory) / capture["events"]).read_text().splitlines()
    events = [json.loads(line) for line in lines]
    # Event timestamps are monitor cycle indices; every cycle must have
    # been continuously sampled at the configured period.
    if capture["sampled_cycles"] <= 0:
        raise ValueError("missing clock observation")
    result = calculate(events, expected_period_ps)
    result["monitor"] = {
        "status": capture["status"], "sampled_cycles": capture["sampled_cycles"],
        "event_count": capture["event_count"],
    }
    dest = Path(directory) / "ddr4_latency.json"
    dest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
