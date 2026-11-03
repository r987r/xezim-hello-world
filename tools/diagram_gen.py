"""Canonical whole-chip FlooNoC/SoC diagram; no duplicate subsystem views.

Topology comes strictly from upstream FlooGen artifacts, never a second
hand-authored connectivity graph. The only SVG is noc-hierarchy.svg.
"""
from __future__ import annotations
from pathlib import Path
import json


def render(cfg: dict, meta: dict, destination: Path, noc_root: Path | None = None) -> dict:
    if noc_root is None:
        raise ValueError("FlooGen-generated structural RTL topology is required")
    import noc_diagrams
    destination.mkdir(parents=True, exist_ok=True)
    graph, diagrams = noc_diagrams.render(cfg, noc_root, destination)
    (destination / "graphs.json").write_text(json.dumps({
        "noc_hierarchy": {
            "status": graph["status"],
            "networks": graph["networks"],
            "source": "gen/noc/floonoc/manifest.json"
        }
    }, indent=2, sort_keys=True) + "\n")
    return diagrams
