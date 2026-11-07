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
