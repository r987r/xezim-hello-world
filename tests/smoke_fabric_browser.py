#!/usr/bin/env python3
"""Exercise Fabric Explorer JavaScript in a real browser (desktop AND mobile).

PR previews contain no validated live timing. In preview mode, inject a strictly
local, visibly synthetic measurement into the published structural report to
catch JS scope/rendering errors without publishing or asserting fake RTL proof.
On main, consume actual source-qualified, offline-collected measurements.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def embedded(html: str) -> tuple[dict, int, int]:
    start_tag = '<script type="application/json" id="fabric-data">'
    start = html.index(start_tag) + len(start_tag)
    end = html.index("</script>", start)
    return json.loads(html[start:end]), start, end


def fixture_html(html: str) -> str:
    """Synthetic frontend-only timing exercises both renderer paths."""
    report, start, end = embedded(html)
    table = copy.deepcopy(report["latency_table"])
    row = next((r for r in table["rows"] if r.get("route_id")
                and r.get("plane") == "data"), None)
    if row is None:
        raise AssertionError("generated Fabric has no reachable data path")
    stats = {
        "min_cycles": 4, "avg_cycles": 5.5, "max_cycles": 7,
        "n": 3, "reference_clock_period_ps": 10000,
        "run_sha": "f" * 40, "source_equivalence": "fixture_not_real_evidence",
    }
    row["end_to_end_cycles"]["read"] = stats
    table["evidence_coverage"] = {
        "status": "synthetic_frontend_fixture_not_published",
        "current_measured_routes": 1, "current_stage_observations": 1,
        "historical_observations": 0, "total_routes": 64,
    }
    table["reference_clock"] = {
        "measured_period_ps": 10000, "measured_frequency_hz": 100000000,
        "signal": "clk_i", "domain": "soc_single_clock",
    }
    report["latency_table"] = table
    report["latency_scopes"] = {"synthetic_browser_fixture": table}
    payload = json.dumps(report, separators=(",", ":"), allow_nan=False)
    return html[:start] + payload.replace("<", "\\u003c") + html[end:]


def exercise(driver, require_measurement: bool) -> None:
    errors = []
    driver.get_log("browser")  # clear prior page's messages
    wait = WebDriverWait(driver, 25)
    wait.until(lambda d: d.find_elements(By.CSS_SELECTOR,
                                        "#fabric-latency-table tbody tr"))
    summary = driver.find_element(By.ID, "fabric-evidence-coverage").text
    if not summary:
        raise AssertionError("Fabric JS never rendered coverage")
    if require_measurement:
        assert "source-verified routes measured" in summary, summary
        assert "Observed simulation reference:" in driver.find_element(
            By.ID, "fabric-reference-clock").text
        rows = driver.find_elements(By.CSS_SELECTOR,
                                    "#fabric-latency-table .metric-line")
        assert any(" / " in x.text and "n=" in x.text for x in rows), (
            "desktop Fabric table contains no actual numerical min/avg/max")
    for entry in driver.get_log("browser"):
        if entry.get("level") == "SEVERE":
            errors.append(entry.get("message"))
    assert not errors, "Fabric desktop JS exception: " + repr(errors)
    driver.set_window_size(390, 850)
    driver.refresh()
    wait.until(lambda d: d.find_elements(By.CSS_SELECTOR,
                                        "#fabric-mobile-routes details"))
    if require_measurement:
        visible = driver.find_elements(By.CSS_SELECTOR,
                                       "#fabric-mobile-routes .fabric-mobile-metric-value")
        assert any(" / " in cell.text for cell in visible), (
            "mobile Fabric cards contain no numerical min/avg/max")
    for entry in driver.get_log("browser"):
        if entry.get("level") == "SEVERE":
            errors.append(entry.get("message"))
    assert not errors, "Fabric mobile JS exception: " + repr(errors)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=Path,
                        default=Path(".tools/pages-site/fabric.html"))
    parser.add_argument("--main-evidence", action="store_true",
                        help="require actual current-source measured values, no fixtures")
    args = parser.parse_args()
    source = args.page.read_text(encoding="utf-8")
    original, _, _ = embedded(source)
    coverage = original["latency_table"]["evidence_coverage"]
    # For main, fail instead of falsely passing the deployment without
    # source-qualified measurements. For a PR, test rendering with a mock.
    if args.main_evidence:
        assert coverage["current_measured_routes"] > 0, (
            "main Fabric report lacks current source-qualified measurement")
        html = source
    else:
        html = fixture_html(source)
    options = ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                 "--disable-gpu", "--window-size=1400,920"):
        options.add_argument(flag)
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    with tempfile.TemporaryDirectory(prefix="fabric-browser-") as temp:
        page = Path(temp) / "fabric.html"
        page.write_text(html, encoding="utf-8")
        with webdriver.Chrome(options=options) as browser:
            browser.set_window_size(1400, 920)
            exercise(browser, True)
            print("PASS Fabric Explorer actual browser: desktop/mobile numerical "
                  "latency, clock, coverage and zero uncaught JS errors "
                  + ("(current-source evidence)" if args.main_evidence
                     else "(synthetic local UI fixture; not RTL proof)"))


if __name__ == "__main__":
    main()
