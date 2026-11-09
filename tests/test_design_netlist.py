"""Tests of external Slang tool adapters without pretending vendor binaries ran."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import design_netlist
import design_elaborate


class ExternalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / ".tools/regression/fake").mkdir(parents=True)
        (self.root / "config/regression.yaml").write_text(
            "schema_version: 1\ntests:\n  fake:\n    top: fake_tb\n")
        (self.root / "fake.sv").write_text("module fake_tb(input logic clk); endmodule\n")
        (self.root / ".tools/regression/fake/sources.f").write_text("fake.sv\n")
        (self.root / ".tools/regression/fake/plan.json").write_text(json.dumps({
            "target":"fake", "top":"fake_tb", "source_target":"noc",
            "sources":["fake.sv"]}))
        (self.root / "config/regression.yaml").write_text(
            "schema_version: 1\\ntests:\\n  fake:\\n    top: fake_tb\\n    sources: noc\\n".replace("\\n","\n"))

    def test_fail_closed_missing_binary(self):
        with patch("design_netlist.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "source-built binary not found"):
                design_netlist.analyze(self.root, "fake", "ports",
                                       self.root / "out/ports.json")
        with patch("design_elaborate.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "executable not found"):
                design_elaborate.analyze(self.root, "fake")

    def test_export_uses_real_profile_and_output(self):
        outfile = self.root / "out/ports.json"
        def run(argv, **kwargs):
            self.assertEqual(argv[1:5], ["--top", "fake_tb", "-f",
                                           str(self.root / ".tools/regression/fake/sources.f")])
            self.assertEqual(argv[-3:], ["--ports", "--format", "json"])
            return subprocess.CompletedProcess(argv, 0, '[{"name":"fake_tb.clk","direction":"input"}]', "")
        with patch("design_netlist.shutil.which", return_value="/mock/slang-report"), \
             patch("design_netlist.subprocess.run", side_effect=run):
            meta = design_netlist.analyze(self.root, "fake", "ports", outfile)
        self.assertEqual(meta["evidence"], "elaborated_slang_netlist_inputs_attested")
        self.assertIn("fake.sv",meta["selected_source_sha256"])
        self.assertEqual(meta["source_count"],1)
        self.assertIn("plan_sha256",meta)
        self.assertEqual(json.loads(outfile.read_text())[0]["name"], "fake_tb.clk")
        self.assertTrue((outfile.parent / (outfile.name + ".meta.json")).exists())

    def test_tool_failure_removes_stale_output(self):
        outfile = self.root / "netlist.json"
        outfile.write_text('{"stale":true}')
        with patch("design_netlist.shutil.which", return_value="/mock/slang-netlist"), \
             patch("design_netlist.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "bad RTL")):
            with self.assertRaisesRegex(ValueError, "bad RTL"):
                design_netlist.analyze(self.root, "fake", "netlist", outfile)
        self.assertFalse(outfile.exists())


    def test_selected_elaborated_hierarchy_rejects_foreign_source_and_duplicates(self):
        import hashlib
        selected = {"fake.sv": hashlib.sha256(
            (self.root / "fake.sv").read_bytes()).hexdigest()}
        def record(path="fake_tb", module="fake_tb", source="fake.sv"):
            return {"path": path, "module": module, "source": source}
        qualified = design_elaborate.audit_selected_hierarchy(
            self.root, "fake_tb", [record()], selected)
        self.assertEqual(qualified[0]["source_sha256"], selected["fake.sv"])
        self.assertFalse("elaborated" in qualified[0]["evidence"]
                         and qualified[0]["evidence"].endswith("hardware_proven"))
        with self.assertRaisesRegex(ValueError, "unselected RTL"):
            (self.root / "unselected.sv").write_text("module extra; endmodule")
            design_elaborate.audit_selected_hierarchy(
                self.root, "fake_tb",
                [record(), record("fake_tb.u_other", "extra", "unselected.sv")],
                selected)
        with self.assertRaisesRegex(ValueError, "duplicate elaborated instance"):
            design_elaborate.audit_selected_hierarchy(
                self.root, "fake_tb", [record(), record()], selected)
        with self.assertRaisesRegex(ValueError, "omitted the required root"):
            design_elaborate.audit_selected_hierarchy(
                self.root, "fake_tb", [record("fake_tb.u_child")], selected)
        with self.assertRaisesRegex(ValueError, "missing required"):
            design_elaborate.audit_selected_hierarchy(
                self.root, "fake_tb", [record(source="")], selected)
        with self.assertRaisesRegex(ValueError, "changed since"):
            (self.root / "fake.sv").write_text("module fake_tb; wire changed; endmodule")
            design_elaborate.audit_selected_hierarchy(
                self.root, "fake_tb", [record()], selected)

    def test_elaboration_custom_format(self):
        def run(argv, **kwargs):
            self.assertIn("--custom-format", argv)
            self.assertIn("|||", argv[-1])
            return subprocess.CompletedProcess(argv, 0,
                                               "fake_tb|||fake_tb|||fake.sv\n", "")
        with patch("design_elaborate.shutil.which", return_value="/mock/slang-hier"), \
             patch("design_elaborate.subprocess.run", side_effect=run):
            result = design_elaborate.analyze(self.root, "fake")
        self.assertEqual(result["instances"][0]["module"], "fake_tb")
        self.assertEqual(result["evidence"], "elaborated_slang_hier_inputs_attested")
        self.assertEqual(result["source_count"],1)
        self.assertFalse(result["bit_level_connectivity_proven"])
        self.assertEqual(len(result["source_hierarchy_sha256"]), 64)

    def test_source_plan_and_filelist_provenance_fail_closed(self):
        from selected_rtl_provenance import selected
        import hashlib
        valid=selected(self.root,"fake")
        self.assertEqual(valid["selected_source_sha256"]["fake.sv"],
                         hashlib.sha256((self.root/"fake.sv").read_bytes()).hexdigest())
        planfile=self.root/".tools/regression/fake/plan.json"
        plan=json.loads(planfile.read_text())
        plan["top"]="another_top"
        planfile.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError,"disagrees"):
            selected(self.root,"fake")
        plan["top"]="fake_tb"
        planfile.write_text(json.dumps(plan))
        (self.root/"fake.sv").unlink()
        with self.assertRaisesRegex(ValueError,"selected source missing"):
            selected(self.root,"fake")
        (self.root/"fake.sv").write_text("module fake_tb; endmodule")
        identity={"legacy_target":"fake","selection":{"filelist_sha256":"0"*64}}
        (self.root/".tools/regression/fake/identity.json").write_text(json.dumps(identity))
        with self.assertRaisesRegex(ValueError,"filelist SHA mismatch"):
            selected(self.root,"fake")



if __name__ == "__main__":
    unittest.main()
