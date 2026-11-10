#!/usr/bin/env python3
"""Post-deploy HTTP gate for the public CSR explorer on GitHub Pages.

Unlike a PR preview, this must fetch the actual deployed Pages URLs and
confirm the tested source SHA and source-qualified DDR map are published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request


def validate(site, address_html, coverage, ddr, dma_header=None):
    if not isinstance(site, dict) or site.get("source_sha") != validate.expected_sha:
        raise ValueError("public Pages site source SHA is not the deployed main commit")
    for fragment in (
        'id="am-csr-browser"',
        "source-only reference(s)",
        'id="ddr-csr-variants-data"',
        "data/csr-source-coverage.json",
    ):
        if fragment not in address_html:
            raise ValueError("published CSR browser missing " + fragment)
    expected_dma=site.get("production_dma_header_sha256")
    if expected_dma is not None:
        if (not isinstance(expected_dma, str) or len(expected_dma)!=64
                or not isinstance(dma_header, str)
                or hashlib.sha256(dma_header.encode("utf-8")).hexdigest()!=expected_dma):
            raise ValueError("published DMA production header differs from verified source")
        if ('SOC_DMA_SHIM_HEAD_LO_OFFSET' not in dma_header
                or 'SOC_DMA_SHIM_STATUS_OFFSET' not in dma_header):
            raise ValueError("published production DMA header lacks expected CSR offsets")
        if 'data/soc_dma_shim_regs.h' not in address_html:
            raise ValueError("published CSR page missing production DMA C header link")
    if coverage.get("schema_version") != 1 or coverage.get("unacknowledged"):
        raise ValueError("published CSR source coverage has missing/unknown CSR IPs")
    by_name = {entry["instance"]: entry for entry in coverage.get("instances", [])}
    for name, count in (("compute0.dma", 4), ("compute1.dma", 4),
                        ("ethernet0.ctrl", 25)):
        if by_name.get(name, {}).get("source_only_registers", 0) < count:
            raise ValueError("published source-qualified CSR map missing " + name)
    if not isinstance(ddr, list) or not ddr:
        raise ValueError("no qualified real DDR CSR variant published")
    valid = False
    for entry in ddr:
        catalog = entry.get("catalog", {})
        if catalog.get("variant") != "ddr_real" or not entry.get("run_id"):
            continue
        ctrl = [region for region in catalog.get("regions", [])
                if region.get("name") == "memory0.ctrl"]
        if (len(ctrl) == 1 and ctrl[0].get("size") == "0x4000"
                and ctrl[0].get("registers")
                and all(reg.get("definition_status") ==
                        "native_LiteDRAM_generated_CSR_not_bus_coverage"
                        for reg in ctrl[0]["registers"])):
            valid = True
            break
    if not valid:
        raise ValueError("published DDR variant lacks qualified native register source")
    return len(ddr)


def fetch(base, rel):
    url = urllib.parse.urljoin(base.rstrip("/") + "/", rel)
    request = urllib.request.Request(
        url, headers={"User-Agent": "xezim-soc-pages-publication-check/1",
                      "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("public Pages returned HTTP " + str(response.status))
        return response.read().decode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--interval", type=int, default=12)
    args = parser.parse_args()
    url = urllib.parse.urlparse(args.base_url)
    if url.scheme != "https" or url.hostname != "r987r.github.io":
        parser.error("unexpected public Pages origin")
    if url.path.rstrip("/") != "/xezim-hello-world":
        parser.error("unexpected public Pages project route")
    if not args.sha or len(args.sha) != 40:
        parser.error("invalid exact deployed commit SHA")
    if args.attempts <= 0 or args.attempts > 30:
        parser.error("invalid attempt count")
    validate.expected_sha = args.sha
    for attempt in range(1, args.attempts + 1):
        try:
            site = json.loads(fetch(args.base_url, "data/site.json"))
            html = fetch(args.base_url, "address-map.html")
            coverage = json.loads(fetch(args.base_url, "data/csr-source-coverage.json"))
            ddr = json.loads(fetch(args.base_url, "data/ddr-csr-verified-runs.json"))
            dma = fetch(args.base_url, "data/soc_dma_shim_regs.h")
            count = validate(site, html, coverage, ddr, dma)
            print("PASS public Pages CSR explorer: sha=" + args.sha
                  + " qualified DDR variants=" + str(count))
            return
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            if attempt == args.attempts:
                raise SystemExit("FAIL public Pages CSR release check: " + str(exc))
            print("Pages not yet source-qualified (" + str(attempt) + "/"
                  + str(args.attempts) + "): " + str(exc), flush=True)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
