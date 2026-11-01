"""Generate 2D GitHub Mermaid diagrams from validated SoC configuration.

The architectural graph is explicitly logical/planned. The RTL graph instead
models exactly the executable memory testbench emitted by socgen.py; it must
not imply that not-yet-connected CPUs, DMAs, or global NoCs are fabricated RTL.

Inspired by the structured instance/connection metadata model used by
r987r/Diagram-gen and r987r/Sv-diagrams, and by verification-boundary metadata
from r987r/Sv-test. No 3D viewer or external diagram renderer is required.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


COLORS = {
    "cpu": "cpu",
    "dma": "dma",
    "fabric": "fabric",
    "memory": "memory",
    "config": "config",
    "verification": "verification",
    "model": "model",
}


def node_id(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if not value or value[0].isdigit():
        value = "n_" + value
    return value


def md_label(text: Any) -> str:
    """Escape a Mermaid quoted label; allow our own line separators only."""
    text = str(text)
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;")
            .replace("\n", "<br/>").replace("|", "&#124;"))


def header(direction: str) -> list[str]:
    return [
        "flowchart " + direction,
        "  classDef cpu fill:#e8f0fe,stroke:#2869c9,color:#172a4b,stroke-width:1px;",
        "  classDef dma fill:#e7f2ff,stroke:#2869c9,color:#172a4b,stroke-width:1px;",
        "  classDef fabric fill:#e3f4ec,stroke:#20824e,color:#153c26,stroke-width:1px;",
        "  classDef memory fill:#fff0e6,stroke:#c46b2f,color:#563115,stroke-width:1px;",
        "  classDef config fill:#f1edff,stroke:#7654b5,color:#342451,stroke-width:1px;",
        "  classDef verification fill:#e3f4ec,stroke:#20824e,color:#153c26,stroke-width:1px;",
        "  classDef model fill:#f2f2f2,stroke:#888888,color:#333333,stroke-width:1px;",
    ]


def block(name: str, label: str, category: str = "model", indent: str = "  ") -> str:
    return f'{indent}{node_id(name)}["{md_label(label)}"]:::{COLORS.get(category, "model")}'


def link(src: str, dst: str, label: str = "", style: str = "logical") -> str:
    # Dashed => planned connectivity, solid => real generated RTL edges.
    op = "-.->" if style == "planned" else "-->"
    if label:
        return f"  {node_id(src)} {op}|{md_label(label)}| {node_id(dst)}"
    return f"  {node_id(src)} {op} {node_id(dst)}"


def regions_by_name(meta: dict, plane: str) -> dict:
    return {r["name"]: r for r in meta[f"{plane}_regions"]}


def span(region: dict) -> str:
    return f'0x{region["base"]:x} + 0x{region["size"]:x}'


def build_architecture(cfg: dict, meta: dict) -> tuple[str, dict]:
    lines = header("TB")
    nodes: list[dict] = []
    edges: list[dict] = []

    def add(name, label, cat, parent=""):
        nodes.append({"id": name, "label": label, "category": cat, "parent": parent})
        lines.append(block(name, label, cat, "    " if parent else "  "))

    def connect(src, dst, label, status="planned"):
        edges.append({"from": src, "to": dst, "label": label, "status": status})
        lines.append(link(src, dst, label, style="planned" if status == "planned" else "rtl"))

    for inst in meta["subsystems"]:
        name, typ = inst["name"], inst["type"]
        lines.append(f'  subgraph {node_id("box_" + name)}["{md_label(name + " : " + typ)}"]')
        lines.append("    direction TB")
        if typ == "compute":
            cpu = inst["cpu"]
            add(f"{name}.cpu", f'{cpu["ip"]}\n{cpu["bus"]} / {cpu["adapter"]}', "cpu", name)
            add(f"{name}.dma", f'{cfg["subsystem_types"]["compute"]["dma"]}\nDMA RTL: pending', "dma", name)
            add(f"{name}.local_data", f'Local data fabric\n{cfg["fabrics"]["local_data"]["backend"]} (pending)', "fabric", name)
            add(f"{name}.local_config", f'Local config fabric\n{cfg["fabrics"]["local_config"]["backend"]} (pending)', "config", name)
            sram = f"{name}.sram"
            r = regions_by_name(meta, "data").get(sram)
            add(sram, f'SRAM\n{span(r) if r is not None else "address not configured"}', "memory", name)
        else:
            add(f"{name}.local_data", f'{meta["ingress"]}-input AXI4 fabric\n{cfg["fabrics"]["memory_data"]["backend"]} (RTL tested)', "fabric", name)
            add(f"{name}.local_config", f'Memory config fabric\n{cfg["fabrics"]["local_config"]["backend"]} (pending)', "config", name)
            for t in meta["targets"]:
                add(t["name"], f'{t["kind"].upper()} {t["controller"]}\nAXI model: {t["sim_backend"]}\n{span(t)}', "memory", name)
        lines.append("  end")
    gf = cfg["fabrics"]["global_data"]
    cf = cfg["fabrics"]["global_config"]
    add("global_data", f'Global data NoC\n{gf["topology"]} / {gf["backend"]}\nAXI4 {meta["data_bits"]}-bit (pending)', "fabric")
    add("global_config", f'Global config NoC\n{cf["topology"]} / {cf["backend"]}\nAXI4-Lite (pending)', "config")

    for inst in meta["subsystems"]:
        name = inst["name"]
        if inst["type"] == "compute":
            connect(f"{name}.cpu", f"{name}.local_config", "MMIO via adapter")
            connect(f"{name}.dma", f"{name}.local_data", "AXI4")
            connect(f"{name}.local_data", f"{name}.sram", "local SRAM")
            connect(f"{name}.local_data", "global_data", "AXI4 uplink")
            connect(f"{name}.local_config", "global_config", "config uplink")
        else:
            for t in meta["targets"]:
                # This subpath is physically present in the executable memory DUT.
                connect(f"{name}.local_data", t["name"], f'AXI4 → {t["kind"].upper()} model', "rtl")
            connect("global_config", f"{name}.local_config", "CSR ingress")
    for i, output in enumerate(meta["global_data_outputs"]):
        connect("global_data", f"{meta['memory_subsystem']}.local_data", f'output{i} / {output["target"]}')
    for inst in meta["subsystems"]:
        if inst["type"] == "compute":
            connect("global_config", f'{inst["name"]}.local_config', "remote MMIO")
    lines += [
        '  %% Dashed links = planned full-chip integration; solid links = memory model RTL scope.',
    ]
    return "\n".join(lines) + "\n", {"nodes": nodes, "connections": edges,
              "meaning": "Logical architecture. Only memory-local model paths have tested RTL."}


def build_rtl_connectivity(cfg: dict, meta: dict) -> tuple[str, dict]:
    """Describe instantiated verification RTL, not architectural wish-list edges."""
    lines = header("LR")
    ni, targets = meta["ingress"], meta["targets"]
    nodes: list[dict] = []
    edges: list[dict] = []

    def add(name, label, cat):
        nodes.append({"id": name, "label": label, "category": cat})
        lines.append(block(name, label, cat, "    "))

    def connect(src, dst, label, status="wired", channels=None, from_port=None, to_port=None):
        edges.append({"from": src, "to": dst, "label": label, "status": status,
                      "protocol": "axi4" if status == "wired" else "monitor",
                      "from_instance": src, "to_instance": dst,
                      "from_port": from_port, "to_port": to_port,
                      "channels": channels or (["AW", "W", "B", "AR", "R"] if status == "wired" else [])})
        lines.append(link(src, dst, label, style="rtl" if status == "wired" else "planned"))

    lines.append('  subgraph TB["EXISTING RTL testbench: memory_tb"]')
    lines.append("    direction LR")
    for i in range(ni):
        add(f"ingress{i}", f'AXI master BFM {i}\n{meta["data_bits"]}-bit / ID {meta["id_bits"]}', "cpu")
    add("xbar", f'{cfg["fabrics"]["memory_data"]["backend"]} axi_crossbar\n{ni} inputs × {len(targets)} outputs\n{meta["address_bits"]}-bit address, {meta["data_bits"]}-bit data', "fabric")
    for t in targets:
        label = f'{t["name"]}\n{t["kind"].upper()} simulation target\n{t["sim_backend"]}\n{span(t)}'
        add(t["name"], label, "memory")
    add("route_monitor", "AXI route monitor\nchecks source/target and ID", "verification")
    lines.append("  end")
    for i in range(ni):
        connect(f"ingress{i}", "xbar", f'AXI4 ingress {i} (AW,W,B,AR,R)',
                from_port=f"masters[{i}].u_agent", to_port=f"fabric.s_axi[{i}]")
    for i, t in enumerate(targets):
        connect("xbar", t["name"], f'AXI4 port {i} (AW,W,B,AR,R)',
                from_port=f"fabric.m_axi[{i}]", to_port=f"memories[{i}].u_mem.s_axi")
    connect("xbar", "route_monitor", "passive observation", "observe")
    lines.append('  %% Only these connections are instantiated by gen/memory/memory_tb.sv.')
    return "\n".join(lines) + "\n", {
        "scope": "memory_fabric", "source": "gen/memory/memory_tb.sv",
        "clock": "clk", "reset": "rst", "status": "executable",
        "nodes": nodes, "connections": edges, "protocol": "axi4",
        "data_bits": meta["data_bits"], "address_bits": meta["address_bits"],
        "source_id_bits": meta["id_bits"],
        "target_id_bits": meta["id_bits"] + (ni - 1).bit_length(),
    }


def build_verification(cfg: dict, meta: dict) -> tuple[str, dict]:
    scopes = cfg["verification"]["scopes"]
    lines = header("TB")
    nodes: list[dict] = []
    edges: list[dict] = []
    lines.append(block("cfg", "config/soc.yaml\nvalidated source of truth", "config"))
    lines.append(block("gen", "make gen\nRTL + NoC IR + DV plan + diagrams", "fabric"))
    lines.append(link("cfg", "gen", "generates"))
    for status in ("executable", "planned"):
        label = "EXECUTABLE CHECKS" if status == "executable" else "NOT YET IMPLEMENTED"
        lines.append(f'  subgraph {status}["{label}"]')
        lines.append("    direction LR")
        for scope in scopes:
            if scope["status"] == status:
                name = scope["name"]
                cmd = scope.get("command", "future")
                checks = ", ".join(scope["checks"][:3])
                label = f'{name}\nDUT: {scope["dut"]}\n{cmd}\n{checks}'
                nodes.append({"id": name, "label": label, "status": status, "dut": scope["dut"],
                              "command": scope.get("command"), "checks": scope["checks"]})
                lines.append(block(name, label, "verification" if status == "executable" else "model", "    "))
        lines.append("  end")
    for scope in scopes:
        lines.append(link("gen", scope["name"], "scope inputs", "planned" if scope["status"] == "planned" else "rtl"))
        edges.append({"from": "generator", "to": scope["name"], "status": scope["status"]})
    lines.append('  %% Planned tests are placeholders only and do not imply RTL was simulated.')
    return "\n".join(lines) + "\n", {
        "scopes": nodes, "connections": edges, "generator": "make gen",
        "memory_agents": meta["ingress"], "memory_targets": [t["name"] for t in meta["targets"]],
        "notes": "Executable means the testbench exists; a green simulation requires CI to run."
    }


def build_subsystem(cfg: dict, meta: dict, inst: dict) -> str:
    name = inst["name"]
    lines = header("TB")
    lines.append(f'  subgraph {node_id(name + "_subsystem")}["{md_label(name)}: subsystem contract"]')
    lines.append('    direction TB')
    if inst["type"] == "compute":
        cpu = inst["cpu"]
        lines += [
            block(f"{name}.cpu", f'{cpu["ip"]}\n{cpu["bus"]} / {cpu["adapter"]}', "cpu", "    "),
            block(f"{name}.dma", cfg["subsystem_types"]["compute"]["dma"], "dma", "    "),
            block(f"{name}.data", f'Local data fabric\n{cfg["fabrics"]["local_data"]["backend"]}', "fabric", "    "),
            block(f"{name}.config", f'Local config fabric\n{cfg["fabrics"]["local_config"]["backend"]}', "config", "    "),
            block(f"{name}.sram", 'SRAM\n' + (span(regions_by_name(meta, 'data')[f"{name}.sram"])
                 if f"{name}.sram" in regions_by_name(meta, 'data') else "address not configured"), "memory", "    "),
        ]
    else:
        lines += [
            block(f"{name}.ingress", f'{meta["ingress"]} AXI4 ingress ports', "cpu", "    "),
            block(f"{name}.data", f'Local {meta["ingress"]}×{len(meta["targets"])} crossbar\n{cfg["fabrics"]["memory_data"]["backend"]}', "fabric", "    "),
            block(f"{name}.config", 'Controller CSRs\nAXI4-Lite pending', "config", "    "),
        ]
        for t in meta['targets']:
            lines.append(block(t['name'], f'{t["kind"].upper()} {t["controller"]}\n{t["sim_backend"]} simulation\n{span(t)}', "memory", "    "))
    lines.append("  end")
    if inst['type'] == 'compute':
        lines += [link(f'{name}.cpu', f'{name}.config', 'adapter required', 'planned'),
                  link(f'{name}.dma', f'{name}.data', 'AXI4 pending', 'planned'),
                  link(f'{name}.data', f'{name}.sram', 'local', 'planned')]
    else:
        lines.append(link(f'{name}.ingress', f'{name}.data', '2 AXI4 ports', 'planned'))
        for t in meta['targets']:
            lines.append(link(f'{name}.data', t['name'], 'AXI4 model in testbench', 'rtl'))
    return "\n".join(lines) + "\n"


def render(cfg: dict, meta: dict, destination: Path) -> dict:
    """Return exactly the generated files as a map for README embedding."""
    destination.mkdir(parents=True, exist_ok=True)
    arch, arch_meta = build_architecture(cfg, meta)
    rtl, rtl_meta = build_rtl_connectivity(cfg, meta)
    dv, dv_meta = build_verification(cfg, meta)
    diagrams = {"architecture": arch, "rtl-connectivity": rtl, "verification": dv}
    for inst in meta["subsystems"]:
        diagrams[f'subsystems/{inst["name"]}'] = build_subsystem(cfg, meta, inst)
    for name, diagram in diagrams.items():
        path = destination / f"{name}.mmd"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(diagram)
        title = name.replace("-", " ").replace("/", " / ").title()
        (destination / f"{name}.md").write_text(
            f"# {title}\n\nGenerated from `config/soc.yaml`. Do not edit.\n\n"
            f"```mermaid\n{diagram}```\n"
        )
    graph_meta = {"architecture": arch_meta, "rtl_connectivity": rtl_meta, "verification": dv_meta}
    (destination / "graphs.json").write_text(json.dumps(graph_meta, indent=2, sort_keys=True) + "\n")
    return diagrams
