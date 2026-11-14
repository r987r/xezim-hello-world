"""Bounded buffered storage for the *same* original passive AXI events.

Captures every accepted channel event without changing protocol monitoring,
sampling order, reset epochs, IDs or post-run AXI correlation. Unlike line
buffering (one OS flush per observed handshake), periodically flushes groups
of complete JSON lines; reset/phase/overflow records flush immediately.
A killed simulator may lose at most the final unflushed batch; the original
test still fails and never claims complete capture without capture evidence.
"""
from __future__ import annotations

import json
from typing import TextIO

BATCH_EVENTS = 128


class PassiveAxiEventSink:
    def __init__(self, output: TextIO, *, batch_events: int = BATCH_EVENTS):
        if type(batch_events) is not int or not 1 <= batch_events <= BATCH_EVENTS:
            raise ValueError("passive AXI batch must be an integer in [1, 128]")
        self.output = output
        self.batch_events = batch_events
        self.pending = 0

    def write(self, event: dict) -> None:
        # Keep the exact old canonical compact JSON wire format and order.
        self.output.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.pending += 1
        if self.pending >= self.batch_events or event.get("channel") in (
                "reset", "phase", "capture_start", "capture_overflow",
                "expect_response", "clock_period"):
            self.flush()

    def flush(self) -> None:
        self.output.flush()
        self.pending = 0
