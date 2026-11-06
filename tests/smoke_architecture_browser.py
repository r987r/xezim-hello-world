#!/usr/bin/env python3
"""Visual browser smoke test of published self-contained hierarchical explorer.

Requires selenium and the Chrome/Chromedriver pair available on GitHub's
Ubuntu runner. Captures views for reviewer QA; validates actual SVG DOM
and drilled-down router structures, not just static HTML presence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

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
        # Synthetic monitor evidence checks the browser UI without publishing
        # fake CI records or relying on PR-preview historical run availability.
        with tempfile.TemporaryDirectory() as scratch:
            original=args.page.read_text()
            synthetic={
                'run_id':12345,'attempt':1,'target':'chip-pcie-host',
                'source_sha':'b'*40,'recorded_at':'2026-11-06T00:00:00Z',
                'passed':True,'workflow':'PCIe0 integrated test',
                'report_path':'runs/12345/chip-pcie-host/protocols.html',
                'axi_report_path':'runs/12345/chip-pcie-host/report.html',
                'raw_path':'runs/12345/chip-pcie-host/protocol-transactions.json',
                'links':{'capture_complete':True,'sources':[
                    {'source':'pcie0.rx_req','protocol':'pcie',
                     'role':'target','clock_domain':'soc_single_clock',
                     'implementation':'upstream_pcieifframe','count':1,
                     'operations':{'mem_read':1},
                     'preview':[{'kind':'transaction','operation':'mem_read',
                                 'id':'02:3','start_ps':1000,'end_ps':3000,
                                 'status':'complete',
                                 'fields':{'tag':'0x3','address':'0x4000',
                                           'length_dw':1,'header_hex':'0x123'}}]}]}}
            marker='<script type="application/json" id="arch-embedded-protocol-links">'
            start=original.index(marker)+len(marker)
            end=original.index('</script>',start)
            copied=Path(scratch)/'explorer.html'
            copied.write_text(original[:start]+json.dumps([synthetic])+
                              original[end:])
            driver.get(copied.as_uri())
            wait.until(lambda d:"SYSTEM-ON-CHIP" in d.find_element(By.ID,"arch-svg").text)
            dblclick_by_label("pcie0")
            wait.until(lambda d:"pcie0" in d.find_element(By.ID,"arch-crumbs").text.lower())
            dblclick_by_label("pcie0.ip")
            wait.until(lambda d:"IP COMPOSITION" in d.find_element(By.ID,"arch-svg").text)
            traffic=driver.find_element(By.ID,"arch-link-traffic")
            assert traffic.is_displayed(), "verified TLP traffic inspector hidden"
            assert "mem_read" in driver.find_element(By.ID,"arch-traffic-rows").text
            assert "0x4000" in driver.find_element(By.ID,"arch-traffic-rows").text
            detail=driver.find_element(By.CSS_SELECTOR,
                "#arch-traffic-actions a").get_attribute("href")
            assert "protocol=pcie" in detail and "source=pcie0.rx_req" in detail
            driver.save_screenshot(str(args.screenshots/"04-pcie-verified-tlp-link.png"))
        print("PASS: architecture RTL drilldown, PCIe monitor link and bounded real-evidence UI")



if __name__=="__main__":
    main()
