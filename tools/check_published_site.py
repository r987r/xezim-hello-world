#!/usr/bin/env python3
"""Post-deploy *public HTTP* integrity gate for Fabric, Test Runs and Architecture.

Only source-derived agreement is mandatory. A cleanly published site can have
unmeasured optional protocols; never fabricate a passing DFI/Ethernet/PCIe run.
The separate CSR public gate retains its own native-DDR qualification checks.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse

from check_published_csr import fetch


SHA = re.compile(r"^[a-f0-9]{40}$")


def validate(expected_sha, site, fabric, graph, rtl, bindings, intents, html):
    """Cross-check source-indexed content and three actual public HTML pages."""
    if not SHA.fullmatch(expected_sha) or site.get("source_sha") != expected_sha:
        raise ValueError("public Pages source SHA differs from deployed main")
    networks = site.get("networks")
    tests = site.get("tests")
    if not isinstance(networks, dict) or not networks:
        raise ValueError("missing source-derived network inventory")
    if not isinstance(tests, dict) or not tests:
        raise ValueError("missing configured regression catalog")
    if set(intents) != set(tests):
        raise ValueError("published intended test flow differs from configured regression targets")
    for name, intent in intents.items():
        if set(("init", "run", "check")) - set(intent.get("phases", {})):
            raise ValueError("published intended test phases missing for " + name)

    groups = {
        g["name"]: g for g in graph.get("groups", [])
        if (g.get("info") or {}).get("plane") in ("data", "config")
    }
    if set(groups) != set(networks):
        raise ValueError("Architecture network groups differ from generator manifest")
    for name, network in networks.items():
        actual = groups[name].get("info", {}).get("router_count")
        if actual != network.get("routers"):
            raise ValueError("Architecture router count differs for " + name)
    if fabric.get("summary", {}).get("meshes") != len(networks):
        raise ValueError("Fabric network count differs from generator manifest")
    latency = fabric.get("latency_table", {})
    if latency.get("units") != "simulation_reference_clock_cycles":
        raise ValueError("Fabric latency does not expose declared simulation reference")
    if len(latency.get("rows", [])) != len(fabric.get("matrix", [])):
        raise ValueError("Fabric route/latency table mismatch")

    parsed = {m["name"]: m for m in rtl.get("modules", [])}
    contract = rtl.get("fabric_contract", {})
    if (rtl.get("producer") != "slang"
            or contract.get("independent_planes") is not True
            or set(contract.get("resolved_networks", [])) != set(networks)):
        raise ValueError("compiler-parsed Fabric RTL does not match generated networks")
    top = site.get("chip", {}).get("top")
    top_module = parsed.get(top, {})
    root_instances = {i["name"]: i for i in top_module.get("instances", [])}
    boundaries = {n["id"] for n in graph.get("nodes", []) if n.get("module") == "soc_boundary"}
    if not boundaries or set(bindings) != boundaries:
        raise ValueError("source-derived RTL binding inventory is incomplete")
    for node, binding in bindings.items():
        status = binding.get("status")
        if status == "unique_root_instance":
            actual = root_instances.get(binding.get("instance"))
            if not actual or actual.get("module") != binding.get("module"):
                raise ValueError("source-correlated RTL root instance changed for " + node)
            if binding.get("parsed_module_available") != (binding["module"] in parsed):
                raise ValueError("parsed module availability disagrees with source for " + node)
            if binding.get("evidence") != "unique_name_correlated_slang_cst_not_elaborated":
                raise ValueError("RTL binding overstates its source proof for " + node)
        elif status not in {
                "no_root_instance_match", "ambiguous_root_instance",
                "invalid_boundary_name", "compiler_parse_unavailable",
        }:
            raise ValueError("unexpected source binding state for " + node)

    for page, fragments in {
        "runs": ('id="test-flow-plan"', 'id="traffic-run"', 'id="traffic-table"'),
        "fabric": ('id="fabric-latency-table"', 'id="fabric-interfaces"',
                   'id="fabric-evidence-coverage"'),
        "explorer": ('id="arch-svg"', 'id="ex-embedded-rtl-bindings"',
                     'id="arch-embedded-protocol-links"'),
    }.items():
        source = html.get(page, "")
        for fragment in fragments:
            if fragment not in source:
                raise ValueError(f"public {page} page missing {fragment}")

    # A full-chip DFI observation must come from an actual verified artifact;
    # report its count, never promote a source-only plan to observed PASS.
    dfi_runs = 0
    for entry in site.get("entries", []):
        if not SHA.fullmatch(str(entry.get("source_sha", ""))):
            raise ValueError("published regression entry lacks tested SHA")
        links = entry.get("protocol_links") or {}
        if entry.get("target") == "chip-ddr4-real" and (
                any(source.get("protocol") == "dfi" and source.get("count", 0) > 0
                    for source in links.get("sources", []))):
            dfi_runs += 1
    return {
        "networks": len(networks), "routers": sum(int(v["routers"]) for v in networks.values()),
        "tests": len(tests), "evidence_entries": len(site.get("entries", [])),
        "real_fullchip_dfi_runs": dfi_runs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
    if not SHA.fullmatch(args.sha):
        parser.error("invalid exact deployed source SHA")
    if not 1 <= args.attempts <= 30:
        parser.error("invalid attempt count")

    paths = {
        "site": "data/site.json",
        "fabric": "data/fabric.json",
        "graph": "data/design-graph.json",
        "rtl": "data/rtl-architecture.json",
        "bindings": "data/rtl-instance-bindings.json",
        "intents": "data/test-intents.json",
    }
    for attempt in range(1, args.attempts + 1):
        try:
            data = {name: json.loads(fetch(args.base_url, relative))
                    for name, relative in paths.items()}
            pages = {page: fetch(args.base_url, page + ".html")
                     for page in ("runs", "fabric", "explorer")}
            report = validate(args.sha, data["site"], data["fabric"],
                              data["graph"], data["rtl"], data["bindings"],
                              data["intents"], pages)
            print("PASS public Pages Fabric/Tests/Architecture: "
                  + " ".join(f"{k}={v}" for k, v in report.items()))
            if not report["real_fullchip_dfi_runs"]:
                print("NOTE: no source-verified full-chip DFI run is publicly "
                      "indexed yet; keep #108 open and do not claim proof")
            return
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            if attempt == args.attempts:
                raise SystemExit("FAIL public Pages surface integrity: " + str(exc))
            print(f"Pages surface not source-qualified ({attempt}/{args.attempts}): "
                  + str(exc), flush=True)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
