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
from traffic_observer import CHANNELS, TrafficObserver, clear_prior_capture, verify_capture


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

    def test_real_valid_not_ready_stalls_are_counted_not_inferred(self):
        obs = self.observer
        for _ in range(13):
            row = sample(channel="r")
            row["r"]["ready"] = 0
            obs.sample(row)
        self.assertEqual(obs.channels["r"], 0)
        self.assertEqual(obs.stall_cycles["r"], 13)
        self.assertEqual(obs.max_stall_streak["r"], 13)
        obs.sample(sample(channel="r"))
        self.assertEqual(obs.channels["r"], 1)
        self.assertEqual(obs.stall_streak["r"], 0)
        obs.sample(sample(channel="r"))
        self.assertEqual(obs.max_stall_streak["r"], 13)
        summary = obs.finish("fail", "isolated source-only test")
        self.assertEqual(summary["stall_cycles"]["r"], 13)
        self.assertEqual(summary["max_stall_streak"]["r"], 13)

    def test_verified_capture_reconciles_summary_and_actual_event_stream(self):
        obs = self.observer
        obs.sample(sample(), sim_time_ns=5)
        obs.next_phase("initialization")
        obs.sample(sample(wb="write"), sim_time_ns=15)
        obs.sample(sample(wb="read", init_done=1), sim_time_ns=25)
        obs.next_phase("traffic")
        for offset, ch in enumerate(CHANNELS):
            obs.sample(sample(channel=ch, init_done=1), sim_time_ns=35 + offset * 10)
        obs.next_phase("post_traffic")
        obs.sample(sample(init_done=1), sim_time_ns=85)
        obs.assert_complete()
        obs.finish("pass")
        summary = verify_capture(Path(self.temp.name))
        self.assertEqual(summary["sampled_cycles"], 9)

    def test_detect_missing_clock_edge(self):
        obs = self.observer
        obs.sample(sample(), sim_time_ns=5)
        with self.assertRaisesRegex(AssertionError, "monitoring gap"):
            obs.sample(sample(), sim_time_ns=35)

    def test_summary_without_trace_is_rejected(self):
        self.observer.sample(sample())
        self.observer.finish("fail", "invalid session")
        self.observer.events_path.unlink()
        with self.assertRaisesRegex(ValueError, "artifacts missing"):
            verify_capture(Path(self.temp.name))

    def test_forged_success_without_completed_phases_rejected(self):
        self.observer.sample(sample())
        self.observer.finish("pass")
        with self.assertRaisesRegex(ValueError, "coverage was not continuous"):
            verify_capture(Path(self.temp.name))

    def test_final_event_mismatch_fails_closed(self):
        self.observer.sample(sample())
        self.observer.finish("pass")
        summary = json.loads(self.observer.summary_path.read_text())
        summary.update({
            "continuous_capture": True,
            "started_before_init": True,
            "sampled_cycles": 4,
            "phases": {p: 1 for p in
                       ("pre_init", "initialization", "traffic", "post_traffic")},
            "channels": {c: 1 for c in CHANNELS}, "rlast_count": 1,
            "wlast_count": 1, "expected_write_beats": 1,
            "expected_read_beats": 1,
            "wishbone": {"writes": 1, "reads": 1},
        })
        self.observer.summary_path.write_text(json.dumps(summary))
        with self.observer.events_path.open("a") as out:
            out.write(json.dumps({"kind": "trace_cannot_end_here"}) + "\n")
        with self.assertRaisesRegex(ValueError, "end marker"):
            verify_capture(Path(self.temp.name))

    def test_prior_success_is_removed_before_next_run(self):
        obs = self.observer
        obs.sample(sample())
        obs.finish("pass")
        other_path = Path(self.temp.name) / "unrelated.rtl"
        other_path.write_text("leave generated files alone")
        functional_result = Path(self.temp.name) / "ddr4_functional_result.json"
        functional_result.write_text('{"status": "pass"}')
        clear_prior_capture(Path(self.temp.name))
        self.assertFalse(obs.summary_path.exists())
        self.assertFalse(obs.events_path.exists())
        self.assertFalse(functional_result.exists())
        self.assertEqual(other_path.read_text(), "leave generated files alone")
        with self.assertRaisesRegex(ValueError, "artifacts missing"):
            verify_capture(Path(self.temp.name))

    def test_stale_symlink_capture_is_refused(self):
        self.observer.finish("fail")
        target = Path(self.temp.name) / "unrelated.rtl"
        target.write_text("do not change")
        self.observer.summary_path.unlink()
        self.observer.summary_path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            clear_prior_capture(Path(self.temp.name))
        self.assertEqual(target.read_text(), "do not change")

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
