"""Independent passive Config-NoC proof for real CPU reset/ACK C frontdoor reads.

Consumes original AXI monitor transactions, not generated C constants,
mailbox echo, guessed RTL hierarchy or direct backdoor handles.
"""
from __future__ import annotations


class ResetCsrEvidenceError(ValueError):
    pass


def _num(value):
    if type(value) is int:
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise ResetCsrEvidenceError("invalid passive AXI numeric value")


def verify(transactions, issues, base, *, monitor="compute0_local_config.cpu"):
    if issues or not isinstance(transactions, list) or type(base) is not int or base < 0:
        raise ResetCsrEvidenceError("incomplete original AXI capture or invalid CSR base")
    found = {base: [], base + 4: []}
    for row in transactions:
        if row.get("monitor") != monitor or row.get("operation") != "read":
            continue
        address = _num(row.get("address"))
        if address not in found:
            continue
        beats = row.get("beats")
        if (row.get("plane") != "config" or row.get("role") != "initiator"
                or row.get("status") != "complete" or row.get("issues")
                or row.get("expected_beats") != 1 or not isinstance(beats, list)
                or len(beats) != 1 or not isinstance(beats[0], dict)
                or _num((row.get("request") or {}).get("size")) != 2
                or _num(row.get("response")) != 0
                or _num(beats[0].get("resp")) != 0
                or _num(beats[0].get("last")) != 1):
            raise ResetCsrEvidenceError("reset CSR observed incomplete/failed Config-NoC read")
        value = _num(beats[0].get("data"))
        if value >= 1 << 32 or value < 0:
            raise ResetCsrEvidenceError("reset CSR width exceeds real 32-bit Config NoC")
        found[address].append(value)
    # The boot ROM legitimately polls ACK==0 until CPU1 initializes.
    # Require an accepted release==1 and ACK==1 after initialization; the
    # CPU C's own synchronous read/check protects firmware execution, while
    # this passive capture independently establishes real bus completions.
    if 1 not in found[base] or 1 not in found[base + 4]:
        raise ResetCsrEvidenceError(
            "missing accepted CPU reset release/ACK=1 Config-NoC frontdoor reads")
    return {
        "status": "real_cpu_config_noc_reset_ack_reads_accepted",
        "monitor": monitor,
        "release_address": hex(base), "ack_address": hex(base + 4),
        "release_read_count": len(found[base]),
        "ack_read_count": len(found[base + 4]),
        "frontdoor_axi_completed": True,
        "backdoor_equivalence_proven": False,
        "evidence": "passive_axi_config_noc_csr_reads_only",
    }
