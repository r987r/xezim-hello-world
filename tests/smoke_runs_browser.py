#!/usr/bin/env python3
"""Browser smoke of automatic test-suite navigation and provenance-aware rows.

The inline synthetic run rows exercise UI behavior only; they are never
published or represented as actual regression evidence.
"""
from __future__ import annotations

import csv
import gzip
import io
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
    # Two executions of the same target under one CI run, plus retained
    # historical captures without a canonical identity.
    ethernet_attempts=[data["entries"][1],sample("chip-ethernet","Ethernet0 integrated test","b"*40)]
    for attempt,entry in enumerate(ethernet_attempts,1):
        execution=f"ci-123-a{attempt}-012345abcdef"
        identity=f"verilator/soc-ethernet-mvp/network-frame-transfer/{execution}"
        route=f"runs/{identity}/report.html"
        entry.update(canonical_id=identity,canonical_url=route,attempt=attempt,
                     simulator="verilator",config_target="soc-ethernet-mvp",
                     testname="network-frame-transfer",execution_id=execution,path=route)
    data["entries"].append(ethernet_attempts[1])
    ethernet_attempts[1]['compressed_assets']={
        'protocol-transactions.json':'protocol-transactions.json.gz'}
    ethernet_identity=ethernet_attempts[0]["canonical_id"]
    ethernet_path=ethernet_attempts[0]["path"]
    manifest_name="selected-rtl-manifest.json"
    manifest_record={"path":manifest_name,"source_count":249}
    data["entries"][0].update(compiler_inputs=manifest_record,assets=[manifest_name])
    # A foreign manifest URL and an unarchived asset must not yield links.
    data["entries"][2].update(
        compiler_inputs=dict(manifest_record,path="https://example.com/foreign.json"),
        assets=[manifest_name])
    data["entries"][3].update(compiler_inputs=manifest_record,assets=[])
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
        for entry in ethernet_attempts:
            packed=entry.get("compressed_assets",{}).get("protocol-transactions.json")
            capture=(Path(tmp)/entry["path"]).with_name(packed or "protocol-transactions.json")
            capture.parent.mkdir(parents=True)
            source,=entry["protocol_links"]["sources"]
            original=json.dumps({
                "schema_version":1,"run":{"target":entry["target"]},
                "sources":[{"id":source["source"],"protocol":source["protocol"]}],
                "records":[dict(source["preview"][0],protocol=source["protocol"])],
            }).encode()
            capture.write_bytes(gzip.compress(original,mtime=0) if packed else original)
        report_root=Path(tmp)/"runs/example"
        report_root.mkdir(parents=True)
        (report_root/manifest_name).write_text(
            json.dumps({"scope":"synthetic browser fixture","source_count":249}))
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
            assert "Invocation selector: chip-pcie-host" in catalog
            assert "Invocation selector: chip-ethernet" in catalog
            assert data["test_names"]["chip-ethernet"] in catalog
            assert "PASS" in driver.find_element(By.ID,"results").text
            results=driver.find_element(By.ID,"results")
            canonical=results.find_element(By.LINK_TEXT,ethernet_identity)
            assert canonical.get_dom_attribute("href")==ethernet_path
            historical=results.find_element(
                By.XPATH,'.//a[normalize-space(.)="chip-pcie-host"]/..')
            assert "Historical run: canonical identity not archived" in historical.text
            assert "Canonical:" not in historical.text, "legacy row inferred a canonical name"
            headings=[element.text for element in driver.find_elements(By.CSS_SELECTOR,"table th")]
            assert not any("engine" in title.lower() for title in headings)
            # The full identity stays visible but wraps inside a narrow cell.
            driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width":390,"height":844,"deviceScaleFactor":1,"mobile":False,
            })
            assert driver.execute_script("""
                const e=arguments[0], style=getComputedStyle(e), box=e.getBoundingClientRect();
                return box.width<=innerWidth*0.5 && box.height>parseFloat(style.lineHeight)*1.5;
                """,canonical), "canonical link did not wrap at 390 px"
            driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})

            compiler_links=driver.find_elements(
                By.CSS_SELECTOR,'#results a[href$="selected-rtl-manifest.json"]')
            # Also catches an anchor on the missing or malformed rows.
            assert len(compiler_links)==1
            compiler_link=compiler_links[0]
            assert compiler_link.text=="Compiler manifest · 249 RTL sources"
            assert compiler_link.get_dom_attribute("href")=="runs/example/"+manifest_name
            assert not driver.find_elements(By.CSS_SELECTOR,'#results a[href*="foreign.json"]')
            driver.execute_script("arguments[0].click()",compiler_link)
            wait.until(lambda d:d.current_url.endswith("/runs/example/"+manifest_name))
            wait.until(lambda d:"synthetic browser fixture" in
                       d.find_element(By.TAG_NAME,"body").text)
            driver.back()
            wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,"#suite-summary button"))

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
            assert "chip-pcie-host" in names and ethernet_identity in names
            assert "chip-ethernet" not in names, "canonical ledger exposed a legacy alias"

            driver.execute_script(
                """const q=document.getElementById("search");
                   q.value="ethernet";q.dispatchEvent(new Event("input"));""")
            assert ethernet_identity in driver.find_element(By.ID,"results").text
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
            # The previously shared run query must still resolve the first
            # archived attempt, while showing its existing canonical identity.
            driver.get(fixture_url+"?run=123-1/chip-ethernet")
            wait.until(lambda d:"Showing full" in d.find_element(By.ID,"traffic-notice").text)
            assert ethernet_identity in driver.find_element(By.ID,"traffic-provenance").text

            def export(ext):
                # Capture the actual Blob from the button's download click;
                # the test needs no persistent browser download permission.
                return driver.execute_async_script("""
                    const id=arguments[0], done=arguments[arguments.length-1];
                    const click=HTMLAnchorElement.prototype.click;
                    HTMLAnchorElement.prototype.click=function(){
                        fetch(this.href).then(r=>r.text()).then(text=>done([this.download,text]));
                    };
                    try { document.getElementById(id).click(); }
                    finally { HTMLAnchorElement.prototype.click=click; }
                    """, "traffic-"+ext)

            def provenance(row):
                return row["canonical_id"],int(row["run_id"]),int(row["attempt"]),row["source_sha"]

            def expected(e):
                return e["canonical_id"],e["run_id"],e["attempt"],e["source_sha"]

            filename,body=export("json")
            assert filename=="traffic-"+ethernet_identity.replace("/","-")+".json"
            selected=json.loads(body)
            row,=selected["records"]
            assert selected["run"]==ethernet_identity and selected["preview"] is False
            assert provenance(row)==expected(ethernet_attempts[0])
            raw=driver.execute_async_script("""
                const path=arguments[0],done=arguments[arguments.length-1];
                fetch(path).then(r=>r.json()).then(done);
                """,ethernet_path.replace("report.html","protocol-transactions.json"))
            assert "canonical_id" not in raw["records"][0] and "attempt" not in raw["records"][0]

            driver.execute_script("""
                const sel=document.getElementById("traffic-run");
                sel.value="__all__";sel.dispatchEvent(new Event("change"));
                """)
            filename,body=export("csv")
            assert filename=="traffic-all-runs.csv"
            rows=list(csv.DictReader(io.StringIO(body)))
            assert {provenance(r) for r in rows if r["protocol"]=="ethernet"}=={
                expected(e) for e in ethernet_attempts}
            legacy=next(r for r in rows if r["protocol"]=="dfi")
            assert provenance(legacy)==("",123,1,"a"*40)
            assert legacy["legacy_target"]=="chip-ddr4-real"
            assert all(not r["legacy_target"] for r in rows if r["protocol"]=="ethernet")
            _,body=export("json")
            mixed=json.loads(body)
            assert mixed["preview"] is True and "run" not in mixed
            assert {provenance(r) for r in mixed["records"] if r["protocol"]=="ethernet"}=={
                expected(e) for e in ethernet_attempts}
            legacy=next(r for r in mixed["records"] if r["protocol"]=="dfi")
            assert legacy["canonical_id"] is None and legacy["legacy_target"]=="chip-ddr4-real"
            driver.execute_script("""
                const sel=document.getElementById("traffic-run");
                sel.value="123-2/chip-ethernet";sel.dispatchEvent(new Event("change"));
                """)
            wait.until(lambda d:"Showing full" in d.find_element(By.ID,"traffic-notice").text)
            assert ethernet_attempts[1]["canonical_id"] in driver.find_element(By.ID,"traffic-provenance").text
            assert driver.find_element(By.ID,"traffic-open-raw").text=="Download raw capture (.gz)"
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
            print("PASS: unified Test Runs preserve source-native records and single/mixed export provenance")


if __name__=="__main__":
    main()
