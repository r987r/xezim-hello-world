#!/usr/bin/env python3
"""Validate a vendor-neutral SoC architecture and generate scoped AXI4 memory DV.

The memory boundary instantiates real open-source AXI fabric RTL and behavioral
AXI memory models. Physical HBM/DDR controller integration is a separate scope.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml
from noc_backends import BACKENDS, BackendError, get_backend, emit_memory_crossbar_parameters

ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    pass


def integer(value):
    if isinstance(value, bool):
        raise ConfigError("boolean provided instead of an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ConfigError(f"not an integer: {value!r}")


def check_region_map(rows, width, plane):
    seen_names = set()
    regions = []
    for row in rows:
        name = row["name"]
        if name in seen_names:
            raise ConfigError(f"duplicate {plane} target {name}")
        seen_names.add(name)
        base, size = integer(row["base"]), integer(row["size"])
        if base < 0 or size <= 0 or size & (size - 1):
            raise ConfigError(f"{plane}:{name} requires a positive power-of-two size")
        if base % size:
            raise ConfigError(f"{plane}:{name} base must align to its size")
        if base + size > (1 << width):
            raise ConfigError(f"{plane}:{name} exceeds {width}-bit address space")
        for prev_base, prev_size, prev_name in regions:
            if base < prev_base + prev_size and prev_base < base + size:
                raise ConfigError(f"{plane} address overlap: {name} and {prev_name}")
        regions.append((base, size, name))
    return regions


def validate(doc):
    if doc.get("schema_version") != 2:
        raise ConfigError("schema_version must be 2")
    buses = doc["buses"]
    d, c = buses["data"], buses["config"]
    if d["protocol"] != "axi4" or c["protocol"] != "axi4_lite":
        raise ConfigError("expected AXI4 data and AXI4-Lite config planes")
    aw, dw, iw = (integer(d[k]) for k in ("addr_bits", "data_bits", "id_bits"))
    if aw not in (32, 64) or dw not in (32, 64, 128, 256) or not 1 <= iw <= 16:
        raise ConfigError("unsupported AXI data/address/ID widths")
    config_aw = integer(c["addr_bits"])
    if config_aw not in (32, 64):
        raise ConfigError("unsupported config address width")
    data_ranges = check_region_map(doc["address_map"]["data"], aw, "data")
    config_ranges = check_region_map(doc["address_map"]["config"], config_aw, "config")

    instances = doc["subsystems"]
    names = [s["name"] for s in instances]
    if len(names) != len(set(names)):
        raise ConfigError("duplicate subsystem name")
    types = doc["subsystem_types"]
    for sub in instances:
        if sub["type"] not in types:
            raise ConfigError(f"unknown subsystem type {sub['type']}")
    compute = [s for s in instances if s["type"] == "compute"]
    valid_cpus = {"picorv32": ("axi4_lite", "picorv32_axi"),
                  "serv": ("wishbone", "serv_wishbone")}
    cpu_instances = []
    for sub in compute:
        spec = sub.get("cpu", {})
        ip = spec.get("ip")
        if ip not in valid_cpus:
            raise ConfigError(f"{sub['name']}: unknown CPU IP {ip}")
        if (spec.get("bus"), spec.get("adapter")) != valid_cpus[ip]:
            raise ConfigError(f"{sub['name']}: incorrect bus/adapter for CPU {ip}")
        cpu_instances.append({"subsystem": sub["name"], "ip": ip,
                              "bus": spec["bus"], "adapter": spec["adapter"]})
    if types["compute"]["dma"] != "pulp_idma":
        raise ConfigError("compute template currently requires common pulp_idma")

    memories = [s for s in instances if s["type"] == "memory"]
    if len(memories) != 1:
        raise ConfigError("memory DV requires exactly one memory subsystem")
    memory_name = memories[0]["name"]
    ingress = integer(types["memory"]["data_ingress_ports"])
    tb_ingress = integer(doc["verification"]["memory"]["ingress_master_agents"])
    if ingress != tb_ingress:
        raise ConfigError("memory TB master agents must match memory ingress ports")
    if not 1 <= ingress <= 16:
        raise ConfigError("memory ingress count must be between 1 and 16")
    if iw + (ingress - 1).bit_length() > 24:
        raise ConfigError("master ID width grows too wide for the test harness")

    targets = []
    for entry in doc["memory_targets"]:
        name, kind = entry["name"], entry["kind"]
        if kind not in ("hbm", "ddr"):
            raise ConfigError(f"unsupported memory kind {kind}: {name}")
        if not name.startswith(memory_name + "."):
            raise ConfigError(f"memory target {name} not in memory subsystem {memory_name}")
        controller = entry["controller"]
        expected = {"hbm": "hisa_hbm", "ddr": "litedram"}[kind]
        if controller != expected:
            raise ConfigError(f"{name}: unsupported {kind} controller {controller}")
        sim = entry["simulation"]
        if sim["backend"] != "axi_ram" or not isinstance(sim["pipeline_output"], bool):
            raise ConfigError(f"{name}: only axi_ram behavioral model is currently implemented")
        matched = [(b, s) for b, s, n in data_ranges if n == name]
        if len(matched) != 1:
            raise ConfigError(f"missing or duplicate memory address window for {name}")
        targets.append({"name": name, "kind": kind, "controller": controller,
                        "sim_backend": sim["backend"],
                        "sim_pipeline": sim["pipeline_output"],
                        "base": matched[0][0], "size": matched[0][1]})
    if not 1 <= len(targets) <= 16 or len({t['name'] for t in targets}) != len(targets):
        raise ConfigError("memory target count must be 1..16 and names unique")
    if set(t['kind'] for t in targets) != {"hbm", "ddr"}:
        raise ConfigError("heterogeneous DV requires HBM and DDR memory targets")

    outs = doc["networks"]["global_data"]["outputs"]
    if len(outs) != ingress or len({x['name'] for x in outs}) != len(outs):
        raise ConfigError("global data output count/name mismatch")
    for x in outs:
        if x["target"] not in {t["name"] for t in targets}:
            raise ConfigError(f"global output {x['name']} refers to missing target")
    config_subs = doc["networks"]["global_config"]["reachable_subsystems"]
    if set(config_subs) != set(names) or len(config_subs) != len(set(config_subs)):
        raise ConfigError("global config fabric must declare each subsystem exactly once")

    fabrics = doc["fabrics"]
    for fabric in ("local_data", "local_config", "memory_data", "global_data", "global_config"):
        if fabric not in fabrics:
            raise ConfigError(f"missing fabric definition {fabric}")
        try:
            get_backend(fabrics[fabric]["backend"], require_executable=(fabric == "memory_data"))
        except BackendError as exc:
            raise ConfigError(str(exc)) from exc
    if fabrics["memory_data"]["topology"] != "crossbar":
        raise ConfigError("memory data fabric must be crossbar in first executable scope")

    mem_bits = integer(doc["verification"]["memory"]["model_address_bits"])
    beats = integer(doc["verification"]["memory"]["burst_beats"])
    if not 10 <= mem_bits <= 20 or not 1 <= beats <= 16:
        raise ConfigError("invalid backing memory model size or burst count")
    if ingress * 256 + beats * dw // 8 >= (1 << mem_bits):
        raise ConfigError("test address offsets exceed memory backing model")
    if min(t["size"] for t in targets) < 1 << mem_bits:
        raise ConfigError("backing memory model larger than a target window")
    return {"name": doc["name"], "memory_subsystem": memory_name,
            "address_bits": aw, "data_bits": dw, "id_bits": iw,
            "ingress": ingress, "targets": targets,
            "backing_addr_bits": mem_bits, "burst_beats": beats,
            "subsystems": instances, "cpu_instances": cpu_instances,
            "common_dma": types["compute"]["dma"],
            "global_data_outputs": outs, "fabrics": fabrics,
            "data_regions": [{"name": n,"base": b,"size": s} for b,s,n in data_ranges],
            "config_regions": [{"name": n,"base": b,"size": s} for b,s,n in config_ranges]}


def fabric_ir(meta):
    """Vendor-neutral intermediate representation for future NoC backends."""
    return {
        "schema_version": 1,
        "buses": {"data": {"protocol": "axi4", "width": meta["data_bits"],
                           "address_bits": meta["address_bits"], "id_bits": meta["id_bits"]},
                  "config": {"protocol": "axi4_lite"}},
        "subsystems": [s["name"] for s in meta["subsystems"]],
        "fabrics": {name: {"backend": v["backend"], "topology": v["topology"],
                           "emitter_available": BACKENDS[v["backend"]].executable}
                    for name, v in sorted(meta["fabrics"].items())},
        "memory": {"ingress_ports": meta["ingress"],
                   "targets": [t["name"] for t in meta["targets"]],
                   "routing": [{"ingress": x["name"], "target": x["target"]}
                               for x in meta["global_data_outputs"]]},
        "cpu_instances": meta["cpu_instances"],
        "common_dma": meta["common_dma"],
        "addresses": meta["data_regions"],
    }


def packed_concat(items, width):
    return "{" + ", ".join(f"{width}'h{n:0{(width+3)//4}x}" for n in reversed(items)) + "}"


def generate_top(meta):
    """Real AXI4 crossbar, two differentiated memory models, BFMs and checker."""
    ni, nt, aw, dw, iw = (meta[k] for k in ("ingress", "target_count", "address_bits", "data_bits", "id_bits"))
    mid = iw + (ni - 1).bit_length()
    bases = [t["base"] for t in meta["targets"]]
    sizes = [t["size"] for t in meta["targets"]]
    width_log2 = [s.bit_length()-1 for s in sizes]
    # Signal descriptions for the crossbar. The output port and input port
    # each use a packed vector, width = port_count * signal_width.
    channels = [
        ("awid", "ID", "in"),("awaddr","ADDR","in"),("awlen",8,"in"),("awsize",3,"in"),
        ("awburst",2,"in"),("awlock",1,"in"),("awcache",4,"in"),("awprot",3,"in"),
        ("awqos",4,"in"),("awvalid",1,"in"),("awready",1,"out"),
        ("wdata","DATA","in"),("wstrb","STRB","in"),("wlast",1,"in"),
        ("wvalid",1,"in"),("wready",1,"out"),
        ("bid","ID","out"),("bresp",2,"out"),("bvalid",1,"out"),("bready",1,"in"),
        ("arid","ID","in"),("araddr","ADDR","in"),("arlen",8,"in"),("arsize",3,"in"),
        ("arburst",2,"in"),("arlock",1,"in"),("arcache",4,"in"),("arprot",3,"in"),
        ("arqos",4,"in"),("arvalid",1,"in"),("arready",1,"out"),
        ("rid","ID","out"),("rdata","DATA","out"),("rresp",2,"out"),
        ("rlast",1,"out"),("rvalid",1,"out"),("rready",1,"in"),
    ]
    def w_expr(port, width):
        if width=="ID":return "IN_ID_BITS" if port=="s" else "OUT_ID_BITS"
        if width=="ADDR":return "ADDR_BITS"
        if width=="DATA":return "DATA_BITS"
        if width=="STRB":return "DATA_BITS/8"
        return str(width)
    lines=["`timescale 1ns/1ps", "// Generated by tools/socgen.py; do not edit.","module memory_tb;",
           f"  localparam integer N_IN = {ni};",f"  localparam integer N_MEM = {nt};",
           f"  localparam integer ADDR_BITS = {aw};",f"  localparam integer DATA_BITS = {dw};",
           f"  localparam integer IN_ID_BITS = {iw};",f"  localparam integer OUT_ID_BITS = {mid};",
           f"  localparam integer MEM_ADDR_BITS = {meta['backing_addr_bits']};",
           f"  localparam integer BURST_BEATS = {meta['burst_beats']};",
           f"  localparam [N_MEM*ADDR_BITS-1:0] TARGET_BASES = {packed_concat(bases,aw)};",
           f"  localparam [N_MEM*32-1:0] TARGET_ADDR_WIDTHS = {packed_concat(width_log2,32)};",
           "  reg clk = 0;", "  reg rst = 1;",
           "  always #5 clk = ~clk;",
           "  initial begin repeat(8) @(posedge clk); @(negedge clk); rst = 0; end",
           "  initial begin #100000; $fatal(1, \"FAIL: memory verification timeout\"); end",
           "  wire [N_IN-1:0] master_done;", ""]
    for port,pcount in (("s","N_IN"),("m","N_MEM")):
        for name,width,flow in channels:
            w=w_expr(port,width)
            lines.append(f"  wire [({pcount})*({w})-1:0] {port}_{name};")
        lines.append("")
    # Some source-side signal set directly from BFM; user fields are tied off.
    fabric_module, _ = emit_memory_crossbar_parameters(meta["fabrics"]["memory_data"]["backend"], [])
    lines.append(f"  {fabric_module} #(")
    p=[".S_COUNT(N_IN)",".M_COUNT(N_MEM)",".DATA_WIDTH(DATA_BITS)",".ADDR_WIDTH(ADDR_BITS)",
       ".S_ID_WIDTH(IN_ID_BITS)",".M_ID_WIDTH(OUT_ID_BITS)",".M_REGIONS(1)",
       ".M_BASE_ADDR(TARGET_BASES)",".M_ADDR_WIDTH(TARGET_ADDR_WIDTHS)"]
    lines.append("    "+",\n    ".join(p))
    lines.append("  ) fabric (")
    conn=[".clk(clk)",".rst(rst)"]
    for port in ("s","m"):
        for name,width,flow in channels:
            conn.append(f".{port}_axi_{name}({port}_{name})")
        if port=="s":
            conn.extend([".s_axi_awuser('0)",".s_axi_wuser('0)",".s_axi_aruser('0)",
                         ".s_axi_buser()",".s_axi_ruser()"])
        else:
            conn.extend([".m_axi_awuser()",".m_axi_wuser()",".m_axi_aruser()",
                         ".m_axi_buser('0)",".m_axi_ruser('0)",".m_axi_awregion()",".m_axi_arregion()"])
    lines.append("    "+",\n    ".join(conn))
    lines.append("  );\n")
    # Agent instances & AXI RAM models are generic in port counts (not hand-wired).
    lines.append("  for (genvar i=0; i<N_IN; i=i+1) begin : masters")
    lines.append("    axi_master_bfm #(.MASTER_INDEX(i), .N_TARGETS(N_MEM), .ADDR_BITS(ADDR_BITS),")
    lines.append("      .DATA_BITS(DATA_BITS), .ID_BITS(IN_ID_BITS), .BURST_BEATS(BURST_BEATS),")
    lines.append("      .TARGET_BASES(TARGET_BASES)) u_agent (")
    lines.append("      .clk(clk), .rst(rst), .done(master_done[i]),")
    agent=[]
    for name,width,flow in channels:
        w=w_expr("s",width)
        agent.append(f".{name}(s_{name}[i*({w}) +: ({w})])")
    lines.append("      "+",\n      ".join(agent))
    lines.append("    );\n  end\n")
    pipeline = sum((1 << i) for i, t in enumerate(meta["targets"]) if t["sim_pipeline"])
    lines.append(f"  localparam [N_MEM-1:0] SIM_PIPELINE = {len(meta['targets'])}'h{pipeline:x};")
    lines.append("  for (genvar t=0; t<N_MEM; t=t+1) begin : memories")
    lines.append("    axi_memory_target_model #(.DATA_WIDTH(DATA_BITS), .ADDR_WIDTH(MEM_ADDR_BITS), .ID_WIDTH(OUT_ID_BITS),")
    lines.append("      .PIPELINE_OUTPUT(SIM_PIPELINE[t])) u_mem (")
    lines.append("      .clk(clk), .rst(rst),")
    mem=[]
    for name,width,flow in channels:
        if name in ("awqos","arqos"):
            continue # axi_ram has no qos
        w=w_expr("m",width)
        if name in ("awaddr","araddr"):
            mem.append(f".s_axi_{name}(m_{name}[t*ADDR_BITS +: MEM_ADDR_BITS])")
        else:
            mem.append(f".s_axi_{name}(m_{name}[t*({w}) +: ({w})])")
    lines.append("      "+",\n      ".join(mem))
    lines.append("    );\n  end\n")
    lines.append("  axi_route_monitor #(.N_IN(N_IN), .N_MEM(N_MEM), .ADDR_BITS(ADDR_BITS),")
    lines.append("    .IN_ID_BITS(IN_ID_BITS), .OUT_ID_BITS(OUT_ID_BITS), .TARGET_BASES(TARGET_BASES),")
    lines.append("    .TARGET_WIDTHS(TARGET_ADDR_WIDTHS)) u_monitor (")
    lines.append("    .clk(clk), .rst(rst), .m_awvalid(m_awvalid), .m_awready(m_awready),")
    lines.append("    .m_awaddr(m_awaddr), .m_awid(m_awid), .m_arvalid(m_arvalid),")
    lines.append("    .m_arready(m_arready), .m_araddr(m_araddr), .m_arid(m_arid));")
    for i,t in enumerate(meta["targets"]):
        lines.append(f'  initial $display("MEMORY TARGET {i}: {t["name"]} kind={t["kind"]} model={t["sim_backend"]}");')
    lines.append("  initial begin")
    lines.append("    wait (&master_done);")
    lines.append("    repeat (3) @(posedge clk);")
    lines.append("    u_monitor.check_coverage();")
    lines.append("    $display(\"PASS: memory_fabric_tb %0d ingress x %0d memory targets\", N_IN, N_MEM);")
    lines.append("    $finish;")
    lines.append("  end")
    lines.append("endmodule")
    return "\n".join(lines)+"\n"


def run(config_file: Path, output_dir: Path):
    try:
        doc = yaml.safe_load(config_file.read_text())
        meta = validate(doc)
    except (ValueError, KeyError, yaml.YAMLError) as exc:
        raise ConfigError(str(exc)) from exc
    meta["target_count"] = len(meta["targets"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir/"memory_tb.sv").write_text(generate_top(meta))
    (output_dir/"manifest.json").write_text(json.dumps(meta, indent=2)+"\n")
    noc_dir=output_dir.parent / "noc"
    noc_dir.mkdir(parents=True,exist_ok=True)
    (noc_dir/"fabric_ir.json").write_text(json.dumps(fabric_ir(meta),indent=2)+"\n")
    print(f"Validated {len(meta['subsystems'])} subsystems; heterogeneous memory DV: {meta['ingress']} ingress x {meta['target_count']} targets")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=ROOT/"config/soc.yaml")
    parser.add_argument("--out",type=Path,default=ROOT/"generated/memory")
    args=parser.parse_args()
    try:
        run(args.config,args.out)
    except ConfigError as exc:
        print("Configuration error:",exc,file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
