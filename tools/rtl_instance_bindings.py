#!/usr/bin/env python3
"""Correlate generated diagram boundaries with source-parsed top RTL instances.

This is an index of *syntactic* instantiations in the checked-in default
chip. It does not elaborate parameterized generate blocks or prove a path
active in any test profile. Optional PCIe/Ethernet variants must not be
invented from similarly named repository source files.
"""
from __future__ import annotations

import re


def tokens(value: str) -> tuple[str, ...]:
    """Use whole instance-name tokens, never arbitrary substring matches."""
    return tuple(part for part in re.split(r"[^a-z0-9]+", value.lower()) if part)


def resolve(graph: dict, parsed: dict, *, top: str) -> dict[str, dict]:
    """Return explicit, fail-closed associations for generic topology nodes.

    A match requires every token in the diagram boundary identifier to
    occur in an actual compiler-parsed top-level instance name. Select a
    source instance only when it uniquely has the fewest extra tokens.
    Both the association and its root RTL instance are *syntactic*, not
    elaboration or live-traffic proof.
    """
    if not top:
        raise ValueError("missing generated RTL top module name")
    modules = {m["name"]: m for m in parsed.get("modules", [])}
    source_top = modules.get(top)
    if parsed.get("modules") and source_top is None:
        raise ValueError("compiler-parsed RTL is missing generated top: " + top)

    instances = (source_top or {}).get("instances", [])
    entries = []
    for inst in instances:
        name = inst.get("name", "")
        if not name.startswith("u_"):
            continue
        entries.append((inst, tokens(name[2:])))

    result = {}
    for node in graph.get("nodes", []):
        if node.get("module") != "soc_boundary":
            continue
        identifier = node["id"]
        requested = set(tokens(identifier))
        if not requested:
            result[identifier] = {"status": "invalid_boundary_name"}
            continue
        if source_top is None:
            result[identifier] = {"status": "compiler_parse_unavailable"}
            continue
        candidates = []
        for inst, names in entries:
            if requested.issubset(names):
                # Penalize incidental name words rather than selecting a
                # broader DMA CSR block as a DMA engine by substring.
                extra = sum(word not in requested for word in names)
                candidates.append((extra, inst["name"], inst))
        if not candidates:
            result[identifier] = {"status": "no_root_instance_match"}
            continue
        candidates.sort(key=lambda row: (row[0], row[1]))
        best = [row for row in candidates if row[0] == candidates[0][0]]
        if len(best) != 1:
            result[identifier] = {
                "status": "ambiguous_root_instance",
                "candidate_names": sorted(row[1] for row in best),
            }
            continue
        inst = best[0][2]
        module_name = inst["module"]
        result[identifier] = {
            "status": "unique_root_instance",
            "top": top,
            "instance": inst["name"],
            "module": module_name,
            "source": inst["source"],
            "parsed_module_available": module_name in modules,
            "conditional_generate": bool(inst.get("conditional_generate", False)),
            "evidence": "unique_name_correlated_slang_cst_not_elaborated",
        }
    return result
