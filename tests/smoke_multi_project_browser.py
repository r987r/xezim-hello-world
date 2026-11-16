#!/usr/bin/env python3
"""Catalog-driven browser smoke: project picker, navigation, and evidence isolation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path(".tools/pages-site"))
    parser.add_argument("--screenshots", type=Path,
                        default=Path(".tools/architecture-screenshots"))
    args = parser.parse_args()
    site = args.site.resolve()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    catalog = yaml.safe_load(
        Path("config/projects/catalog.yaml").read_text())["projects"]
    assert catalog
    options = ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                 "--disable-gpu", "--window-size=1500,1000"):
        options.add_argument(flag)
    with webdriver.Chrome(options=options) as browser:
        browser.get((site / "index.html").as_uri())
        assert "Choose a chip project" in browser.find_element(By.TAG_NAME, "h1").text
        cards = browser.find_elements(By.CSS_SELECTOR, ".project-card")
        assert len(cards) == len(catalog), "project picker differs from catalog"
        assert all(c.is_displayed() for c in cards)
        browser.save_screenshot(str(args.screenshots / "07-project-picker-desktop.png"))
        filter_box = browser.find_element(By.ID, "project-filter")
        filter_box.send_keys(catalog[-1]["id"])
        assert len(browser.find_elements(
            By.CSS_SELECTOR, ".project-card:not([hidden])")) == 1
        filter_box.send_keys(Keys.CONTROL, 'a')
        filter_box.send_keys(Keys.BACKSPACE)
        assert len(browser.find_elements(
            By.CSS_SELECTOR, ".project-card:not([hidden])")) == len(catalog)

        for item in catalog:
            pid = item["id"]
            source = yaml.safe_load(Path(item["config"]).read_text())
            expected = site / "projects" / pid
            project_json = json.loads((expected / "data/project.json").read_text())
            assert project_json["id"] == pid
            assert project_json["config"] == item["config"]

            browser.get((expected / "index.html").as_uri())
            assert item["title"] in browser.find_element(By.TAG_NAME, "h1").text
            assert source["memory_targets"][0]["name"] in (
                browser.find_element(By.TAG_NAME, "main").text)
            browser.find_element(
                By.CSS_SELECTOR, 'main .actions a[href="architecture.html"]').click()
            assert browser.current_url.endswith("/projects/" + pid + "/architecture.html")
            for selector in ("#arch-h-tree", "#arch-h-crumbs", "#arch-h-filter",
                             "#arch-h-children", "#arch-h-svg", "#arch-h-plane",
                             "#arch-h-fit", "#arch-h-graph-status"):
                assert browser.find_element(By.CSS_SELECTOR, selector).is_displayed(), selector
            graph = browser.find_element(By.ID, "arch-h-svg")
            assert len(graph.find_elements(By.CSS_SELECTOR, ".arch-h-svg-node")) >= len(
                source["subsystems"])
            # The requested visual composition must be BOXES inside the
            # chip-level subsystem surfaces, not merely a textual subtitle.
            previews = graph.find_elements(
                By.CSS_SELECTOR, '.arch-h-svg-node [data-component-box]')
            assert previews, (pid, "chip diagram lacks nested composition boxes")
            assert all(rect.size["width"] >= 70 and rect.size["height"] >= 20
                       for rect in previews)
            assert "connections" in browser.find_element(
                By.ID, "arch-h-graph-status").text
            browser.save_screenshot(str(args.screenshots / ("09-" + pid + "-chip.png")))
            if item.get("architecture_explorer"):
                assert browser.find_element(
                    By.PARTIAL_LINK_TEXT, "detailed generated RTL")
            # Exact same diagram path on every project: chip -> selected
            # subsystem -> actual FlooGen NoC -> router -> attached NI.
            first_sub = source["subsystems"][0]["name"]
            browser.find_element(
                By.CSS_SELECTOR, '#arch-h-svg .arch-h-svg-node[aria-label="Explore '+first_sub+'"]').click()
            assert "local FlooNoCs" in browser.find_element(
                By.ID, "arch-h-graph-status").text
            # Drill-down composition has independently clickable rectangular
            # IP/memory and local FlooNoC nodes.
            composed = browser.find_element(By.ID, "arch-h-svg")
            assert composed.find_elements(
                By.CSS_SELECTOR, '.arch-h-svg-node[data-arch-ref^="noc:"] rect')
            assert composed.find_elements(
                By.CSS_SELECTOR, '.arch-h-svg-node[data-arch-ref^="ip:"] rect, '
                                 '.arch-h-svg-node[data-arch-ref^="profile:"] rect, '
                                 '.arch-h-svg-node[data-arch-ref^="property:"] rect')
            browser.save_screenshot(str(args.screenshots / ("10-" + pid + "-subsystem.png")))
            assert browser.find_elements(
                By.CSS_SELECTOR, '#arch-h-svg .arch-h-svg-node[data-arch-ref^="noc:"]')
            browser.find_elements(
                By.CSS_SELECTOR, '#arch-h-svg .arch-h-svg-node[data-arch-ref^="noc:"]')[0].click()
            assert "router slots" in browser.find_element(
                By.ID, "arch-h-graph-status").text
            browser.save_screenshot(str(args.screenshots / ("11-" + pid + "-noc.png")))
            assert browser.find_elements(
                By.CSS_SELECTOR, '#arch-h-svg .arch-h-svg-node[data-arch-ref^="router:"]')
            browser.find_elements(
                By.CSS_SELECTOR, '#arch-h-svg .arch-h-svg-node[data-arch-ref^="router:"]')[0].click()
            assert "NI attachments" in browser.find_element(
                By.ID, "arch-h-graph-status").text
            browser.save_screenshot(str(args.screenshots / ("12-" + pid + "-router.png")))
            assert len(browser.find_elements(
                By.CSS_SELECTOR, "#arch-h-diagram-crumbs button")) >= 3
            browser.find_element(By.CSS_SELECTOR, "#arch-h-diagram-crumbs button").click()
            assert "connections" in browser.find_element(
                By.ID, "arch-h-graph-status").text
            for link in source["networks"].get("direct_data", {}).get("links", []):
                finder = browser.find_element(By.ID, "arch-h-filter")
                finder.clear()
                finder.send_keys(link["name"])
                matches = browser.find_elements(By.CSS_SELECTOR, '#arch-h-tree button')
                assert any(link["name"] in el.text for el in matches)
                next(el for el in matches if link["name"] in el.text).click()
                assert link["name"] in browser.find_element(By.ID, "arch-h-title").text
                assert link["endpoints"][0] in browser.find_element(
                    By.ID, "arch-h-facts").text
            finder = browser.find_element(By.ID, "arch-h-filter")
            finder.clear()
            finder.send_keys(source["subsystems"][0]["name"])
            assert source["subsystems"][0]["name"] in (
                browser.find_element(By.ID, "arch-h-tree").text)
            Select(browser.find_element(By.ID, "arch-h-plane")).select_by_value("data")
            graph_status = browser.find_element(By.ID, "arch-h-graph-status").text
            assert "connections" in graph_status, (pid, graph_status,
                browser.find_element(By.ID, "arch-h-diagram-crumbs").text)
            browser.find_element(By.ID, "arch-h-fit").click()
            browser.get((expected / "address-map.html").as_uri())
            for target in source["memory_targets"]:
                assert target["name"] in browser.find_element(By.TAG_NAME, "main").text

            browser.get((expected / "files.html").as_uri())
            content = browser.find_element(By.TAG_NAME, "main").text
            assert item["config"] in content
            if item["qualification"] == "generated_default":
                assert item["generated_source"] in content
                assert browser.find_elements(By.CSS_SELECTOR,
                    'a[href="../../' + item["generated_source"] + '"]')
            elif item["qualification"] == "ci_generated_compiled":
                assert "chip/soc_top.sv" in content
                assert "chip/sources.f" in content
                assert "project-compile.yml" in browser.page_source
            else:
                assert "chip/soc_top.sv" not in content

            browser.get((expected / "runs.html").as_uri())
            if not project_json["runs"]:
                assert "No project-qualified run evidence" in (
                    browser.find_element(By.TAG_NAME, "main").text)
                assert "Recorded PASS" not in browser.page_source

        browser.set_window_size(390, 840)
        # Mobile must show boxed subsystem contents within the visible
        # diagram width; previously the 1030px two-column layout hid NoCs.
        for item in catalog:
            source = yaml.safe_load(Path(item["config"]).read_text())
            pid = item["id"]
            browser.get((site / "projects" / pid / "architecture.html").as_uri())
            first_sub = source["subsystems"][0]["name"]
            browser.find_element(
                By.CSS_SELECTOR, '#arch-h-svg .arch-h-svg-node[aria-label="Explore '+first_sub+'"]').click()
            viewport = browser.find_element(By.ID, "arch-h-viewport")
            cards = browser.find_elements(
                By.CSS_SELECTOR, '#arch-h-svg .arch-h-svg-node[data-arch-ref^="noc:"]')
            assert cards, (pid, "mobile composition missing local NoC boxes")
            bounds = viewport.rect
            for card in cards:
                rect = card.rect
                assert rect["x"] + rect["width"] <= bounds["x"] + bounds["width"] + 30, (
                    pid, "NoC box off mobile viewport", rect, bounds)
            browser.save_screenshot(
                str(args.screenshots / ("13-" + pid + "-subsystem-mobile.png")))
        browser.get((site / "index.html").as_uri())
        assert browser.find_element(By.CSS_SELECTOR, ".project-grid").is_displayed()
        assert all(c.is_displayed() for c in browser.find_elements(
            By.CSS_SELECTOR, ".project-card"))
        browser.save_screenshot(str(args.screenshots / "08-project-picker-mobile.png"))
        print("PASS catalog-sized project picker, desktop/mobile, sources and run isolation")


if __name__ == "__main__":
    main()
