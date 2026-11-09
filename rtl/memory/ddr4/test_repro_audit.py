"""DDR source repeatability test: no fabricated byte-equivalence."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "rtl/memory/ddr4"))
from repro_audit import compare, snapshot, RepeatabilityError


def sha(data):
    return hashlib.sha256(data).hexdigest()


class DdrReproAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.first, self.second = root / "first", root / "second"
        for p in (self.first, self.second):
            (p / "gateware").mkdir(parents=True)
            (p / "gateware/soc_ddr4_sim.v").write_text(
                "module soc_ddr4_sim;\nwire [3:0] axi_data;\nendmodule\n")
            self.record(p)

    def record(self, p):
        source = p / "gateware/soc_ddr4_sim.v"
        record = {
            "top": "soc_ddr4_sim",
            "status": "generated-not-simulated",
            "config": "rtl/memory/ddr4/litedram_sim.yml",
            "source": {"commit": "a" * 40, "model": "behavioral"},
            "ports": {"clk": 1},
            "files_sha256": {"gateware/soc_ddr4_sim.v": sha(source.read_bytes())}
        }
        (p / "ddr4_manifest.json").write_text(json.dumps(record))

    def test_byte_identical_two_independent_directories(self):
        x = compare(self.first, self.second)
        self.assertTrue(x["repeatable"])
        self.assertEqual(x["changed_count"], 0)
        self.assertIn("not_equivalence", x["qualification"])

    def test_real_generated_sv_mutation_reports_not_pass(self):
        p = self.second / "gateware/soc_ddr4_sim.v"
        p.write_text("module soc_ddr4_sim;\nwire [4:0] axi_data;\nendmodule\n")
        self.record(self.second)
        x = compare(self.first, self.second)
        self.assertFalse(x["repeatable"])
        self.assertIn("gateware/soc_ddr4_sim.v", x["changed_generated_paths"])
        self.assertTrue(any("axi_data" in line for line in x["diff_sample"]))

    def test_tamper_and_untracked_generated_outputs_fail_closed(self):
        p = self.second / "gateware/soc_ddr4_sim.v"
        p.write_text("module incorrect; endmodule\n")
        with self.assertRaisesRegex(RepeatabilityError, "tampered"):
            compare(self.first, self.second)
        self.record(self.second)
        (self.second / "new-untracked.sv").write_text("module other; endmodule\n")
        with self.assertRaisesRegex(RepeatabilityError, "untracked"):
            compare(self.first, self.second)

    def test_foreign_config_source_and_same_directory_rejected(self):
        with self.assertRaisesRegex(RepeatabilityError, "independent"):
            compare(self.first, self.first)
        rec = json.loads((self.second / "ddr4_manifest.json").read_text())
        rec["source"]["commit"] = "b" * 40
        (self.second / "ddr4_manifest.json").write_text(json.dumps(rec))
        with self.assertRaisesRegex(RepeatabilityError, "configuration"):
            compare(self.first, self.second)


if __name__ == "__main__":
    unittest.main()
