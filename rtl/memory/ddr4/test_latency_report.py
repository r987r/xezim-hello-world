"""Fail-closed standalone latency calculations; test without running RTL."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from latency_report import calculate, clock_period_ps, configured_clock_period_ps


def ev(ch, cycle, **fields):
    return {"kind": "axi_handshake", "phase": "traffic",
            "channel": ch, "cycle": cycle, "fields": fields}


def complete():
    return [
        ev("ar", 10, id=1, addr=0x4000, len=1),
        ev("r", 19, id=1, last=0, resp=0),
        ev("r", 22, id=1, last=1, resp=0),
        ev("aw", 30, id=2, addr=0x8000, len=1),
        ev("w", 31, last=0),
        ev("w", 32, last=1),
        ev("b", 40, id=2, resp=0),
    ]


class DDR4LatencyContractTests(unittest.TestCase):
    def test_profile_clock_matches_source(self):
        self.assertEqual(configured_clock_period_ps(), 10000)
        self.assertEqual(clock_period_ps({"input_clk_freq": 100_000_000,
                                          "sys_clk_freq": 100_000_000}), 10000)

    def test_clock_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "must match"):
            clock_period_ps({"input_clk_freq": 100_000_000,
                             "sys_clk_freq": 159_000_000})

    def test_noninteger_period_rejected(self):
        with self.assertRaisesRegex(ValueError, "integer"):
            clock_period_ps({"input_clk_freq": 159_000_000,
                             "sys_clk_freq": 159_000_000})

    def test_correlation_and_scope(self):
        report = calculate(complete(), 10000)
        self.assertEqual(report["measured"]["read"]["avg_cycles"], 12)
        self.assertEqual(report["measured"]["write"]["avg_cycles"], 10)
        self.assertEqual(report["transactions"][0]["address"], 0x4000)
        self.assertEqual(report["measured"]["read"]["min_ps"], 120000)
        self.assertEqual(report["reference_clock"]["frequency_hz"], 100_000_000)
        self.assertEqual(report["internal_stages"]["controller_scheduling"]["status"], "unmeasured")
        self.assertEqual(report["internal_stages"]["physical_phy"]["status"], "not_modeled")
        self.assertEqual(report["internal_stages"]["noc_and_soc"]["status"], "not_connected")

    def test_last_accepted_read_beat_after_phase_transition_is_counted(self):
        # Test's task/monitor scheduler may update the label at the same
        # boundary where the final accepted read was observed. Don't lose it.
        events = complete()
        events[2]["phase"] = "post_traffic"
        result = calculate(events, 10000)
        self.assertEqual(result["measured"]["read"]["avg_cycles"], 12)
        self.assertEqual(result["measured"]["write"]["avg_cycles"], 10)

    def test_reject_uninitialized_axi_request(self):
        events = complete()
        events[0]["phase"] = "initialization"
        with self.assertRaisesRegex(ValueError, "outside traffic"):
            calculate(events, 10000)

    def test_reject_missing_rlast(self):
        events = complete()
        events[2]["fields"]["last"] = 0
        with self.assertRaisesRegex(ValueError, "RLAST"):
            calculate(events, 10000)

    def test_reject_write_without_wlast(self):
        events = complete()
        events[5]["fields"]["last"] = 0
        with self.assertRaisesRegex(ValueError, "WLAST"):
            calculate(events, 10000)

    def test_reject_unacknowledged_read(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            calculate(complete()[:-1] + [ev("ar", 45, id=3, addr=0x9000, len=0),
                                         ev("b", 48, id=2, resp=0)], 10000)

    def test_reject_non_okay_response(self):
        events = complete()
        events[-1]["fields"]["resp"] = 2
        with self.assertRaisesRegex(ValueError, "non-OKAY"):
            calculate(events, 10000)

    def test_reject_orphan_response(self):
        events = complete()
        events.insert(0, ev("r", 0, id=9, last=1, resp=0))
        with self.assertRaisesRegex(ValueError, "no accepted request"):
            calculate(events, 10000)

    def test_reject_extra_data(self):
        events = complete()
        events.insert(5, ev("w", 32, last=0))
        with self.assertRaisesRegex(ValueError, "WLAST"):
            calculate(events, 10000)

    def test_ignore_nontraffic_phase(self):
        events = [ev("ar", 1, id=9, addr=0x1200, len=0),
                  ev("r", 2, id=9, last=1, resp=0)]
        for event in events:
            event["phase"] = "initialization"
        report = calculate(events + complete(), 10000)
        self.assertEqual(report["measured"]["read"]["samples"], 1)


if __name__ == "__main__":
    unittest.main()
