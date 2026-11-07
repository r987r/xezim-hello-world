"""Resolve physical windows from the exact regression-selected SoC source.

Never copy absolute Ethernet/DDR/CSR base addresses into an IP testbench.
The existing address_map builder validates the selected SoC variant and owns
the meaning of source-defined physical apertures; this module only selects
a named region for tests. Packet/descriptor/CSR offsets remain IP-owned.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from tools.address_map import build as build_address_map

ROOT = Path(__file__).resolve().parents[2]


def selected_aperture(name: str, plane: str, *, plan_path=None) -> tuple[int, int]:
    """Return (base, size) from the test's exact selected address-map config.

    With no run plan, use the versioned default config for standalone tests.
    A report-less/foreign path or wrong plane fails closed. The caller must
    still prove any live RTL attachment and real accepted transactions.
    """
    if plane not in ("data", "config") or not name:
        raise ValueError("invalid physical aperture query")
    chosen = plan_path if plan_path is not None else os.environ.get("SOC_RUN_PLAN")
    if chosen:
        path = Path(chosen)
        plan = json.loads(path.read_text())
        selected = plan.get("report", {}).get("address_map")
        if not isinstance(selected, dict):
            raise ValueError("run has no selected SoC address-map source")
        relative = selected.get("config")
        variant = selected.get("variant")
        if not isinstance(relative, str) or not relative or not isinstance(variant, str):
            raise ValueError("invalid selected SoC address-map provenance")
        config = (ROOT / relative).resolve()
        if not config.is_relative_to(ROOT.resolve()):
            raise ValueError("selected SoC address-map source escapes repository")
    else:
        config = ROOT / "config/soc.yaml"
        variant = "architecture"
    from tools import address_map
    selected_map = address_map.build(config, variant=variant)
    matches = [row for row in selected_map["regions"]
               if row["plane"] == plane and row["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"missing or ambiguous selected {plane} window {name}")
    entry = matches[0]
    base, size = int(entry["base"], 0), int(entry["size"], 0)
    if size <= 0:
        raise ValueError("empty selected physical aperture")
    return base, size
