#!/usr/bin/env python3
"""Browser smoke of automatic test-suite navigation and provenance-aware rows.

The inline synthetic run rows exercise UI behavior only; they are never
published or represented as actual regression evidence.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import tempfile

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/".tools/pages-site/runs.html"


def sample(target,workflow,sha="a"*40):
    protocol=("dfi" if "ddr4" in workflow.lower() else
              "pcie" if "pcie" in workflow.lower() else
              "ethernet" if "ethernet" in workflow.lower() else "axi4")
    source=("memory0.ddr0.dfi" if protocol=="dfi" else
            "pcie0.rx_req" if protocol=="pcie" else
            "ethernet0.gmii_tx" if protocol=="ethernet" else "compute0_local_data.cpu")
    operation=("act" if protocol=="dfi" else
               "mem_read" if protocol=="pcie" else
               "frame_tx" if protocol=="ethernet" else "read")
    fields=({"bank":2,"dfi_phase":0,"model_boundary":"controller_dfi"} if protocol=="dfi" else
            {"tag":"0x4","address":"0x4000","header_hex":"0x1122"} if protocol=="pcie" else
            {"dst_mac":"02:50:b6:00:00:22","ether_type":"0x0800","length_bytes":85}
            if protocol=="ethernet" else {"address":"0x13000000"})
    return {
        "protocol_links":{"capture_complete":True,"sources":[{
            "source":source,"protocol":protocol,"role":"target",
            "clock_domain":"clk","implementation":"test_fixture","count":1,
            "operations":{operation:1},"preview":[{
                "kind":"transaction","operation":operation,"id":"test:4",
                "source":source,"start_ps":1000,"end_ps":3000,
                "status":"complete","fields":fields}]}]},
        "target":target,"attempt":1,"engine":"cocotb-verilator","passed":True,
        "expected_failure":None,"axi":True,"observations":5,
        "protocols":["pcie","axi4"] if "pcie" in workflow.lower() else ["axi4"],
        "protocol_observations":5,"annotations":True,
        "expected_errors":0,"undeclared_errors":0,
        "source_sha":sha,"run_id":123,"recorded_at":"2026-11-06T00:00:00Z",
        "workflow":workflow,
        "workflow_url":"https://github.com/r987r/xezim-hello-world/actions/runs/123",
        "path":"runs/example/report.html",
    }


def main():
    html=PAGE.read_text()
    marker='<script type="application/json" id="site-data">'
    start=html.index(marker)+len(marker)
    end=html.index("</script>",start)
    data=json.loads(html[start:end])
    assert "chip-ethernet" in data["tests"]
    assert "chip-pcie-host" in data["tests"]
    # Exercise a deterministic synthetic dataset even when the main-branch
    # Pages build has already collected many real historical CI results.
    data["entries"]=[
        sample("chip-pcie-host","PCIe0 integrated test"),
        sample("chip-ethernet","Ethernet0 integrated test"),
        sample("chip-ddr4-real","DDR4 full-chip DFI test"),
        sample("chip-cpu-dma","PCIe0 supplemental CPU test"),
        sample("chip-cpu-dma","Full-chip CPU boot test"),
    ]
    embedded=json.dumps(data,separators=(",",":")).replace("<","\\u003c")
    page=html[:start]+embedded+html[end:]

    options=ChromeOptions()
    for flag in ("--headless=new","--no-sandbox","--disable-dev-shm-usage",
                 "--disable-gpu","--window-size=1365,900"):
        options.add_argument(flag)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"runs-fixture.html"
        path.write_text(page)
        with webdriver.Chrome(options=options) as driver:
            driver.get(path.as_uri())
            wait=WebDriverWait(driver,20)
            wait.until(lambda d: d.find_elements(By.CSS_SELECTOR,"#suite-summary button"))
            catalog=driver.find_element(By.ID,"catalog").text
            assert "chip-pcie-host" in catalog
            assert "chip-ethernet" in catalog
            assert "PASS" in driver.find_element(By.ID,"results").text

            driver.execute_script(
                """const f=document.getElementById("family");
                   f.value="PCIe";f.dispatchEvent(new Event("change"));""")
            wait.until(lambda d: "chip-pcie-host" in d.find_element(By.ID,"results").text)
            assert "chip-ethernet" not in driver.find_element(By.ID,"results").text
            # PCIe-filtered catalog legitimately contains the new combined\n            # chip-ethernet-ddr-pcie target. Exclude only the standalone\n            # chip-ethernet target, not its composite PCIe sibling.\n            assert not re.search(r"\\bchip-ethernet\\b(?!-)",\n                                 driver.find_element(By.ID,"catalog").text)
            assert "chip-pcie-host" in driver.find_element(By.ID,"catalog").text

            driver.execute_script(
                """const f=document.getElementById("family");
                   f.value="";f.dispatchEvent(new Event("change"));""")
            names=[row.find_element(By.TAG_NAME,"a").text
                   for row in driver.find_elements(By.CSS_SELECTOR,"#results tr")
                   if row.find_elements(By.TAG_NAME,"a")]
            assert names.count("chip-cpu-dma")==2, names
            assert "chip-pcie-host" in names and "chip-ethernet" in names

            driver.execute_script(
                """const q=document.getElementById("search");
                   q.value="ethernet";q.dispatchEvent(new Event("input"));""")
            assert "chip-ethernet" in driver.find_element(By.ID,"results").text
            assert "chip-pcie-host" not in driver.find_element(By.ID,"results").text
            # The main page, not a separate protocol report, must display
            # source-native TLP and GMII records with a run and protocol filter.
            driver.execute_script(
                """const q=document.getElementById("search");
                   q.value="";q.dispatchEvent(new Event("input"));""")
            driver.execute_script(
                """const e=[...document.querySelectorAll("#results tr")]
                   .find(n=>n.textContent.includes("chip-pcie-host"));
                   e.querySelector("button").click();""")
            wait.until(lambda d:"mem_read" in d.find_element(By.ID,"traffic-rows").text)
            assert "0x4000" in driver.find_element(By.ID,"traffic-rows").text
            assert "pcie" in driver.find_element(By.ID,"traffic-protocol").text
            driver.execute_script(
                """const sel=document.getElementById("traffic-run");
                   const found=[...sel.options].find(x=>x.textContent.includes("chip-ethernet"));
                   if(!found)throw new Error("missing Ethernet run");
                   sel.value=found.value;sel.dispatchEvent(new Event("change"));""")
            wait.until(lambda d:"frame_tx" in d.find_element(By.ID,"traffic-rows").text)
            assert "02:50:b6:00:00:22" in driver.find_element(By.ID,"traffic-rows").text
            assert "ethernet" in driver.find_element(By.ID,"traffic-protocol").text
            driver.execute_script(
                """const sel=document.getElementById("traffic-run");
                   const found=[...sel.options].find(x=>x.textContent.includes("chip-ddr4-real"));
                   if(!found)throw new Error("missing real-DDR fixture run");
                   sel.value=found.value;sel.dispatchEvent(new Event("change"));""")
            wait.until(lambda d:"act" in d.find_element(By.ID,"traffic-rows").text)
            assert "memory0.ddr0.dfi" in driver.find_element(By.ID,"traffic-rows").text
            assert "dfi" in driver.find_element(By.ID,"traffic-protocol").text
            assert "chip-ddr4-real" in driver.find_element(By.ID,"traffic-provenance").text
            print("PASS: unified Test Runs show source-native PCIe, Ethernet, DFI sample records")


if __name__=="__main__":
    main()
