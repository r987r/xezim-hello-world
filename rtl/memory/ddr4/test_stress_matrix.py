"""Host-only contract tests, not a DDR4 RTL pass."""
import unittest
from stress_matrix import build_matrix, expected_write, pattern_byte


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

    def test_fail_closed_geometry(self):
        for kw in ({"aperture_bytes": 4}, {"aperture_bytes": 4095},
                   {"aperture_bytes": 4096, "data_bits": 7},
                   {"aperture_bytes": 4096, "id_bits": 0}):
            with self.assertRaises(ValueError):
                build_matrix(**kw)


if __name__ == "__main__":
    unittest.main()
