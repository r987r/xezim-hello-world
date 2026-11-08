#!/usr/bin/env python3
"""On-demand bit-aware source-to-sink dependency path from slang-netlist JSON.

This traverses upstream's serialized graph, not regex-inferred connections.
A data-dependency path is NOT a proof of packet route, protocol legality,
timing, CDC safety, or causality across time.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path


def read_graph(path: Path) -> tuple[dict, dict[int, dict], dict[int, list[dict]]]:
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or not isinstance(data.get("version"), int)
            or not isinstance(data.get("nodes"), list)
            or not isinstance(data.get("edges"), list)
            or not isinstance(data.get("fileTable"), list)):
        raise ValueError("unsupported slang-netlist JSON schema")
    nodes = {}
    port_paths = set()
    for node in data["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), int):
            raise ValueError("invalid netlist node")
        if node["id"] in nodes:
            raise ValueError(f"duplicate netlist node ID {node['id']}")
        if node.get("kind") == "Port":
            port_path = node.get("path")
            if not isinstance(port_path, str) or not port_path:
                raise ValueError("elaborated Port node requires a nonempty path")
            if port_path in port_paths:
                raise ValueError(f"duplicate elaborated port path: {port_path}")
            port_paths.add(port_path)
            bounds = node.get("bounds")
            if bounds is not None and (not isinstance(bounds, list)
                    or len(bounds) != 2 or any(type(n) is not int or n < 0 for n in bounds)
                    or bounds[0] > bounds[1]):
                raise ValueError(f"{port_path}: invalid elaborated port bounds")
        nodes[node["id"]] = node
    adjacency = {n: [] for n in nodes}
    for edge in data["edges"]:
        if not isinstance(edge, dict) or edge.get("source") not in nodes or edge.get("target") not in nodes:
            raise ValueError("dangling netlist dependency edge")
        if not edge.get("disabled", False):
            adjacency[edge["source"]].append(edge)
    return data, nodes, adjacency


def locate(node: dict, file_table: list[str]) -> dict | None:
    loc = node.get("location")
    if not isinstance(loc, dict):
        return None
    idx = loc.get("fileIndex")
    if not isinstance(idx, int) or idx < 0 or idx >= len(file_table):
        return None
    return {"file": file_table[idx], "line": loc.get("line"),
            "column": loc.get("column")}


def enumerate_ports(nodes: dict[int, dict], prefix: str = "") -> list[dict]:
    values = []
    for item in nodes.values():
        if item.get("kind") == "Port" and str(item.get("path", "")).startswith(prefix):
            values.append({"id": item["id"], "path": item.get("path", ""),
                           "direction": item.get("direction"),
                           "bounds": item.get("bounds", [])})
    return sorted(values, key=lambda x: x["path"])


def trace(path: Path, source: str, target: str,
          *, max_depth: int = 128, max_visited: int = 200000) -> dict:
    data, nodes, adjacency = read_graph(path)
    ports = {x["path"]: x for x in enumerate_ports(nodes)}
    if source not in ports or target not in ports:
        missing = [s for s in (source, target) if s not in ports]
        raise ValueError(f"unknown elaborated port(s): {missing}")
    src, dst = ports[source]["id"], ports[target]["id"]
    seen = {src}
    q = deque([(src, 0)])
    parent: dict[int, tuple[int, dict]] = {}
    truncated_by_depth = False
    while q:
        cur, depth = q.popleft()
        if cur == dst:
            break
        if depth >= max_depth:
            # A bounded miss is inconclusive only if traversal actually
            # discarded unexplored outgoing paths. A terminal leaf is exhaustive.
            if any(edge["target"] not in seen for edge in adjacency[cur]):
                truncated_by_depth = True
            continue
        for edge in adjacency[cur]:
            nxt = edge["target"]
            if nxt in seen:
                continue
            seen.add(nxt)
            parent[nxt] = (cur, edge)
            q.append((nxt, depth + 1))
            if len(seen) > max_visited:
                raise ValueError("netlist trace exceeded explicit node visit bound")
    connected = dst in seen
    steps = []
    if connected:
        cur = dst
        while cur != src:
            before, edge = parent[cur]
            node = nodes[cur]
            steps.append({"from": before, "to": cur,
                          "kind": node.get("kind"), "name": node.get("name"),
                          "path": node.get("path"),
                          "edge_kind": edge.get("edgeKind"),
                          "bit_bounds": edge.get("bounds"),
                          "source_location": locate(node, data["fileTable"])})
            cur = before
        steps.reverse()
    return {"schema_version": 1,
            "tool": "slang-netlist", "evidence": "elaborated_static_data_dependency",
            "source_port": source, "target_port": target,
            "found": connected, "hop_limit": max_depth,
            "complete_under_limits": connected or not truncated_by_depth,
            "steps": steps,
            "warning": "Static data-flow reachability does not prove protocol route or simulation correctness."}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("netlist", type=Path)
    cli.add_argument("--from-port")
    cli.add_argument("--to-port")
    cli.add_argument("--list-ports", action="store_true")
    cli.add_argument("--prefix", default="")
    cli.add_argument("--max-depth", type=int, default=128)
    cli.add_argument("--output", type=Path)
    a = cli.parse_args()
    if a.list_ports:
        _, nodes, _ = read_graph(a.netlist)
        obj = enumerate_ports(nodes, a.prefix)
    else:
        if not a.from_port or not a.to_port:
            cli.error("--from-port and --to-port are both required unless --list-ports")
        if a.max_depth < 1:
            cli.error("--max-depth must be positive")
        obj = trace(a.netlist, a.from_port, a.to_port, max_depth=a.max_depth)
    value = json.dumps(obj, indent=2) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(value)
    else:
        print(value, end="")


if __name__ == "__main__":
    main()
