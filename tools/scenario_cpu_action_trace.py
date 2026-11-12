"""Passive accepted-AXI attestation of real CPU source-selected SCN-C dispatch.

CPU firmware writes two driver-stage words for each resolved action to a
reserved, non-overlapping scenario SRAM trace. Only the original independent
AXI monitor can qualify the words as accepted/retired, with unique AW/W/B and
correct byte strobes. It is *not* independent hardware completion; existing
DMA/TLP/GMII/DFI scoreboards and exact bytes are still required.
"""
from __future__ import annotations

import re

from tools.scenario_cpu_plan_witness import (
    PlanWitnessError, accepted_cpu_word_bytes,
)


class CpuActionTraceError(ValueError):
    pass


def verify(plan_sha256: str, trace_phys: int, actions: list[dict],
           transactions: list[dict], *,
           monitor: str = "compute0_local_data.cpu") -> dict:
    if (not isinstance(plan_sha256, str) or
            re.fullmatch(r"[0-9a-f]{64}", plan_sha256) is None or
            type(trace_phys) is not int or trace_phys < 0 or
            not isinstance(actions, list) or not 1 <= len(actions) <= 4096):
        raise CpuActionTraceError("invalid source-selected CPU action trace contract")
    seen = set()
    words = []
    for i, action in enumerate(actions):
        if not isinstance(action, dict) or not isinstance(
                action.get("action_instance_id"), str):
            raise CpuActionTraceError("missing canonical action ID")
        aid = action["action_instance_id"]
        if not aid or aid in seen:
            raise CpuActionTraceError("duplicate or empty canonical action ID")
        seen.add(aid)
        # Exact C11 on-chip event encoding, bound to the source plan order.
        words.extend((0xa7000000 | i << 8 | 1,
                      0xa7000000 | i << 8 | 2))
    expected = b"".join(word.to_bytes(4, "little") for word in words)
    try:
        actual, accepted = accepted_cpu_word_bytes(
            trace_phys, len(expected), transactions, monitor=monitor)
    except PlanWitnessError as exc:
        raise CpuActionTraceError(f"real CPU action driver trace incomplete: {exc}") from exc
    if actual != expected:
        raise CpuActionTraceError(
            "real CPU action trace does not match source-selected issued/driver_done indices")
    return {
        "status": "source_selected_cpu_action_driver_observed_on_real_axi",
        "plan_sha256": plan_sha256,
        "trace_phys": hex(trace_phys),
        "action_ids": [action["action_instance_id"] for action in actions],
        "accepted_writes": accepted,
        "checked_bytes": len(expected),
        "issued": len(actions),
        "driver_done": len(actions),
        "evidence": "original_passive_axi_aw_w_b_driver_events_only",
        "hardware_completion_proven": False,
    }
