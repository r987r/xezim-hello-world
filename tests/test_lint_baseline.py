import unittest
from tools.lint_baseline import deduplicate


class LintBaselineTests(unittest.TestCase):
    def test_deduplicate_across_mode_and_profile_without_hiding_errors(self):
        finding = {"code": "MissingTimeScale", "file": "rtl/top.sv", "line": 4,
                   "symbol_path": "top", "mode": "lint", "severity": "error",
                   "message": "needs timescale"}
        r1 = {"schema_version": 1, "profile": "chip-dma", "findings": [finding]}
        r2 = {"schema_version": 1, "profile": "chip-boot",
              "findings": [{**finding, "mode": "elaborate"}]}
        result = deduplicate([r1, r2])
        self.assertEqual(result["unique_count"], 1)
        self.assertEqual(result["findings"][0]["occurrences"], 2)
        self.assertEqual(result["findings"][0]["modes"], ["elaborate", "lint"])
        self.assertEqual(sum(x["count"] for x in result["raw_counts"]), 2)

    def test_malformed_fails(self):
        with self.assertRaises(ValueError):
            deduplicate([{"schema_version": 1, "profile": "x", "findings": [{"severity": "bad"}]}])
        with self.assertRaises(ValueError):
            deduplicate([{"profile": "x", "findings": []}])


if __name__ == "__main__":
    unittest.main()
