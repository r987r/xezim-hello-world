"""Unit tests for always-on, fail-closed DDR4 passive capture.

No cocotb/RTL needed. Exercise real event and summary writing, coverage,
bounds, and negative monitoring lifecycle cases independently of the DUT.
"""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from traffic_observer import CHANNELS, TrafficObserver


def sample(*, channel=None, addr=0x4000, wb=None, init_done=0, init_error=0):
    records = {name: {"valid": 0, "ready": 0} for name in CHANNELS}
    for name in CHANNELS:
        records[name].update({
            "addr": addr, "id": 1, "len": 0, "size": 3, "burst": 1,
            "data": 0x1234, "strb": 0xff, "last": 1, "resp": 0,
        })
    if channel:
        records[channel]["valid"] = 1
        records[channel]["ready"] = 1
    return {
        **records, "init_done": init_done, "init_error": init_error, "user_rst": 0,
        "wb": {"cyc": int(wb is not None), "stb": int(wb is not None),
               "ack": int(wb is not None), "we": int(wb == "write"),
               "adr": addr // 4, "dat_w": 0xabcd, "dat_r": 0xabcd, "err": 0},
    }


class FakeTask:
    def __init__(self, finished=False):
        self.finished = finished
    def done(self):
        return self.finished
    def result(self):
        return None


class TrafficObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.observer = TrafficObserver(Path(self.temp.name), heartbeat_cycles=2)

    def tearDown(self):
        if not self.observer.closed:
            self.observer.finish("fail", "test teardown")
        self.temp.cleanup()

    def test_all_phases_and_all_five_channels_stay_observed(self):
        obs = self.observer
        obs.sample(sample())
        obs.assert_health(FakeTask(), min_samples=1)
        obs.next_phase("initialization")
        obs.sample(sample(wb="write"))
        obs.sample(sample(wb="read", init_done=1))
        obs.next_phase("traffic")
        for ch in ("aw", "w", "b", "ar", "r"):
            obs.sample(sample(channel=ch, init_done=1))
        obs.next_phase("post_traffic")
        obs.sample(sample(init_done=1))
        obs.assert_complete()
        info = obs.finish("pass")
        self.assertTrue(info["continuous_capture"])
        self.assertTrue(info["started_before_init"])
        self.assertEqual(info["sampled_cycles"], 9)
        self.assertEqual(set(info["channels"]), set(CHANNELS))
        self.assertEqual(info["rlast_count"], 1)
        self.assertEqual(info["wishbone"], {"writes": 1, "reads": 1})
        self.assertEqual(info["status"], "pass")
        events = [json.loads(x) for x in obs.events_path.read_text().splitlines()]
        self.assertEqual(events[0]["kind"], "capture_start")
        self.assertEqual(events[-1]["kind"], "capture_end")
        self.assertEqual(len([x for x in events if x["kind"] == "axi_handshake"]), 5)
        self.assertTrue(any(x["kind"] == "heartbeat" for x in events))

    def test_missing_traffic_channel_fails_closed(self):
        obs = self.observer
        obs.sample(sample())
        obs.next_phase("initialization")
        obs.sample(sample(wb="write"))
        obs.sample(sample(wb="read"))
        obs.next_phase("traffic")
        for ch in ("aw", "w", "b", "ar"):
            obs.sample(sample(channel=ch))
        obs.next_phase("post_traffic")
        obs.sample(sample())
        with self.assertRaisesRegex(AssertionError, "missed R"):
            obs.assert_complete()

    def test_capture_must_start_before_initialization(self):
        with self.assertRaisesRegex(AssertionError, "never sampled previous phase"):
            self.observer.next_phase("initialization")

    def test_monitor_early_exit_fails(self):
        self.observer.sample(sample())
        with self.assertRaisesRegex(AssertionError, "exited before test teardown"):
            self.observer.assert_health(FakeTask(finished=True))

    def test_partial_capture_is_not_a_pass(self):
        obs = self.observer
        obs.sample(sample())
        info = obs.finish("fail", "simulated timeout")
        self.assertEqual(info["status"], "fail")
        self.assertFalse(info["continuous_capture"])
        self.assertIn("simulated timeout", obs.summary_path.read_text())

    def test_overflow_fails_closed(self):
        self.observer.finish("fail")
        other = TrafficObserver(Path(self.temp.name) / "overflow", max_events=10,
                                heartbeat_cycles=100000)
        with self.assertRaisesRegex(AssertionError, "capture incomplete"):
            for _ in range(12):
                other.sample(sample(channel="ar"))
        other.finish("fail", "capture overflow")
        self.assertGreater(other.overflows, 0)

    def test_missing_read_completion_fails(self):
        obs = self.observer
        obs.sample(sample())
        obs.next_phase("initialization")
        obs.sample(sample(wb="write"))
        obs.sample(sample(wb="read"))
        obs.next_phase("traffic")
        for ch in CHANNELS:
            record = sample(channel=ch)
            if ch == "r":
                record["r"]["last"] = 0
            obs.sample(record)
        obs.next_phase("post_traffic")
        obs.sample(sample())
        with self.assertRaisesRegex(AssertionError, "AR and RLAST"):
            obs.assert_complete()

    def test_invalid_phase_transition_rejected(self):
        self.observer.sample(sample())
        with self.assertRaisesRegex(AssertionError, "skip/repeat"):
            self.observer.next_phase("traffic")


if __name__ == "__main__":
    unittest.main()
