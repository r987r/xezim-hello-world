"""Memory benchmark result schema and mode coverage, not RTL timing claims."""
import unittest
from tools.memory_benchmark import sweep


class MemoryBenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_modes_share_scenario_and_keep_synthetic_label(self):
        result = await sweep([64, 4096], ["strict", "hybrid", "fast"], repeats=1)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source"], "synthetic_bytes_not_rtl")
        self.assertEqual(len(result["summary"]), 6)
        for row in result["runs"]:
            self.assertEqual(row["simulated_cycles"], None)
            self.assertEqual(row["axi_transactions"], None)
            self.assertIn(row["policy"], ("strict", "hybrid", "fast"))
            self.assertGreaterEqual(row["total_wall_ns"], 0)
            self.assertIn("not a measured RTL speedup", row["note"])
        by_mode = {row["policy"]: row for row in result["summary"]
                   if row["size_bytes"] == 4096}
        self.assertEqual(set(by_mode), {"strict", "hybrid", "fast"})
        self.assertEqual(by_mode["strict"]["relative_to_strict"], 1.0)

    async def test_invalid_benchmark_sizes_and_policies_fail_closed(self):
        with self.assertRaises(ValueError):
            await sweep([0], ["fast"])
        with self.assertRaises(ValueError):
            await sweep([64], ["autofallback"])
