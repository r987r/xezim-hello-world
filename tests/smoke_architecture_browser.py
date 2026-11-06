#!/usr/bin/env python3
"""Visual browser smoke test of published self-contained hierarchical explorer.

Requires selenium and the Chrome/Chromedriver pair available on GitHub's
Ubuntu runner. Captures views for reviewer QA; validates actual SVG DOM
and drilled-down router structures, not just static HTML presence.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page",type=Path,default=Path(".tools/pages-site/explorer.html"))
    parser.add_argument("--screenshots",type=Path,default=Path(".tools/architecture-screenshots"))
    args=parser.parse_args()
    args.screenshots.mkdir(parents=True,exist_ok=True)
    options=ChromeOptions()
    for flag in ("--headless=new","--no-sandbox","--disable-dev-shm-usage",
                 "--disable-gpu","--window-size=1600,1000"):
        options.add_argument(flag)
    with webdriver.Chrome(options=options) as driver:
        driver.get(args.page.resolve().as_uri())
        wait=WebDriverWait(driver,20)
        wait.until(lambda d:"SYSTEM-ON-CHIP" in d.find_element(By.ID,"arch-svg").text)
        assert "GLOBAL FABRIC" in driver.find_element(By.ID,"arch-svg").text
        assert "COMPUTE0" in driver.find_element(By.ID,"arch-svg").text
        assert "MEMORY0" in driver.find_element(By.ID,"arch-svg").text
        # The same generated topology must reflect the *selected* RTL/test
        # actor manifest, not a stale boot-only DMA placeholder.
        assert driver.find_element(By.ID,"arch-profile").get_attribute("value")=="chip-dma"
        assert "Real PULP iDMA RTL" in driver.find_element(By.ID,"arch-svg").text
        assert "AXI RAM model" in driver.find_element(By.ID,"arch-svg").text
        driver.execute_script(
            """const p=document.getElementById('arch-profile');
               p.value='chip-boot';p.dispatchEvent(new Event('change',{bubbles:true}));""")
        assert "AXI verification BFM" in driver.find_element(By.ID,"arch-svg").text
        driver.execute_script(
            """const p=document.getElementById('arch-profile');
               p.value='chip-dma';p.dispatchEvent(new Event('change',{bubbles:true}));""")
        driver.save_screenshot(str(args.screenshots/"01-full-chip.png"))

        def dblclick_by_label(label):
            driver.execute_script(
                """const node=[...document.querySelectorAll('#arch-svg .arch-click')]
                     .find(n=>n.getAttribute('aria-label')===arguments[0]);
                   if(!node)throw new Error('not clickable: '+arguments[0]);
                   node.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));""",label)

        dblclick_by_label("compute0")
        wait.until(lambda d:"compute0" in d.find_element(By.ID,"arch-crumbs").text.lower() and "SUBSYSTEM COMPOSITION" in d.find_element(By.ID,"arch-svg").text)
        assert "LOCAL FABRICS" in driver.find_element(By.ID,"arch-svg").text
        driver.save_screenshot(str(args.screenshots/"02-compute0-composition.png"))

        # An ordinary IP must open its nested compiler-parsed implementation.
        dblclick_by_label("compute0.cpu")
        wait.until(lambda d:"IP COMPOSITION" in d.find_element(By.ID,"arch-svg").text)
        assert "picorv32_cpu_adapter" in driver.find_element(By.ID,"arch-svg").text, driver.find_element(By.ID,"arch-svg").text[:1500]
        driver.save_screenshot(str(args.screenshots/"03-compute0-cpu-ip.png"))
        driver.execute_script(
            """const b=[...document.querySelectorAll("#arch-crumbs button")]
               .find(b=>b.textContent==="compute0");if(!b)throw new Error("missing breadcrumb");b.click();""")
        dblclick_by_label("compute0_local_data")
        wait.until(lambda d:"compute0_local_data" in d.find_element(By.ID,"arch-crumbs").text and "FLOONOC ROUTERS" in d.find_element(By.ID,"arch-svg").text)
        mesh=driver.find_element(By.ID,"arch-svg").text
        assert "9 routers" in mesh
        assert len(driver.find_elements(By.XPATH,
            "//*[name()='svg' and @id='arch-svg']//*[name()='text' and text()='ROUTER']"))==9
        driver.save_screenshot(str(args.screenshots/"03-compute0-data-mesh.png"))

        driver.execute_script(
            """const e=document.getElementById('ex-endpoint');
               e.value='compute0_local_data.cpu';
               e.dispatchEvent(new Event('change',{bubbles:true}));""")
        driver.execute_script("document.getElementById('arch-signals').open=true")
        wait.until(lambda d: "awaddr" in d.find_element(By.ID,"ex-signal-rows").text)
        rows=driver.find_element(By.ID,"ex-signal-rows").text
        assert "awaddr" in rows and "araddr" in rows and "rdata" in rows
        print("PASS: browser rendered all three hierarchy levels, 9 real XY routers, and AXI signal details")


if __name__=="__main__":
    main()
