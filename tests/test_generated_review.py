"""Generator review should expose meaningful paths without inventing RTL evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generated_review


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


class GeneratedReviewTests(unittest.TestCase):
    def test_semantic_json_fields_include_adds_deletes_changes(self):
        old = '{"networks":{"a":{"routers":2},"b":{"routers":3}}}'
        new = '{"networks":{"a":{"routers":4},"c":{"routers":6}}}'
        self.assertEqual(generated_review.semantic_keys(old, new),
                         ["networks.a.routers", "networks.b.routers",
                          "networks.c.routers"])

    def test_grouping_is_explicit_about_what_is_generated(self):
        self.assertEqual(generated_review.classify("gen/projects/a/variants/default/rtl/soc_top.sv"),
                         "Selected/review RTL variants")
        self.assertEqual(generated_review.classify("gen/noc/floonoc/global_data/foo.sv"),
                         "Generated FlooNoC RTL and configurations")

    def test_review_tracks_modified_and_untracked_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            git(root, "init", "-q")
            git(root, "config", "user.name", "Test")
            git(root, "config", "user.email", "test@example.invalid")
            p = root / "gen/diagrams/noc-topology.json"
            p.parent.mkdir(parents=True)
            p.write_text('{"networks":{"a":{"routers":2}}}\n')
            git(root, "add", "gen")
            git(root, "commit", "-qm", "baseline")
            p.write_text('{"networks":{"a":{"routers":3}}}\n')
            new = root / "gen/chip/soc_top.sv"
            new.parent.mkdir(parents=True)
            new.write_text("module soc_top; endmodule\n")
            result = generated_review.review("HEAD", root=root)
            names = {item["path"]: item for item in result["files"]}
            self.assertEqual(names["gen/diagrams/noc-topology.json"]["changed_fields"],
                             ["networks.a.routers"])
            self.assertEqual(names["gen/chip/soc_top.sv"]["change"], "?")
            report = generated_review.markdown(result)
            self.assertIn("Generated diagrams and connectivity", report)
            self.assertIn("not establish an elaborated chip", report)

    def test_invalid_ref_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid comparison ref"):
            generated_review.review("--bad")


if __name__ == "__main__":
    unittest.main()
