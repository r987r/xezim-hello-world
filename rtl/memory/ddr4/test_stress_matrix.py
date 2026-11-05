"""Host-only contract tests, not a DDR4 RTL pass."""
import unittest
from stress_matrix import build_matrix, expected_write, enabled_lane_runs, pattern_byte


class DDR4StressMatrixTests(unittest.TestCase):
    def test_bounded_low_mid_high_and_ids(self):
        cases = build_matrix(aperture_bytes=32 * 1024 * 1024, id_bits=3)
        self.assertEqual(len(cases), 8)
        self.assertEqual({x.kind for x in cases}, {"read", "write"})
        self.assertEqual({x.id for x in cases}, {0, 7})
        for case in cases:
            self.assertLessEqual(case.address + case.beats * 8, 32 * 1024 * 1024)

    def test_byte_strobes_do_not_modify_disabled_lanes(self):
        case = next(x for x in build_matrix(aperture_bytes=4096) if x.kind == "write")
        previous = bytes([0x55] * (case.beats * 8))
        out = expected_write(previous, case, 8)
        self.assertEqual(out[1:], previous[1:])
        self.assertEqual(out[0], pattern_byte(case.address, case.pattern))

    def test_sparse_strobe_decomposition_is_exact_and_bounded(self):
        for mask, expected in [
            (0x00, ()), (0x01, ((0, 1),)), (0xff, ((0, 8),)),
            (0x80, ((7, 8),)), (0x55, ((0, 1), (2, 3), (4, 5), (6, 7))),
        ]:
            with self.subTest(mask=mask):
                actual = enabled_lane_runs(mask, 8)
                self.assertEqual(actual, expected)
                reconstructed = sum(sum(1 << i for i in range(lo, hi))
                                    for lo, hi in actual)
                self.assertEqual(reconstructed, mask)
        for bad in (-1, 256):
            with self.assertRaises(ValueError):
                enabled_lane_runs(bad, 8)

    def test_final_beat_mask_retains_unmodified_burst_beats(self):
        case = next(c for c in build_matrix(aperture_bytes=4096)
                    if c.kind == "write" and c.beats == 16)
        original = bytes([0x5a]) * (case.beats * 8)
        selected = case.beats - 1
        partial = type(case)(case.address + selected * 8, 1, case.id,
                             case.strobe, case.pattern, "write")
        changed = expected_write(original[selected * 8:], partial, 8)
        result = original[:selected * 8] + changed
        self.assertEqual(result[:selected * 8], original[:selected * 8])
        self.assertEqual(result[-8:], changed)

    def test_fail_closed_geometry(self):
        for kw in ({"aperture_bytes": 4}, {"aperture_bytes": 4095},
                   {"aperture_bytes": 4096, "data_bits": 7},
                   {"aperture_bytes": 4096, "id_bits": 0}):
            with self.assertRaises(ValueError):
                build_matrix(**kw)


if __name__ == "__main__":
    unittest.main()
