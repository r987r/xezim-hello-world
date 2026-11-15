#!/usr/bin/env python3
"""Browser smoke: project picker navigation, mobile layout, evidence isolation."""
from __future__ import annotations

import argparse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path(".tools/pages-site"))
    parser.add_argument("--screenshots", type=Path,
                        default=Path(".tools/architecture-screenshots"))
    args = parser.parse_args()
    site = args.site.resolve()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    options = ChromeOptions()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                 "--disable-gpu", "--window-size=1500,1000"):
        options.add_argument(flag)
    with webdriver.Chrome(options=options) as browser:
        browser.get((site / "index.html").as_uri())
        assert "Choose a chip project" in browser.find_element(By.TAG_NAME, "h1").text
        cards = browser.find_elements(By.CSS_SELECTOR, ".project-card")
        assert len(cards) == 2, "project picker missing independent projects"
        assert all(c.is_displayed() for c in cards)
        browser.save_screenshot(str(args.screenshots / "07-project-picker-desktop.png"))
        b = next(c for c in cards if "Ethernet / CPU" in c.text)
        b.click()
        assert "/projects/xezim_ethernet_cpu_ddr_pcie/index.html" in browser.current_url
        assert "memory0.ddr0" in browser.find_element(By.TAG_NAME, "main").text
        assert "memory0.hbm0" not in browser.page_source
        browser.find_element(By.LINK_TEXT, "Architecture").click()
        assert "l0_ethernet_compute" in browser.find_element(By.TAG_NAME, "main").text
        assert "l1_compute_pcie" in browser.find_element(By.TAG_NAME, "main").text
        assert "Global control FlooNoC" in browser.find_element(By.TAG_NAME, "main").text
        browser.find_element(By.LINK_TEXT, "Test runs").click()
        assert "No project-qualified run evidence" in browser.find_element(By.TAG_NAME, "main").text
        assert "Recorded PASS" not in browser.page_source
        browser.set_window_size(390, 840)
        browser.get((site / "index.html").as_uri())
        assert browser.find_element(By.CSS_SELECTOR, ".project-grid").is_displayed()
        assert all(c.is_displayed() for c in browser.find_elements(By.CSS_SELECTOR, ".project-card"))
        browser.save_screenshot(str(args.screenshots / "08-project-picker-mobile.png"))
        browser.get((site / "projects/xezim_soc_dv/index.html").as_uri())
        assert "compute1" in browser.find_element(By.TAG_NAME, "main").text
        browser.find_element(By.LINK_TEXT, "Generated topology").click()
        assert "/topology.html" in browser.current_url
        print("PASS project picker desktop/mobile, independent topology and run evidence")


if __name__ == "__main__":
    main()
