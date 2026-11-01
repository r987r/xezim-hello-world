#!/usr/bin/env python3
"""Validate SoC architecture and emit a reproducible, scoped HBM DV harness.

No hard-coded addresses in the testbench: generated parameters and DV manifest
come from config/soc.yaml. This stage deliberately tests the HBM subsystem
fabric while the CPU, DMA, global NoCs and actual HBM controllers remain
boundary models / future integration scopes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import yaml

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
    if doc.get("schema_version") != 1:
        raise ConfigError("schema_version must be 1")
    buses = doc["buses"]
    d = buses["data"]
    c = buses["config"]
    if d["protocol"] != "axi4" or c["protocol"] != "axi4_lite":
        raise ConfigError("expected AXI4 data and AXI4-Lite config planes")
    aw, dw, iw = (integer(d[k]) for k in ("addr_bits", "data_bits", "id_bits"))
    if aw not in (32, 64) or dw not in (32, 64, 128, 256) or not 1 <= iw <= 16:
        raise ConfigError("unsupported AXI data/address/ID widths")
    config_aw = integer(c["addr_bits"])
    if config_aw not in (32, 64):
        raise ConfigError("unsupported config address width")
    data_ranges = check_region_map(doc["address_map"]["data"], aw, "data")
    check_region_map(doc["address_map"]["config"], config_aw, "config")
    instances = doc["subsystems"]
    names = [s["name"] for s in instances]
    if len(names) != len(set(names)):
        raise ConfigError("duplicate subsystem name")
    types = doc["subsystem_types"]
    for sub in instances:
        if sub["type"] not in types:
            raise ConfigError(f"unknown subsystem type {sub['type']}")
    hbm_subs = [s for s in instances if s["type"] == "hbm"]
    if len(hbm_subs) != 1:
        raise ConfigError("the first HBM DV harness requires exactly one HBM subsystem")
    hbm_name = hbm_subs[0]["name"]
    template = types["hbm"]
    hbm_count = integer(template["hbm_controllers"])
    ingress = integer(template["data_noc"]["ingress_ports"])
    tb_ingress = integer(doc["verification"]["hbm"]["ingress_master_agents"])
    if ingress != tb_ingress:
        raise ConfigError("HBM TB master agents must match HBM ingress ports")
    if not 1 <= ingress <= 16 or not 1 <= hbm_count <= 16:
        raise ConfigError("HBM ingress/target count must be between 1 and 16")
    if iw + (ingress - 1).bit_length() > 24:
        raise ConfigError("master ID width grows too wide for the test harness")
    targets = []
    for idx in range(hbm_count):
        name = f"{hbm_name}.hbm{idx}"
        match = [(base, size) for base, size, n in data_ranges if n == name]
        if len(match) != 1:
            raise ConfigError(f"missing HBM region for {name}")
        targets.append({"name": name, "base": match[0][0], "size": match[0][1]})
    outs = doc["networks"]["global_data"]["hbm_outputs"]
    if len(outs) != ingress or len({x['name'] for x in outs}) != len(outs):
        raise ConfigError("global data ingress interface count/name mismatch")
    for x in outs:
        if x["target"] not in {p["name"] for p in targets}:
            raise ConfigError(f"global output {x['name']} refers to missing target")
    mem_bits = integer(doc["verification"]["hbm"]["model_address_bits"])
    beats = integer(doc["verification"]["hbm"]["burst_beats"])
    if not 10 <= mem_bits <= 20 or not 1 <= beats <= 16:
        raise ConfigError("invalid backing memory model size or burst count")
    if ingress * 256 + beats * dw // 8 >= (1 << mem_bits):
        raise ConfigError("test address offsets exceed memory backing model")
    if min(t["size"] for t in targets) < 1 << mem_bits:
        raise ConfigError("backing memory model larger than the mapped target window")
    return {"name": doc["name"], "hbm_subsystem": hbm_name,
            "address_bits": aw, "data_bits": dw, "id_bits": iw,
            "ingress": ingress, "targets": targets, "backing_addr_bits": mem_bits,
            "burst_beats": beats, "subsystems": instances,
            "global_data_outputs": outs,
            "data_regions": [{"name": n,"base":b,"size":s} for b,s,n in data_ranges],
            "config_regions": [{"name":r["name"],"base":integer(r["base"]),"size":integer(r["size"])} for r in doc["address_map"]["config"]]}


def packed_concat(items, width):
    return "{" + ", ".join(f"{width}'h{n:0{(width+3)//4}x}" for n in reversed(items)) + "}"


def generate_top(meta):
    """A *real* AXI4 crossbar, AXI4 DRAM models, BFMs, and a route monitor."""
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
    lines=["`timescale 1ns/1ps", "// Generated by tools/socgen.py; do not edit.","module hbm_tb;",
           f"  localparam integer N_IN = {ni};",f"  localparam integer N_HBM = {nt};",
           f"  localparam integer ADDR_BITS = {aw};",f"  localparam integer DATA_BITS = {dw};",
           f"  localparam integer IN_ID_BITS = {iw};",f"  localparam integer OUT_ID_BITS = {mid};",
           f"  localparam integer MEM_ADDR_BITS = {meta['backing_addr_bits']};",
           f"  localparam integer BURST_BEATS = {meta['burst_beats']};",
           f"  localparam [N_HBM*ADDR_BITS-1:0] HBM_BASES = {packed_concat(bases,aw)};",
           f"  localparam [N_HBM*32-1:0] HBM_ADDR_WIDTHS = {packed_concat(width_log2,32)};",
           "  reg clk = 0;", "  reg rst = 1;",
           "  always #5 clk = ~clk;",
           "  initial begin repeat(8) @(posedge clk); @(negedge clk); rst = 0; end",
           "  initial begin #100000; $fatal(1, \"FAIL: HBM verification timeout\"); end",
           "  wire [N_IN-1:0] master_done;", ""]
    for port,pcount in (("s","N_IN"),("m","N_HBM")):
        for name,width,flow in channels:
            w=w_expr(port,width)
            lines.append(f"  wire [({pcount})*({w})-1:0] {port}_{name};")
        lines.append("")
    # Some source-side signal set directly from BFM; user fields are tied off.
    lines.append("  axi_crossbar #(")
    p=[".S_COUNT(N_IN)",".M_COUNT(N_HBM)",".DATA_WIDTH(DATA_BITS)",".ADDR_WIDTH(ADDR_BITS)",
       ".S_ID_WIDTH(IN_ID_BITS)",".M_ID_WIDTH(OUT_ID_BITS)",".M_REGIONS(1)",
       ".M_BASE_ADDR(HBM_BASES)",".M_ADDR_WIDTH(HBM_ADDR_WIDTHS)"]
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
    lines.append("    axi_master_bfm #(.MASTER_INDEX(i), .N_TARGETS(N_HBM), .ADDR_BITS(ADDR_BITS),")
    lines.append("      .DATA_BITS(DATA_BITS), .ID_BITS(IN_ID_BITS), .BURST_BEATS(BURST_BEATS),")
    lines.append("      .TARGET_BASES(HBM_BASES)) u_agent (")
    lines.append("      .clk(clk), .rst(rst), .done(master_done[i]),")
    agent=[]
    for name,width,flow in channels:
        w=w_expr("s",width)
        agent.append(f".{name}(s_{name}[i*({w}) +: ({w})])")
    lines.append("      "+",\n      ".join(agent))
    lines.append("    );\n  end\n")
    lines.append("  for (genvar t=0; t<N_HBM; t=t+1) begin : memories")
    lines.append("    axi_ram #(.DATA_WIDTH(DATA_BITS), .ADDR_WIDTH(MEM_ADDR_BITS), .ID_WIDTH(OUT_ID_BITS),")
    lines.append("      .PIPELINE_OUTPUT(1)) u_ram (")
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
    lines.append("  axi_route_monitor #(.N_IN(N_IN), .N_HBM(N_HBM), .ADDR_BITS(ADDR_BITS),")
    lines.append("    .IN_ID_BITS(IN_ID_BITS), .OUT_ID_BITS(OUT_ID_BITS), .TARGET_BASES(HBM_BASES),")
    lines.append("    .TARGET_WIDTHS(HBM_ADDR_WIDTHS)) u_monitor (")
    lines.append("    .clk(clk), .rst(rst), .m_awvalid(m_awvalid), .m_awready(m_awready),")
    lines.append("    .m_awaddr(m_awaddr), .m_awid(m_awid), .m_arvalid(m_arvalid),")
    lines.append("    .m_arready(m_arready), .m_araddr(m_araddr), .m_arid(m_arid));")
    lines.append("  initial begin")
    lines.append("    wait (&master_done);")
    lines.append("    repeat (3) @(posedge clk);")
    lines.append("    u_monitor.check_coverage();")
    lines.append("    $display(\"PASS: hbm_fabric_tb %0d ingress x %0d HBM targets\", N_IN, N_HBM);")
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
    (output_dir/"hbm_tb.sv").write_text(generate_top(meta))
    (output_dir/"manifest.json").write_text(json.dumps(meta, indent=2)+"\n")
    print(f"Validated {len(meta['subsystems'])} subsystems; HBM DV: {meta['ingress']} ingress x {meta['target_count']} targets")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=ROOT/"config/soc.yaml")
    parser.add_argument("--out",type=Path,default=ROOT/"generated/hbm")
    args=parser.parse_args()
    try:
        run(args.config,args.out)
    except ConfigError as exc:
        print("Configuration error:",exc,file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
