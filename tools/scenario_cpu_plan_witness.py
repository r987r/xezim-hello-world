"""Fail-closed passive AXI proof of accepted CPU0 word stores.

The hardware observer, NOT the C callback/event log, reconstructs all
bytes, exact strobes, accepted B response and unique 32-bit writes.
Used for both the full plan SHA and source-selected action driver trace.
Neither proof alone substitutes for DMA/PCIe/GMII protocol scoreboards.
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


def accepted_cpu_word_bytes(start: int, byte_count: int, transactions: list[dict],
                            *, monitor: str = "compute0_local_data.cpu",
                            check_prior_lane: bool = False) -> tuple[bytes, int]:
    """Return independently accepted AXI bytes, never a mailbox/backdoor peek.

    check_prior_lane checks any crossing write into a standalone target.
    For an adjacent trace window it is disabled because the preceding
    full-SHA witness legitimately ends four bytes before the trace begins.
    """
    if (type(start) is not int or start < 0 or start % 8 or
            type(byte_count) is not int or not 4 <= byte_count <= 32768 or
            byte_count % 4 or start + byte_count > (1 << 64) or
            not isinstance(transactions, list)):
        raise PlanWitnessError("invalid selected aligned CPU AXI word window")
    end = start + byte_count
    observed: dict[int, int] = {}
    counted = 0
    for tx in transactions:
        if not isinstance(tx, dict):
            raise PlanWitnessError("invalid original AXI transaction")
        if tx.get("monitor") != monitor or tx.get("operation") != "write":
            continue
        addr = _num(tx.get("address"))
        if not ((start - 7 if check_prior_lane else start) <= addr < end):
            continue
        beats = tx.get("beats")
        req = tx.get("request")
        if (tx.get("status") != "complete" or tx.get("issues") or
                tx.get("role") != "initiator" or
                _num(tx.get("response")) != 0 or
                tx.get("expected_beats") != 1 or
                not isinstance(req, dict) or _num(req.get("size")) != 2 or
                not isinstance(beats, list) or len(beats) != 1 or
                not isinstance(beats[0], dict) or
                _num(beats[0].get("last")) != 1):
            raise PlanWitnessError("CPU observed word lacks completed real AXI AW/W/B")
        beat = beats[0]
        strb, data = _num(beat.get("strb")), _num(beat.get("data"))
        if strb <= 0 or strb >= 1 << 8 or data < 0 or data >= 1 << 64:
            raise PlanWitnessError("CPU word malformed 64-bit AXI W beat")
        lane = addr & 7
        if lane not in (0, 4) or strb != (0xf << lane):
            raise PlanWitnessError("CPU word has wrong AXI byte strobes or offset")
        base = addr & ~7
        for pos in range(8):
            if not (strb & (1 << pos)):
                continue
            phys = base + pos
            if not (start <= phys < end) or phys in observed:
                raise PlanWitnessError("CPU word extra or duplicate accepted AXI lane")
            observed[phys] = (data >> (pos * 8)) & 0xff
        counted += 1
    if counted != byte_count // 4 or len(observed) != byte_count:
        raise PlanWitnessError("missing or duplicate real CPU accepted AXI word writes")
    return bytes(observed[start + i] for i in range(byte_count)), counted


def verify(plan_sha256: str, witness_phys: int, transactions: list[dict],
           *, monitor: str = "compute0_local_data.cpu") -> dict:
    if not isinstance(plan_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_sha256):
        raise PlanWitnessError("invalid selected plan SHA")
    actual, counted = accepted_cpu_word_bytes(
        witness_phys, 32, transactions, monitor=monitor, check_prior_lane=True)
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
