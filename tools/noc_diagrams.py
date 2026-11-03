"""Document the real FlooGen router/endpoint topology across the whole SoC.

Consumes generator-owned FlooGen YAML + manifest (NOT an independently
maintained diagram topology). Emits Mermaid, standalone SVG and Diagram-gen
compatible JSON metadata with physical-versus-planned connectivity labeled.
No FlooNoC RTL code or custom AXI adapters are produced here.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any

import yaml


def identifier(name: str) -> str:
    return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", name)


def read_generated_nocs(root: Path) -> dict[str, dict]:
    if not (root / "manifest.json").is_file():
        raise ValueError("checked-in FlooGen network manifest is missing")
    manifest = json.loads((root / "manifest.json").read_text())
    networks = {}
    for name, entry in sorted(manifest["networks"].items()):
        conf = yaml.safe_load((root / entry["config"]).read_text())
        routers = conf["routers"]
        if len(routers) != 1 or routers[0]["name"] != "router":
            raise ValueError(f"{name}: expected a single regular FlooGen router array")
        w, h = routers[0]["array"]
        if type(w) is not int or type(h) is not int or not 1 <= w <= 32 or not 1 <= h <= 32:
            raise ValueError(f"{name}: invalid router array size")
        if w * h != entry["routers"]:
            raise ValueError(f"{name}: router count differs from generated manifest")
        endpoints = {e["name"]: e for e in conf["endpoints"]}
        if len(endpoints) != entry["endpoint_count"]:
            raise ValueError(f"{name}: endpoints differ from generated manifest")
        positions = {}
        for connection in conf["connections"]:
            ep = connection["src"]
            x, y = connection["dst_idx"]
            if connection["dst"] != "router" or connection["dst_dir"] != "Eject":
                raise ValueError(f"{name}: unsupported connection, expected FlooGen Eject")
            if ep not in endpoints or ep in positions or not 0 <= x < w or not 0 <= y < h:
                raise ValueError(f"{name}: invalid, duplicated or out-of-range endpoint {ep}")
            positions[ep] = (x, y)
        if set(positions) != set(endpoints):
            raise ValueError(f"{name}: not all FlooGen endpoints attach to routers")
        if conf["network_type"] != "axi" or conf["routing"]["route_algo"] != "XY":
            raise ValueError(f"{name}: unexpected FlooGen protocol or routing")
        networks[name] = {"config": conf, "entry": entry, "width": w,
                          "height": h, "endpoints": endpoints, "positions": positions}
    if len(networks) != manifest["networks"].__len__():
        raise ValueError("network names must be unique")
    return networks


def _inst(network: str, what: str) -> str:
    return f"{network}.{what}"


def diagram_gen_metadata(cfg: dict, networks: dict) -> dict:
    """Instances/connections/groups model also understood by Diagram-gen viewers.

    Router-to-router and router-to-chimney are generated *structural* RTL.
    NoC-to-NoC bridges and CPU/DMA/endpoints are *planned*, not wired SoC RTL.
    """
    modules = {
        "floo_axi_router": {"description": "Real upstream FlooNoC router", "color": "#14845A", "ports": []},
        "floo_axi_chimney": {"description": "Real upstream AXI network interface", "color": "#2877B5", "ports": []},
        "soc_boundary": {"description": "Planned SoC component or protocol adapter", "color": "#64748B", "ports": []},
        "axi_crossbar": {"description": "Existing standalone Verilog-AXI memory crossbar", "color": "#16A34A", "ports": []},
    }
    instances = []
    connections = []
    groups = []
    next_id = 0

    def edge(src, dst, name, status, width=None, ports=("out", "in")):
        nonlocal next_id
        next_id += 1
        info = {"id": f"noc_link_{next_id:04d}", "name": name,
                "from": {"instance": src, "port": ports[0]},
                "to": {"instance": dst, "port": ports[1]},
                "type": "noc_link" if status == "generated_structural" else "planned_interconnect",
                "status": status,
                "signals": [{"name": "floo_req_and_rsp", "width": None}]
                           if status == "generated_structural" else
                           [{"name": "AXI4", "width": width}] if width is not None else [],
        }
        connections.append(info)

    for index, (name, net) in enumerate(networks.items()):
        conf, entry = net["config"], net["entry"]
        plane = entry["plane"]
        color = "#16845D" if plane == "data" else "#8055B7"
        group_members = []
        nx, ny = net["width"], net["height"]
        px, py = 16 * (index % 2), 16 * (index // 2)
        protocol = {p["name"]: p for p in conf["protocols"]}
        for y in range(ny):
            for x in range(nx):
                rname = _inst(name, f"router_{x}_{y}")
                group_members.append(rname)
                instances.append({
                    "name": rname, "module": "floo_axi_router",
                    "position": {"x": px + x * 4, "y": py + y * 4, "z": 0},
                    "info": {"network": name, "plane": plane, "grid": [x, y],
                             "status": "generated_structural",
                             "source": entry["top"]},
                })
                if x:
                    edge(_inst(name, f"router_{x-1}_{y}"), rname,
                         "east/west FlooNoC request+response links", "generated_structural",
                         ports=("E", "W"))
                if y:
                    edge(_inst(name, f"router_{x}_{y-1}"), rname,
                         "north/south FlooNoC request+response links", "generated_structural",
                         ports=("S", "N"))
        for epname, ep in net["endpoints"].items():
            x, y = net["positions"][epname]
            ep_id = _inst(name, epname)
            proto_name = (ep.get("mgr_port_protocol") or ep.get("sbr_port_protocol"))[0]
            proto = protocol[proto_name]
            group_members.append(ep_id)
            instances.append({
                "name": ep_id, "module": "floo_axi_chimney",
                "position": {"x": px + x * 4, "y": py + y * 4 - 1.6, "z": 0},
                "info": {
                    "network": name, "plane": plane,
                    "role": "initiator" if ep.get("mgr_port_protocol") else "target",
                    "protocol": "AXI4", "data_bits": proto["data_width"],
                    "address_bits": proto["addr_width"], "id_bits": proto["id_width"],
                    "address_ranges": ep.get("addr_range"),
                    "status": "generated_structural",
                    "source": entry["top"],
                },
            })
            edge(ep_id, _inst(name, f"router_{x}_{y}"),
                 f"{epname} NI Eject", "generated_structural", ports=("NoC", "Eject"))
        groups.append({"name": name, "instances": group_members,
                       "color": color, "padding": 2.0,
                       "info": {"plane": plane, "router_count": entry["routers"],
                                "source": entry["top"], "status": "generated_structural"}})

    # Show actual CPU/DMA/SRAM/CSR block boundaries in Diagram-gen too.
    # Their links to the generated FlooNoCs are PLANNED, not instantiated.
    for ci, subsystem in enumerate(s for s in cfg["subsystems"] if s["type"] == "compute"):
        name = subsystem["name"]
        for suffix, kind in (("cpu", subsystem["cpu"]["ip"]), ("dma", cfg["subsystem_types"]["compute"]["dma"]),
                             ("sram", "local_sram"), ("dma_csr", "dma_registers")):
            instances.append({"name": f"{name}.{suffix}", "module": "soc_boundary",
                              "position": {"x": 20 + ci * 12, "y": 72 + 3 * len(instances) % 12, "z": 0},
                              "info": {"ip": kind, "status": "planned_noc_endpoint_integration"}})
        ld, lc = name+"_local_data", name+"_local_config"
        edge(name+".cpu", _inst(ld,"cpu"), "CPU adapter to local data", "planned_integration", width=64)
        edge(name+".cpu", _inst(lc,"cpu"), "upstream protocol-to-AXI4-Lite adapter", "planned_integration", width=32)
        edge(name+".dma", _inst(ld,"dma"), "PULP iDMA AXI4 initiator", "planned_integration", width=64)
        edge(_inst(ld,"sram"), name+".sram", "local SRAM AXI destination", "planned_integration", width=64)
        edge(_inst(lc,"dma_regs"), name+".dma_csr", "PULP iDMA CSR port", "planned_integration", width=32)
        if name == cfg["boot"]["primary"]:
            instances.append({"name": name+".reset_ctrl", "module": "soc_boundary",
                              "position": {"x": 20, "y": 89, "z": 0},
                              "info": {"status": "planned_noc_endpoint_integration"}})
            edge(_inst(lc,"reset_ctrl"), name+".reset_ctrl",
                 "reset-control CSR", "planned_integration", width=32)

    # These are planned inter-fabric and subsystem endpoint links. Never
    # present them as real continuous RTL until an actual SoC top is compiled.
    for compute in (s["name"] for s in cfg["subsystems"] if s["type"] == "compute"):
        ld = compute + "_local_data"
        lc = compute + "_local_config"
        edge(_inst(ld, "global_out"), _inst("global_data", compute),
             "64b AXI4 uplink (planned)", "planned_integration", width=64)
        edge(_inst("global_data", compute + "_sram"), _inst(ld, "global_in"),
             "64b AXI4 remote SRAM return path (planned)", "planned_integration", width=64)
        edge(_inst(lc, "global_out"), _inst("global_config", compute),
             "32b AXI4 control transport (planned)", "planned_integration", width=32)
        edge(_inst("global_config", compute + "_regs"), _inst(lc, "global_in"),
             "32b AXI4 control ingress (planned)", "planned_integration", width=32)

    memory = next(s["name"] for s in cfg["subsystems"] if s["type"] == "memory")
    for output in cfg["networks"]["global_data"]["outputs"]:
        name = output["name"]
        edge(_inst("global_data", name), _inst(memory + "_local_data", name),
             "64b AXI4 memory ingress (planned)", "planned_integration", width=64)
    edge(_inst("global_config", memory + "_regs"),
         _inst(memory + "_local_config", "global_in"),
         "32b AXI4 memory control (planned)", "planned_integration", width=32)

    xbar = memory + ".internal_target_crossbar"
    instances.append({"name": xbar, "module": "axi_crossbar",
                      "position": {"x": 8, "y": 80, "z": 0},
                      "info": {"status": "verified_separate_memory_tb",
                               "source": "gen/memory/memory_tb.sv"}})
    edge(_inst(memory + "_local_data", "target_crossbar"), xbar,
         "memory0 local-to-crossbar link (planned)", "planned_integration", width=64)
    instances.append({"name": memory + ".ctrl", "module": "soc_boundary",
                      "position": {"x": 21, "y": 90, "z": 0},
                      "info": {"status": "reserved_controller_csr_no_RTL"}})
    edge(_inst(memory+"_local_config", "controller_regs"), memory+".ctrl",
         "reserved memory controller CSR", "planned_integration", width=32)
    for target in cfg["memory_targets"]:
        ep = target["name"]
        instances.append({"name": ep, "module": "soc_boundary",
                          "position": {"x": 8, "y": 85 + 3 * len(instances) % 9, "z": 0},
                          "info": {"status": "verified_separate_memory_tb",
                                   "kind": target["kind"], "model": "axi_ram"}})
        edge(xbar, ep, "Memory0 testbench AXI RAM route", "verified_separate_memory_tb", width=64)

    for sub in cfg["subsystems"]:
        prefix = sub["name"] + "_"
        group_members = [e["name"] for e in instances if
                         e["name"].startswith(prefix) or e["name"].startswith(sub["name"] + ".")]
        if group_members:
            groups.append({"name": sub["name"] + "_subsystem", "instances": group_members,
                           "color": "#62758C", "padding": 4.0})
    assert all(x["from"]["instance"] in {i["name"] for i in instances} and
               x["to"]["instance"] in {i["name"] for i in instances} for x in connections)
    return {
        "schema_version": 1,
        "source_of_truth": ["config/soc.yaml", "config/interface_contracts.yaml",
                            "gen/noc/floonoc/*/floogen.yaml"],
        "status": "real_structural_networks_with_planned_inter_network_links",
        "scope_note": "Cross-NoC wiring exists in gen/supernoc/supernoc_tb.sv; full SoC endpoint integration is planned",
        "modules": modules, "instances": instances, "connections": connections, "groups": groups,
        "networks": {name: {"plane": net["entry"]["plane"], "routers": net["entry"]["routers"],
                            "endpoints": len(net["endpoints"]), "top": net["entry"]["top"],
                            "config": net["entry"]["config"]}
                     for name, net in networks.items()},
    }


def hierarchy_mermaid(cfg: dict, networks: dict) -> str:
    lines = [
        "flowchart TB",
        "  classDef data fill:#e6f6ec,stroke:#188459,color:#143b2b;",
        "  classDef config fill:#f3edfd,stroke:#7047b5,color:#342451;",
        "  classDef model fill:#f5f6f7,stroke:#7b8794,color:#233047;",
        "  classDef verified fill:#e4f8e8,stroke:#228450,color:#12432b;",
        "  %% All FlooNoC internal router and NI RTL is generated.",
        "  %% Every dashed subsystem-to-NoC connection remains unimplemented.",
    ]
    def node(id, label, kind):
        lines.append('  ' + identifier(id) + '["' + label + '"]:::' + kind)

    def planned(src, dst, label):
        lines.append("  " + identifier(src) + ' -.->|' + label + '| ' + identifier(dst))

    memory = next(x["name"] for x in cfg["subsystems"] if x["type"] == "memory")
    computes = [x for x in cfg["subsystems"] if x["type"] == "compute"]
    for c in computes:
        name = c["name"]
        ld, lc = name+"_local_data", name+"_local_config"
        lines.append(f'  subgraph {identifier(name+"_box")}["{name} / compute subsystem"]')
        node(name+".cpu", c["cpu"]["ip"] + " CPU", "model")
        node(name+".dma", "PULP iDMA (planned)", "model")
        node(name+".sram", "Local SRAM", "model")
        node(ld, f"Local DATA FlooNoC / {networks[ld]['entry']['routers']} routers / AXI4", "data")
        node(lc, f"Local CONFIG FlooNoC / {networks[lc]['entry']['routers']} routers / 32-bit AXI4 transport", "config")
        lines.append("  end")
        planned(name+".cpu", ld, "CPU adapter")
        planned(name+".dma", ld, "DMA")
        planned(ld, name+".sram", "local")
        planned(name+".cpu", lc, "AXI-Lite bridge")
        planned(ld, "global_data", "global data")
        planned(lc, "global_config", "global control")
    for name, color in (("global_data", "data"), ("global_config", "config")):
        n = networks[name]
        bits = "64b AXI4" if color == "data" else "32b AXI4 via AXI-Lite bridges"
        node(name, f"{name} FlooNoC / {n['entry']['routers']} routers / {bits}", color)

    lines.append(f'  subgraph {identifier(memory+"_box")}["{memory} / memory subsystem"]')
    node(memory+"_local_data", "Local DATA FlooNoC / "
         + str(networks[memory+"_local_data"]["entry"]["routers"])+" routers", "data")
    node(memory+"_local_config", "Local CONFIG FlooNoC / "
         + str(networks[memory+"_local_config"]["entry"]["routers"])+" routers", "config")
    node("xbar", "Internal Verilog-AXI 2x2 crossbar (standalone RTL tested)", "verified")
    for target in cfg["memory_targets"]:
        node(target["name"], target["kind"].upper()+" AXI RAM model", "model")
    lines.append("  end")
    for c in computes:
        planned("global_data", c["name"]+"_local_data", "remote SRAM ingress")
        planned("global_config", c["name"]+"_local_config", "CSR ingress")
    for output in cfg["networks"]["global_data"]["outputs"]:
        planned("global_data", memory+"_local_data", output["name"])
    planned("global_config", memory+"_local_config", "control ingress")
    planned(memory+"_local_data", "xbar", "AXI4")
    for target in cfg["memory_targets"]:
        lines.append("  " + identifier("xbar") + " -->|" + target["kind"].upper()
                     + " tested separately| " + identifier(target["name"]))
    lines.append("  %% Solid crossbar paths are only proven in a standalone memory TB.")
    return "\n".join(lines)+"\n"


def overview_svg(cfg: dict, networks: dict, dst: Path):
    from diagram_svg import Art, BG, WHITE, INK, MUTED, FAINT, GREEN, PURPLE, BLUE, ORANGE
    computes=[s for s in cfg["subsystems"] if s["type"]=="compute"]
    mem=next(s["name"] for s in cfg["subsystems"] if s["type"]=="memory")
    columns=2
    rows=math.ceil(len(computes)/columns)
    gy=172+rows*285+32
    my=gy+181
    h=my+360
    a=Art(1600,h)
    a.heading("Real upstream-generated NoC hierarchy","Full-chip FlooNoC network map",
              f"{len(networks)} generated meshes; dashed links show pending full-SoC integration (see the separate NoC BFM test)")
    for i, compute in enumerate(computes):
        name=compute["name"];x=56+(i%2)*784;y=158+(i//2)*285
        a.rect(x,y,744,267,WHITE,FAINT,r=17,width=2)
        a.text(x+18,y+14,name+" / compute subsystem",22,INK)
        a.box_label(x+18,y+50,220,76,compute["cpu"]["ip"]+" CPU",
                    compute["cpu"]["bus"]+" adapter pending","cpu",title_size=19,detail_size=13)
        a.box_label(x+255,y+50,213,76,"PULP iDMA + CSR","IP wiring pending","dma",title_size=19,detail_size=14)
        a.box_label(x+486,y+50,235,76,"Local SRAM","global remote address", "memory",title_size=19,detail_size=13)
        ld=name+"_local_data";lc=name+"_local_config"
        a.box_label(x+18,y+155,351,81,"LOCAL DATA  /  FlooNoC",
                    str(networks[ld]["entry"]["routers"])+" generated routers / 64b AXI4", "fabric",
                    title_size=19,detail_size=15)
        a.box_label(x+386,y+155,335,81,"LOCAL CONFIG  /  FlooNoC",
                    str(networks[lc]["entry"]["routers"])+" generated routers / 32b AXI4", "config",
                    title_size=19,detail_size=15)
        a.line([(x+129,y+126),(x+129,y+155)],BLUE,2,True,True)
        a.line([(x+360,y+126),(x+280,y+155)],BLUE,2,True,True)
        a.line([(x+128,y+126),(x+553,y+155)],PURPLE,2,True,True)
        a.line([(x+320,y+155),(x+603,y+126)],GREEN,2,True,True)
        a.line([(x+553,y+155),(x+400,y+126)],PURPLE,2,True,True)
    a.box_label(56,gy,744,113,"GLOBAL DATA / FlooNoC",
                str(networks["global_data"]["entry"]["routers"])+" routers / XY mesh / 64-bit AXI4\ncompute uplinks, remote SRAMs, configured memory ingress ports",
                "fabric",title_size=24,detail_size=15)
    a.box_label(840,gy,704,113,"GLOBAL CONFIG / FlooNoC",
                str(networks["global_config"]["entry"]["routers"])+" routers / XY mesh / 32-bit AXI4\nPULP upstream AXI4-Lite bridges required at CSR boundaries",
                "config",title_size=24,detail_size=15)
    for i,c in enumerate(computes):
        x=56+(i%2)*784
        y=158+(i//2)*285+236
        a.line([(x+192,y),(x+192,y+40),(428,gy-10),(428,gy)],GREEN,2,True,"both")
        a.line([(x+555,y),(x+555,y+44),(1193,gy-10),(1193,gy)],PURPLE,2,True,"both")
    a.rect(56,my,1488,307,WHITE,FAINT,r=17,width=2)
    a.text(82,my+18,mem+" / memory subsystem",24,INK)
    a.box_label(83,my+64,500,71,"LOCAL DATA / FlooNoC",
                str(networks[mem+"_local_data"]["entry"]["routers"])+" routers / two AXI ingress ports",
                "fabric",title_size=20,detail_size=14)
    a.box_label(622,my+64,485,71,"LOCAL CONFIG / FlooNoC",
                str(networks[mem+"_local_config"]["entry"]["routers"])+" generated routers / CSR bridge pending",
                "config",title_size=20,detail_size=14)
    a.box_label(1142,my+64,375,71,"Controller CSRs",
                "Upstream AXI-Lite bridge pending", "config",title_size=20,detail_size=14)
    a.line([(1107,my+100),(1142,my+100)],PURPLE,2,True,True)
    a.box_label(83,my+171,702,75,"Internal 2x2 Verilog-AXI crossbar",
                "Real independently tested memory fabric RTL","rtl",title_size=22,detail_size=15)
    targets=cfg["memory_targets"]
    for j,t in enumerate(targets):
        tx=810+j*363
        a.box_label(tx,my+170,346,78,t["kind"].upper()+" AXI RAM",
                    "Behavioral model; physical controller pending",
                    "memory",title_size=20,detail_size=14)
        if j == 0:
            a.line([(785,my+208),(tx,my+208)],GREEN,2,False,True)
        else:
            a.line([(785,my+220),(795,my+220),(795,my+259),
                    (tx+173,my+259),(tx+173,my+248)],GREEN,2,False,True)
    outputs=cfg["networks"]["global_data"]["outputs"]
    for i, output in enumerate(outputs):
        x=320+(i-(len(outputs)-1)/2)*60
        a.line([(x,gy+113),(x,my+64)],GREEN,3,True,True)
    a.text(390,my+48,f"{len(outputs)} AXI4 ingress ports",12,MUTED)
    a.line([(1193,gy+113),(1193,my+42),(864,my+42),(864,my+64)],PURPLE,3,True,True)
    a.line([(320,my+135),(320,my+171)],GREEN,2,True,True)
    a.text(83,my+274,
           "Solid target links: standalone memory testbench ONLY. Full SoC NoC links and endpoint bridges: planned.",
           17,MUTED)
    a.text(65,h-29,
           "Router coordinates and link details: gen/diagrams/noc-topology.json and gen/noc/floonoc/*/floogen.yaml.",
           15,MUTED)
    a.save(dst)


def render(cfg: dict, root: Path, destination: Path) -> tuple[dict, dict[str,str]]:
    """Write Diagram-gen JSON and Mermaid/SVG from *actual emitted* FlooGen configs."""
    networks = read_generated_nocs(root)
    expected = 2 + 2 * len(cfg["subsystems"])
    if len(networks) != expected:
        raise ValueError(f"expected {expected} independent FlooNoC networks, got {len(networks)}")
    # One visual per SoC. Detailed topology remains machine-readable JSON
    # sourced from FlooGen, without eight redundant mesh SVG/MD/MMD files.
    mermaid = {"noc-hierarchy": hierarchy_mermaid(cfg, networks)}
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "noc-hierarchy.mmd").write_text(mermaid["noc-hierarchy"])
    overview_svg(cfg, networks, destination / "noc-hierarchy.svg")
    graph = diagram_gen_metadata(cfg, networks)
    (destination / "noc-topology.json").write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n")
    return graph, mermaid
