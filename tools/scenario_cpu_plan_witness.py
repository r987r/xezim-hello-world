"""Verify complete real CPU0 selected-plan SHA from independently accepted AXI writes.

The compiler-derived header and firmware action logs are NOT evidence. This
checker sees only original passive AXI AW/W/B transactions, checked against
the independently resolved scenario-plan SHA, including byte lanes and B.
"""
from __future__ import annotations

import re


class PlanWitnessError(ValueError):
    pass


def _num(value):
    if type(value) is int:
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise PlanWitnessError("invalid original AXI numeric field")


def verify(plan_sha256: str, witness_phys: int, transactions: list[dict],
           *, monitor: str = "compute0_local_data.cpu") -> dict:
    if (not isinstance(plan_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", plan_sha256)
            or type(witness_phys) is not int or witness_phys < 0
            or witness_phys % 8):
        raise PlanWitnessError("invalid selected plan SHA or aligned CPU SRAM witness")
    if not isinstance(transactions, list):
        raise PlanWitnessError("missing independently correlated AXI transaction list")
    start, end = witness_phys, witness_phys + 32
    observed = {}
    counted = 0
    for tx in transactions:
        if tx.get("monitor") != monitor or tx.get("operation") != "write":
            continue
        addr = _num(tx.get("address"))
        if not (start - 7 <= addr < end):
            continue
        # Reject missing, failed, or incomplete original AW/W/B handshakes.
        beats = tx.get("beats")
        if (tx.get("status") != "complete" or tx.get("issues")
                or tx.get("role") != "initiator"
                or _num(tx.get("response")) != 0
                or tx.get("expected_beats") != 1
                or not isinstance(beats, list) or len(beats) != 1
                or _num(tx.get("request", {}).get("size")) != 2
                or _num(beats[0].get("last")) != 1):
            raise PlanWitnessError("CPU plan witness lacks an accepted and retired AXI write")
        beat = beats[0]
        strb, data = _num(beat.get("strb")), _num(beat.get("data"))
        if strb <= 0 or strb >= 1 << 8 or data < 0 or data >= 1 << 64:
            raise PlanWitnessError("CPU plan witness malformed 64-bit AXI W beat")
        lane = addr & 7
        expected_strobe = 0xf << (lane & ~3)
        if lane not in (0, 4) or strb != expected_strobe:
            raise PlanWitnessError("CPU plan witness has wrong write strobes or offset")
        base = addr & ~7
        for pos in range(8):
            if not (strb & (1 << pos)):
                continue
            phys = base + pos
            if not (start <= phys < end) or phys in observed:
                raise PlanWitnessError("CPU plan witness extra or duplicate accepted byte lane")
            observed[phys] = (data >> (pos * 8)) & 0xff
        counted += 1
    if counted != 8 or len(observed) != 32:
        raise PlanWitnessError("missing or duplicate full 256-bit CPU plan SHA transport")
    actual = bytes(observed[start + i] for i in range(32))
    if actual != bytes.fromhex(plan_sha256):
        raise PlanWitnessError("observed CPU AXI plan SHA does not match source-selected plan")
    return {
        "status": "full_sha_observed_on_real_cpu_axi",
        "plan_sha256": plan_sha256,
        "witness_phys": hex(witness_phys),
        "accepted_writes": counted,
        "checked_bytes": 32,
        "evidence": "original_passive_axi_aw_w_b_not_firmware_self_report",
        "scenario_action_completion_proven": False,
    }
