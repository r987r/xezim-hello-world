"""The same unit emitters generate two separate projects without overwriting."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from project_build import build


class ProjectBuildTests(unittest.TestCase):
    def test_two_project_artifacts_isolated_and_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            original = build("xezim_soc_dv", output_root=out)
            new = build("xezim_ethernet_cpu_ddr_pcie", output_root=out)
            self.assertFalse(original["generated_full_chip"])
            self.assertFalse(new["generated_full_chip"])
            self.assertNotEqual(original["source_config_sha256"],
                                new["source_config_sha256"])
            self.assertIn("boot/bootrom.hex", new["files"])
            self.assertIn("memory/memory_tb.sv", new["files"])
            old_file = out / "xezim_soc_dv/memory/memory_tb.sv"
            new_file = out / "xezim_ethernet_cpu_ddr_pcie/memory/memory_tb.sv"
            self.assertIn("N_MEM = 2", old_file.read_text())
            self.assertIn("N_MEM = 1", new_file.read_text())
            build("xezim_soc_dv", output_root=out, check=True)
            build("xezim_ethernet_cpu_ddr_pcie", output_root=out, check=True)
            self.assertEqual(json.loads(
                (out / "xezim_soc_dv/manifest.json").read_text()
            )["project_id"], "xezim_soc_dv")
            self.assertEqual(json.loads(
                (out / "xezim_ethernet_cpu_ddr_pcie/manifest.json").read_text()
            )["project_id"], "xezim_ethernet_cpu_ddr_pcie")

    def test_cross_project_build_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            build("xezim_soc_dv", output_root=out)
            marker = out / "xezim_soc_dv/.project-build-owned"
            marker.write_text("xezim_ethernet_cpu_ddr_pcie\n")
            with self.assertRaisesRegex(ValueError, "another project"):
                build("xezim_soc_dv", output_root=out)

    def test_no_unknown_project_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "unknown project id"):
                build("invented_soc", output_root=Path(folder))


if __name__ == "__main__":
    unittest.main()
