"""All published per-run views retain the shared site navigation.

Use representative HTML from the two independent monitor renderers and the
legacy step renderer. The actual source-verified evidence remains untouched.
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from run_page_chrome import decorate_run_pages
from publish_site import shell


class RunPageChromeTests(unittest.TestCase):
    def test_all_run_views_have_navigation_and_immutable_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/"runs"/"xezim"/"attempt"/"target"
            destination.mkdir(parents=True)
            pages={
                "report.html":('<html><style>main{color:red}header{display:flex}</style>'
                               '<main><header><h1>AXI Run Explorer</h1></header>'
                               '<script id="axi-data">AXI_ORIGINAL_RECORDS</script></main></html>'),
                "protocols.html":('<html><style>main{color:blue}</style><main>'
                                  '<h1>Protocol Run Explorer</h1>'
                                  '<script id="protocol-data">TLP_ORIGINAL_CAPTURE</script></main></html>'),
                "test-flow.html":('<!doctype html><title>Test flow</title><style>'
                                  'body{color:teal}</style><h1>INIT RUN CHECK</h1>'
                                  '<p>REAL_CHECKER_EVIDENCE</p>'),
                "variant-architecture.html":shell(
                    "Selected variant connectivity",'<h1>SELECTED_REAL_RTL</h1>',
                    Path("runs/xezim/attempt/target/variant-architecture.html"),
                    "r987r/xezim-hello-world","b"*40),
            }
            for name,body in pages.items():
                (destination/name).write_text(body)
            decorate_run_pages(
                destination,Path("runs/xezim/attempt/target"),
                "r987r/xezim-hello-world","a"*40,shell_fn=shell)
            for name,original in pages.items():
                with self.subTest(name=name):
                    html=(destination/name).read_text()
                    self.assertIn('aria-label="Main navigation"',html)
                    self.assertIn('aria-current="page"',html)
                    self.assertIn('aria-label="Run report navigation"',html)
                    self.assertIn('href="../../../../runs.html"',html)
                    self.assertIn('href="../../../../index.html"',html)
                    self.assertIn("All test runs",html)
                    self.assertIn('<footer',html)
                    # Already shell-rendered variant pages keep their original source footer.\n                    self.assertIn(("b" if name=="variant-architecture.html" else "a")*12,html)
                    self.assertNotIn("Not Found",html)
            self.assertIn("AXI_ORIGINAL_RECORDS",(destination/"report.html").read_text())
            self.assertIn("TLP_ORIGINAL_CAPTURE",(destination/"protocols.html").read_text())
            self.assertIn("REAL_CHECKER_EVIDENCE",(destination/"test-flow.html").read_text())
            self.assertIn("SELECTED_REAL_RTL",(destination/"variant-architecture.html").read_text())
            self.assertIn('href="protocols.html"',(destination/"report.html").read_text())
            self.assertIn('href="test-flow.html"',(destination/"report.html").read_text())
            self.assertEqual((destination/"variant-architecture.html").read_text().count('aria-label="Main navigation"'),1)

    def test_only_actual_subpages_appear(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/"runs"/"capture-only"/"123"/"scope"
            destination.mkdir(parents=True)
            (destination/"protocols.html").write_text(
                '<main><h1>Verified standalone capture</h1></main>')
            decorate_run_pages(
                destination,Path("runs/capture-only/123/scope"),
                "r987r/xezim-hello-world","c"*40,shell_fn=shell)
            html=(destination/"protocols.html").read_text()
            self.assertIn("All test runs",html)
            self.assertNotIn("INIT/RUN/CHECK</a>",html)
            self.assertNotIn("Run overview</a>",html)
            self.assertIn("Verified standalone capture",html)

    def test_reject_double_navigation_and_ambiguous_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/"runs"/"r"
            destination.mkdir(parents=True)
            p=destination/"report.html"
            p.write_text("<main>duplicate</main><main>another</main>")
            with self.assertRaisesRegex(ValueError,"unsupported standalone"):
                decorate_run_pages(destination,Path("runs/r"),
                                   "r987r/xezim-hello-world","c"*40,shell_fn=shell)
            p.write_text('<div class="hub-global-chrome"></div><main>already</main>')
            with self.assertRaisesRegex(ValueError,"already decorated"):
                decorate_run_pages(destination,Path("runs/r"),
                                   "r987r/xezim-hello-world","c"*40,shell_fn=shell)


if __name__=="__main__":
    unittest.main()
