#!/usr/bin/env python3
"""Fail-closed main Pages release gate for source-qualified Fabric latency.

Historical test records may be published as history, but they must not quietly
replace current-source measured latency. When new RTL/DV source lacks a passing
baseline, schedule one main-ref RTL benchmark. A passing benchmark schedules
a fresh Pages publication. PR previews never dispatch or deploy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import urllib.request

SHA = re.compile(r"^[a-f0-9]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def site_coverage(site_root: Path, source_sha: str) -> dict:
    site = json.loads((site_root / "data/site.json").read_text())
    fabric = json.loads((site_root / "data/fabric.json").read_text())
    if not SHA.fullmatch(source_sha) or site.get("source_sha") != source_sha:
        raise ValueError("Fabric publication does not match exact main checkout SHA")
    coverage = fabric.get("latency_table", {}).get("evidence_coverage", {})
    measured = coverage.get("current_measured_routes")
    stages = coverage.get("current_stage_observations")
    historical = coverage.get("historical_observations")
    period = (fabric.get("latency_table", {}).get("reference_clock", {})
              .get("measured_period_ps"))
    for name, count in (("measured", measured), ("stages", stages),
                        ("historical", historical)):
        if type(count) is not int or count < 0:
            raise ValueError("Fabric publication has invalid " + name + " count")
    if measured and (not stages or type(period) is not int or period <= 0):
        raise ValueError("Fabric measured routes lack qualified stage/clock evidence")
    return {"measured": measured, "stages": stages, "historical": historical}


def decision(source_sha: str, measured: int, runs: list[dict]) -> str:
    """Never repeatedly dispatch a successful, running, or failed exact SHA."""
    if not SHA.fullmatch(source_sha) or type(measured) is not int or measured < 0:
        raise ValueError("invalid exact-source Fabric refresh request")
    if measured:
        return "publish"
    matches = [r for r in runs if r.get("head_sha") == source_sha
               and r.get("event") == "workflow_dispatch"
               and r.get("head_branch") == "main"]
    if any(r.get("status") == "completed" and r.get("conclusion") == "success"
           for r in matches):
        return "qualified_unpublished"
    if any(r.get("status") in {"queued", "in_progress", "pending", "requested", "waiting"}
           for r in matches):
        return "in_progress"
    if matches:
        return "qualification_failed"
    return "dispatch"


def github_request(repository: str, token: str, path: str,
                   *, body: dict | None = None) -> dict:
    if not REPOSITORY.fullmatch(repository) or not token:
        raise ValueError("main publication requires scoped GitHub authentication")
    base = f"https://api.github.com/repos/{repository}/"
    if not path.startswith("actions/"):
        raise ValueError("unexpected GitHub workflow resource")
    raw = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        base + path, data=raw, method="POST" if body is not None else "GET",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "soc-fabric-publish-gate",
                 **({"Content-Type": "application/json"} if body is not None else {})})
    with urllib.request.urlopen(req, timeout=45) as response:
        payload = response.read()
    return json.loads(payload) if payload else {}


def guard_main(source_sha: str, measured: int, historical: int,
               repository: str, token: str) -> None:
    if (os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_SHA") != source_sha):
        raise ValueError("Fabric auto-refresh is allowed only for exact main-ref dispatch")
    if type(historical) is not int or historical < 0:
        raise ValueError("invalid historical observation count")
    if measured:
        print(f"FABRIC RELEASE READY: main {source_sha} has {measured} measured routes.")
        return
    runs = github_request(
        repository, token,
        "actions/workflows/dv-fabric-latency.yml/runs"
        "?branch=main&event=workflow_dispatch&per_page=100").get("workflow_runs", [])
    if not isinstance(runs, list):
        raise ValueError("GitHub benchmark run history unavailable")
    action = decision(source_sha, measured, runs)
    if action == "dispatch":
        github_request(repository, token,
                       "actions/workflows/dv-fabric-latency.yml/dispatches",
                       body={"ref": "main"})
        raise RuntimeError("FABRIC DEPLOY DEFERRED: requested real main RTL "
                           f"benchmark at {source_sha}; retain last published site")
    if action == "in_progress":
        raise RuntimeError("FABRIC DEPLOY DEFERRED: exact-main RTL benchmark "
                           f"still running for {source_sha}; retain last published site")
    if action == "qualified_unpublished":
        raise RuntimeError("FABRIC PUBLICATION BUG: exact-main RTL benchmark "
                           f"PASSED for {source_sha}, but Pages has zero measured "
                           "routes. Check benchmark artifact selection/provenance.")
    raise RuntimeError("FABRIC BENCHMARK FAILED: exact-main RTL benchmark "
                       f"already attempted for {source_sha}; don't silently "
                       "publish Unmeasured or create a retry loop.")


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report-site", type=Path)
    mode.add_argument("--guard", action="store_true")
    cli.add_argument("--sha", required=True)
    cli.add_argument("--measured", type=int)
    cli.add_argument("--historical", type=int)
    args = cli.parse_args()
    if args.report_site:
        result = site_coverage(args.report_site, args.sha)
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise ValueError("missing GitHub job output path")
        with open(output, "a", encoding="utf-8") as out:
            out.write(f"measured={result['measured']}\n")
            out.write(f"historical={result['historical']}\n")
        print("FABRIC SOURCE COVERAGE: " + json.dumps(result, sort_keys=True))
    else:
        if args.measured is None or args.historical is None:
            cli.error("guard requires measured and historical counts")
        guard_main(args.sha, args.measured, args.historical,
                   os.environ.get("GITHUB_REPOSITORY", ""),
                   os.environ.get("GH_TOKEN", ""))


if __name__ == "__main__":
    main()
