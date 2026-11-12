"""The original AXI channel stream remains lossless on successful runs.

Fast pure-Python test; no fake AXI transactions or bus model.
"""
from __future__ import annotations

import io
import json
import unittest

from dv.common.axi_event_sink import PassiveAxiEventSink, BATCH_EVENTS


class TrackedOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flush_calls = 0

    def flush(self):
        self.flush_calls += 1
        super().flush()


class PassiveAxiEventSinkTests(unittest.TestCase):
    def test_all_handshakes_ordered_and_exact_after_bounded_flush(self):
        output = TrackedOutput()
        sink = PassiveAxiEventSink(output)
        expected = [{"monitor":"cpu0", "channel":channel,
                     "time_ps":idx * 100, "fields":{"addr":hex(idx), "id":"0x0"}}
                    for idx,channel in enumerate(["ar", "r", "aw", "w", "b"] * 103)]
        for index, event in enumerate(expected):
            sink.write(event)
            if index == BATCH_EVENTS - 2:
                self.assertEqual(output.flush_calls, 0)
            if index == BATCH_EVENTS - 1:
                self.assertEqual(output.flush_calls, 1)
        self.assertEqual(output.flush_calls, len(expected) // BATCH_EVENTS)
        sink.flush()  # normal successful simulation shutdown
        self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()],
                         expected)
        self.assertEqual(output.getvalue(),
                         "".join(json.dumps(row, separators=(",",":")) + "\n"
                                 for row in expected))

    def test_critical_controls_flush_immediately_without_discarding_channel_events(self):
        output = TrackedOutput()
        sink = PassiveAxiEventSink(output)
        all_events = []
        for channel in ("ar", "r", "reset", "aw", "w", "phase",
                        "b", "expect_response", "ar", "clock_period",
                        "r", "capture_overflow"):
            item = {"channel": channel, "time_ps": len(all_events) * 10}
            all_events.append(item)
            previous = output.flush_calls
            sink.write(item)
            self.assertEqual(output.flush_calls, previous + (
                1 if channel in ("reset", "phase", "expect_response",
                                 "clock_period", "capture_overflow") else 0))
        sink.flush()
        self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()],
                         all_events)

    def test_maximum_unflushed_window_is_bounded_on_failing_run(self):
        sink = PassiveAxiEventSink(TrackedOutput())
        for i in range(BATCH_EVENTS * 3 + 19):
            sink.write({"channel":"r", "time_ps":i})
            self.assertLess(sink.pending, BATCH_EVENTS)
        self.assertEqual(sink.pending, 19)
        sink.flush()
        self.assertEqual(sink.pending, 0)


if __name__ == "__main__":
    unittest.main()
