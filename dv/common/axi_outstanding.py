"""Passive, protocol-only AXI4 in-flight handshakes for clean run shutdown.

Tracks accepted AW until B and accepted AR until RLAST at each monitored
boundary and AXI ID. This never drives a signal or substitutes for the
canonical post-run correlator (tools/axi_report.py). The latter still checks
every byte, beat, ID, error response and incomplete transaction.
"""
from collections import Counter


def _number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


class AcceptedAxiInFlight:
    def __init__(self):
        self.pending = Counter()
        self.unmatched_responses = Counter()

    def observe(self, event):
        channel = event["channel"]
        if channel == "reset" and event["active"]:
            self.pending.clear()
            self.unmatched_responses.clear()
            return
        if channel not in ("aw", "b", "ar", "r"):
            return
        if channel == "r" and not _number(event["fields"]["last"]):
            return
        operation = "write" if channel in ("aw", "b") else "read"
        key = (event["monitor"], operation, _number(event["fields"]["id"]))
        if channel in ("aw", "ar"):
            self.pending[key] += 1
        elif self.pending[key] > 0:
            self.pending[key] -= 1
            if not self.pending[key]:
                del self.pending[key]
        else:
            # A response without an accepted request cannot qualify as idle.
            # The canonical AXI correlator independently reports its details.
            self.unmatched_responses[key] += 1

    def is_idle(self):
        return not self.pending and not self.unmatched_responses

    def summary(self):
        return {
            "pending": [list(key) + [count] for key, count in
                        sorted(self.pending.items()) if count],
            "unmatched": [list(key) + [count] for key, count in
                          sorted(self.unmatched_responses.items()) if count],
        }
