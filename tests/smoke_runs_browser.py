#!/usr/bin/env python3
"""Browser smoke of automatic test-suite navigation and provenance-aware rows.

The inline synthetic run rows exercise UI behavior only; they are never
published or represented as actual regression evidence.
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import tempfile

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/".tools/pages-site/runs.html"


@contextmanager
def serve_fixture(directory: Path):
    """Use the same HTTP navigation semantics as Pages, never file:// links.

    Chrome can render a file:// landing page but restrict clicks to sibling
    local files. That makes a click-through smoke fail without testing the
    deployed site's navigation at all.
    """
    class QuietHTTP(SimpleHTTPRequestHandler):
        def log_message(self, _format, *args):
            pass

    with ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHTTP, directory=str(directory))
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/runs.html"
        finally:
            server.shutdown()
            thread.join(timeout=5)




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
        # The synthetic list links to a synthetic source-attested run page.
        # This exercises the real click-through path without inventing CI PASS.
        from sys import path as module_path
        module_path.insert(0,str(ROOT/"tools"))
        from publish_site import shell
        from run_page_chrome import decorate_run_pages
        path=Path(tmp)/"runs.html"
        path.write_text(page)
        report_root=Path(tmp)/"runs/example"
        report_root.mkdir(parents=True)
        (report_root/"report.html").write_text(
            '<html><style>header{display:flex}</style><main>'
            '<header><h1>AXI Run Explorer</h1></header>'
            '<p id="synthetic-observations">Synthetic browser fixture only</p>'
            '</main></html>')
        (report_root/"protocols.html").write_text(
            '<html><main><h1>Protocol Run Explorer</h1></main></html>')
        decorate_run_pages(report_root,Path("runs/example"),
                           "r987r/xezim-hello-world","a"*40,shell_fn=shell)
        with serve_fixture(Path(tmp)) as fixture_url, webdriver.Chrome(options=options) as driver:
            driver.get(fixture_url)
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
            # A combined chip-ethernet-ddr-pcie target belongs to PCIe.
            # Exclude only the standalone Ethernet target.
            assert not re.search(r"\bchip-ethernet\b(?!-)",
                                 driver.find_element(By.ID,"catalog").text)
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
            # Clicking the actual run link must preserve hub chrome and the
            # same-site return path, unlike the old standalone HTML reports.
            report_link=driver.find_element(
                By.CSS_SELECTOR, '#results a[href="runs/example/report.html"]')
            assert report_link.get_attribute("href").endswith(
                "/runs/example/report.html"), "unexpected run report destination"
            # Execute the real anchor's click handler rather than relying on a
            # viewport-dependent WebDriver pointer hit in the scrollable
            # results table. A click must still navigate to the linked page;
            # never substitute driver.get() or mark a failed navigation PASS.
            driver.execute_script("arguments[0].click()", report_link)
            expected="/runs/example/report.html"
            def entered_report(d):
                for handle in d.window_handles:
                    d.switch_to.window(handle)
                    if d.current_url.endswith(expected):
                        return True
                return False
            try:
                wait.until(entered_report)
            except Exception as exc:
                raise AssertionError(
                    "Test Runs report link did not navigate; "
                    f"windows={[(h, driver.switch_to.window(h) or driver.current_url) for h in driver.window_handles]} "
                    f"expected suffix={expected}"
                ) from exc
            wait.until(lambda d: "AXI Run Explorer" in d.find_element(By.TAG_NAME,"main").text)
            assert driver.find_element(By.CSS_SELECTOR,
                '.hub-global-header .brand').text=="SoC / verification hub"
            assert driver.find_element(By.CSS_SELECTOR,
                '.hub-global-header nav a[aria-current="page"]').text=="Test runs"
            assert driver.find_element(By.CSS_SELECTOR,
                '.hub-run-tabs a[aria-current="page"]').text=="Run overview"
            assert "Synthetic browser fixture only" in driver.find_element(By.TAG_NAME,"main").text
            driver.find_element(By.CSS_SELECTOR,'.hub-run-tabs a[href="protocols.html"]').click()
            wait.until(lambda d: "Protocol Run Explorer" in d.find_element(By.TAG_NAME,"main").text)
            assert driver.find_element(By.CSS_SELECTOR,
                '.hub-run-tabs a[aria-current="page"]').text=="Protocol traffic"
            driver.find_element(By.CSS_SELECTOR,'.hub-run-tabs a[href="../../runs.html"]').click()
            wait.until(lambda d:"test runs" in d.find_element(By.TAG_NAME,"h1").text.lower())
            assert driver.find_element(By.ID,"catalog")
            print("PASS: Test Runs click-through preserves global nav, protocol tabs and same-site back path")
            print("PASS: unified Test Runs show source-native PCIe, Ethernet, DFI sample records")


if __name__=="__main__":
    main()
