"""Doc changes must keep local links and durable entrypoints valid."""
import tempfile
import unittest
from pathlib import Path
from tools.check_docs import ROOT, documents, issues

class DocumentationTests(unittest.TestCase):
    def test_all_repository_docs(self):
        self.assertGreaterEqual(len(documents(ROOT)), 40)
        self.assertEqual(issues(ROOT), [])

    def test_broken_links_and_dated_headlines_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "README.md").write_text(
                "# Test\n<!-- BEGIN GENERATED SOC -->\n"
                "<!-- END GENERATED SOC -->\n"
                "## Current status 2026 milestone\n[missing](docs/absent.md)\n")
            found = issues(root)
            self.assertTrue(any("broken local link" in x for x in found))
            self.assertTrue(any("dated progress" in x for x in found))

    def test_stale_draft_pr_claim_in_entrypoint_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "docs").mkdir()
            (root / "README.md").write_text(
                "# Main\n<!-- BEGIN GENERATED SOC -->\n"
                "<!-- END GENERATED SOC -->\n"
            )
            (root / "docs" / "implementation-status.md").write_text(
                "# Status\nPR #150 is draft; no CI proof yet.\n"
            )
            self.assertTrue(any("dated progress" in x for x in issues(root)))

    def test_anchor_and_duplicate_headings(self):
        from tools.check_docs import heading_anchors
        anchors = heading_anchors("# Hello, World!\n## Hello, World!\n")
        self.assertIn("hello-world", anchors)
        self.assertIn("hello-world-1", anchors)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "docs").mkdir()
            (root / "docs/guide.md").write_text("# Intro\n## Next Step\n")
            (root / "README.md").write_text(
                "# Main\n<!-- BEGIN GENERATED SOC -->\n"
                "<!-- END GENERATED SOC -->\n"
                "[ok](docs/guide.md#next-step) [bad](docs/guide.md#not-here)\n"
            )
            self.assertTrue(any("broken heading anchor" in x for x in issues(root)))

    def test_command_targets_and_workflow_paths(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "docs").mkdir()
            (root / "tools").mkdir()
            (root / "config").mkdir()
            (root / ".github/workflows").mkdir(parents=True)
            (root / "Makefile").write_text("check-docs:\n\t@true\n")
            (root / "config/regression.yaml").write_text(
                "tests:\n  chip-pcie-host:\n    engine: cocotb-verilator\n"
            )
            (root / "tools/regress.py").write_text("# sample\n")
            (root / "README.md").write_text(
                "# Main\n<!-- BEGIN GENERATED SOC -->\n"
                "<!-- END GENERATED SOC -->\n"
                "[old workflow](https://github.com/r987r/xezim-hello-world/"
                "actions/workflows/removed.yml)\n"
                "```sh\n"
                "python3 tools/regress.py chip-pcie-host\n"
                "python3 tools/regress.py missing-target\n"
                "python3 tools/removed.py\n"
                "make check-docs\nmake made-up\n"
                "```\n"
            )
            errors = issues(root)
            self.assertTrue(any("unknown regression target missing-target" in x for x in errors))
            self.assertTrue(any("missing documented script tools/removed.py" in x for x in errors))
            self.assertTrue(any("unknown make target made-up" in x for x in errors))
            self.assertTrue(any("missing workflow removed.yml" in x for x in errors))
            self.assertFalse(any("chip-pcie-host" in x for x in errors))

    def test_external_links_and_code_samples_ignored(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "docs").mkdir()
            (root / "docs/ok.md").write_text("# Valid\n")
            fence = chr(96) * 3
            (root / "README.md").write_text(
                "# Main\n<!-- BEGIN GENERATED SOC -->\n"
                "<!-- END GENERATED SOC -->\n"
                "[valid](docs/ok.md) [web](https://github.com/)\n"
                + fence + "\n[not a file](missing.md)\n" + fence + "\n")
            self.assertEqual(issues(root), [])

if __name__ == "__main__":
    unittest.main()
