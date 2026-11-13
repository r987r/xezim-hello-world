"""Integrate source-verified per-run evidence pages into the Pages site navigation.

The AXI/protocol/flow renderers intentionally own their own table CSS and
JavaScript. Preserve their entire document rather than copying archive HTML
or nesting an HTML document inside another. Only attach trusted site chrome.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re

REPORTS = (
    ("report.html", "Run overview"),
    ("protocols.html", "Protocol traffic"),
    ("test-flow.html", "INIT/RUN/CHECK"),
    ("variant-architecture.html", "Selected RTL topology"),
)

# Explicitly scoped: report CSS and AXI/protocol scripts remain untouched.
# The header colors and responsive behavior match tools/templates/site.html.
CHROME_STYLE = """
<style id="hub-run-navigation-style">
body{margin:0!important;max-width:none!important}
.hub-global-chrome,.hub-global-footer{background:#0b1220;color:#e9eff8;
  font:16px/1.6 system-ui,sans-serif;box-sizing:border-box}
.hub-global-chrome{border-bottom:1px solid #2b3c54}
.hub-global-header{display:block!important;max-width:1440px!important;
  margin:0 auto!important;padding:22px 4vw 12px!important;
  background:transparent!important;color:#e9eff8!important;box-sizing:border-box!important}
.hub-global-header .brand{font:750 19px/1.4 system-ui,sans-serif!important;
  letter-spacing:-.02em!important;text-decoration:none!important;color:#e9eff8!important}
.hub-global-header nav[aria-label="Main navigation"]{display:flex!important;gap:7px!important;
  align-items:center!important;flex-wrap:wrap!important;margin-top:14px!important}
.hub-global-header nav[aria-label="Main navigation"] a{display:inline-block!important;
  padding:7px 11px!important;color:#a9b9d0!important;border:1px solid transparent!important;
  border-radius:7px!important;text-decoration:none!important;font:14px/1.5 system-ui,sans-serif!important}
.hub-global-header nav[aria-label="Main navigation"] a:hover{background:#1e3045!important;color:#e9eff8!important}
.hub-global-header nav[aria-label="Main navigation"] a[aria-current="page"]{
  background:#1b3548!important;border-color:#4b728b!important;color:#e9eff8!important;font-weight:650!important}
.hub-run-tabs{display:flex;gap:9px;align-items:center;flex-wrap:wrap;
  max-width:1440px;margin:0 auto;padding:6px 4vw 14px;font:13px/1.4 system-ui,sans-serif}
.hub-run-tabs a{padding:6px 9px;border-radius:7px;border:1px solid #38506a;
  text-decoration:none!important;color:#80d4ff!important}
.hub-run-tabs a:hover{background:#1e3045}
.hub-run-tabs a[aria-current="page"]{background:#1b3548;color:#e9eff8!important;border-color:#80d4ff}
.hub-global-footer{border-top:1px solid #2b3c54;padding:20px 4vw!important;
  font:12px/1.65 system-ui,sans-serif!important;max-width:none!important;margin:0!important}
.hub-global-footer a{color:#80d4ff!important}
.hub-global-chrome a:focus-visible,.hub-run-tabs a:focus-visible{
  outline:2px solid #80d4ff;outline-offset:3px}
.hub-embedded .hub-global-chrome,.hub-embedded .hub-global-footer{display:none!important}
@media(max-width:800px){
  .hub-global-header nav[aria-label="Main navigation"]{flex-wrap:nowrap!important;
    overflow-x:auto!important;scrollbar-width:thin}
  .hub-global-header nav[aria-label="Main navigation"] a{white-space:nowrap}
  .hub-run-tabs{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:thin}
  .hub-run-tabs a{white-space:nowrap}
}
@media(max-width:650px){.hub-global-header{padding:18px 20px 10px!important}
  .hub-run-tabs{padding:6px 20px 12px}}
</style>
""".strip()

EMBED = """<script>
if (window.self !== window.top && new URLSearchParams(window.location.search).get("embed") === "1") {
  document.documentElement.classList.add("hub-embedded");
}
</script>"""


def _site_chrome(shell_fn, relative: Path, repository: str, source_sha: str):
    # Derive the header, active nav and provenance footer from the exact
    # same site template that every top-level page uses.
    outer = shell_fn("Verification test run", "", relative, repository, source_sha)
    header = re.search(r"<header>.*?</header>", outer, flags=re.DOTALL)
    footer = re.search(r"<footer>.*?</footer>", outer, flags=re.DOTALL)
    if header is None or footer is None:
        raise ValueError("site template does not define navigation and footer")
    return (header.group().replace("<header>", '<header class="hub-global-header">', 1),
            footer.group().replace("<footer>", '<footer class="hub-global-footer">', 1))


def decorate_run_pages(destination: Path, relative: Path, repository: str,
                       site_sha: str, *, shell_fn) -> None:
    """Normalize all linked report pages; reject unsupported standalone markup.

    Pages without a source-verified report never become a test PASS.
    Existing native report data, scripts, styles and local evidence paths
    remain byte-for-byte substrings of the original page where applicable.
    """
    destination = Path(destination)
    relative = Path(relative)
    available = [(name, label) for name, label in REPORTS
                 if (destination / name).is_file()]
    if not available:
        return
    for name, _ in available:
        file = destination / name
        html = file.read_text()
        if 'class="hub-global-chrome"' in html:
            raise ValueError("report page already decorated: " + name)
        page_relative = relative / name
        # Do not add fake links for missing reports. All targets retain a
        # back path to the same site's canonical Test Runs catalog.
        tabs = ('<nav class="hub-run-tabs" aria-label="Run report navigation">' +
                '<a href="' +
                escape(__import__("os").path.relpath("runs.html", start=relative.as_posix()).replace("\\", "/"),
                       quote=True) + '">All test runs</a>' +
                ''.join(
                    '<a href="' + escape(file_name, quote=True) + '"' +
                    (' aria-current="page"' if file_name == name else '') +
                    '>' + escape(label) + '</a>'
                    for file_name, label in available
                ) + '</nav>')
        if '<nav aria-label="Main navigation">' in html:
            # Already rendered by shell(), including selected variant views.
            if html.count("<main>") != 1:
                raise ValueError("site run page has ambiguous main content: " + name)
            html = html.replace("<main>", "<main>" + tabs, 1)
            file.write_text(html)
            continue
        if name == "test-flow.html" and "<main>" not in html:
            # The legacy trusted step renderer has a complete style/head
            # followed by top-level body content, but no main landmark.
            if html.count("</style>") != 1 or "<h1>" not in html:
                raise ValueError("unexpected test-flow page format")
            html = html.replace("</style>", "</style>\n<main>", 1).rstrip() + "\n</main>\n"
        if html.count("<main>") != 1 or html.count("</main>") != 1:
            raise ValueError("unsupported standalone run report: " + name)
        header, footer = _site_chrome(
            shell_fn, page_relative, repository, site_sha)
        # The first report 'header' is an internal AXI title, not global
        # site navigation. Inject the shared header outside its <main>.
        html = html.replace(
            "<main>", CHROME_STYLE + '\n<div class="hub-global-chrome">' +
            header + tabs + '</div>\n<main>', 1)
        html = html.replace(
            "</main>", "</main>\n" + footer + "\n" + EMBED, 1)
        file.write_text(html)
