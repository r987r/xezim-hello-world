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
        directory=driver.find_element(By.ID,"arch-directory")
        directory_labels=directory.text
        for subsystem in ("compute0","compute1","memory0","pcie0","ethernet0"):
            assert subsystem in directory_labels, f"missing subsystem directory entry: {subsystem}"
        for network in ("global_data","global_config","compute0_local_data",
                        "compute0_local_config","pcie0_local_data","ethernet0_local_config"):
            assert network in directory_labels, f"missing NoC directory entry: {network}"
        # Exercise directory navigation, not just presence of labels.
        driver.execute_script("""
            const b=[...document.querySelectorAll('#arch-directory button')]
              .find(x=>x.textContent.includes('memory0_local_data'));
            if(!b)throw new Error('missing memory-local NoC shortcut');
            b.click();
        """)
        assert "memory0_local_data" in driver.find_element(By.ID,"arch-crumbs").text
        driver.execute_script("""
            document.querySelector('#arch-crumbs button').click();
        """)
        assert "GLOBAL FABRIC" in driver.find_element(By.ID,"arch-svg").text
        assert "COMPUTE0" in driver.find_element(By.ID,"arch-svg").text
        assert "MEMORY0" in driver.find_element(By.ID,"arch-svg").text
        # The overview must not be tiny merely because the tall diagram
        # cannot fit the viewport height. The viewport scrolls vertically.
        visible_width=driver.execute_script(
            "return document.getElementById('arch-svg').getBoundingClientRect().width")
        assert visible_width>1100, f"desktop architecture scaled too small: {visible_width}"
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
            synthetic_ddr={
                'run_id':67890,'attempt':1,'target':'ddr4-standalone',
                'source_sha':'c'*40,'recorded_at':'2026-11-06T00:01:00Z',
                'passed':True,'workflow':'DDR4 verified foundation',
                'report_path':'runs/67890/ddr4-standalone/protocols.html',
                'axi_report_path':'runs/67890/ddr4-standalone/report.html',
                'raw_path':'runs/67890/ddr4-standalone/protocol-transactions.json',
                'links':{'capture_complete':True,'sources':[
                    {'source':'memory0.ddr0.dfi','protocol':'dfi',
                     'role':'link','clock_domain':'ddr_source_clk',
                     'implementation':'litedram_flat_dfi_probe','count':2,
                     'operations':{'rd':1,'wr':1},
                     'preview':[{'kind':'event','operation':'rd',
                                 'id':None,'start_ps':45000,'end_ps':45000,
                                 'status':'observed',
                                 'fields':{'bank':2,'dfi_phase':3,'address':128}}]}]}}
            copied.write_text(original[:start]+json.dumps([synthetic,synthetic_ddr])+
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
            driver.get(copied.as_uri())
            wait.until(lambda d:"SYSTEM-ON-CHIP" in d.find_element(By.ID,"arch-svg").text)
            dblclick_by_label("memory0")
            wait.until(lambda d:"memory0" in d.find_element(By.ID,"arch-crumbs").text.lower())
            dblclick_by_label("memory0.ddr0")
            wait.until(lambda d: d.find_element(By.ID,"arch-link-traffic").is_displayed())
            assert "ddr_source_clk" in driver.find_element(By.ID,"arch-traffic-context").text
            assert "rd" in driver.find_element(By.ID,"arch-traffic-rows").text
            assert "dfi" in driver.find_element(By.ID,"arch-traffic-source").text
            detail=driver.find_element(By.CSS_SELECTOR,
                "#arch-traffic-actions a").get_attribute("href")
            assert "protocol=dfi" in detail and "source=memory0.ddr0.dfi" in detail
            driver.save_screenshot(str(args.screenshots/"05-ddr-nested-dfi-link.png"))

        # Verify mobile visibility of the same canonical generated SVG.
        # This is a browser layout test, not a second hand-authored image.
        driver.set_window_size(400,850)
        homepage=args.page.resolve().parent/"index.html"
        driver.get(homepage.as_uri())
        wait.until(lambda d:d.execute_script(
            "return document.querySelector('.topology-pan img')?.naturalWidth>0"))
        dims=driver.execute_script("""
            const wrap=document.querySelector('.topology-pan');
            const img=wrap.querySelector('img');
            return {scroll:wrap.scrollWidth,client:wrap.clientWidth,
                    image:img.getBoundingClientRect().width};
        """)
        assert dims["scroll"]>dims["client"], "mobile topology not horizontally pannable"
        assert dims["image"]>=1050, "mobile topology shrank its connection strokes"
        driver.save_screenshot(str(args.screenshots/"06-overview-topology-mobile.png"))
        print("PASS: architecture wiring, readable desktop zoom, mobile-pan topology and drilldown")



if __name__=="__main__":
    main()
