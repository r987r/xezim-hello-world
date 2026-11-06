"""Contract tests only, no real PCIe RTL simulated."""
import unittest
from dv.pcie0.bar_contract import Bar, Request, decode_bar, CompletionTracker


class BarContractTests(unittest.TestCase):
    def test_bar_decode_rejects_cross_boundary_and_overlap(self):
        bars = [Bar(0, 0x100000, 4096), Bar(2, 0x200000, 8192)]
        self.assertEqual(decode_bar(bars, Request(1, 0x100200, 16, False))[1], 0x200)
        for addr in (0x100ffc, 0x300000):
            with self.assertRaises(ValueError):
                decode_bar(bars, Request(2, addr, 8, False))

    def test_completion_fragment_and_duplicates(self):
        tracker = CompletionTracker()
        request = Request(7, 0x100000, 12, False)
        tracker.issue(request)
        with self.assertRaises(ValueError):
            tracker.issue(request)
        self.assertFalse(tracker.complete(7, b"abcd"))
        self.assertTrue(tracker.complete(7, b"abcdefgh"))
        tracker.assert_drained()
        with self.assertRaises(ValueError):
            tracker.complete(7, b"x")

    def test_missing_completion_must_fail(self):
        t = CompletionTracker()
        t.issue(Request(3, 0, 4, False))
        with self.assertRaises(AssertionError):
            t.assert_drained()
        with self.assertRaises(ValueError):
            t.issue(Request(3, 0, 4, True))


if __name__ == "__main__":
    unittest.main()
