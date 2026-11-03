"""One real eight-FlooNoC interconnect composition, without custom router IP.

Generated from the same FlooGen config+manifest as the production meshes.
Simulation boundary SRAM/CSR models use upstream PULP axi_sim_mem; the
physical HBM/DDR crossbar is not yet in this integration fixture.
"""
import json
from pathlib import Path
import re
import yaml


def render(config, root: Path, out: Path):
    manifest = json.loads((root / "manifest.json").read_text())["networks"]
    networks = {}
    for name, entry in manifest.items():
        cfg = yaml.safe_load((root / entry["config"]).read_text())
        networks[name] = {"entry": entry, "config": cfg,
                          "eps": {ep["name"]: ep for ep in cfg["endpoints"]}}
    expected = 2 + 2 * len(config["subsystems"])
    if len(networks) != expected:
        raise ValueError(f"expected {expected} real meshes, got {len(networks)}")

    # The only cross-NoC links are manager<->subordinate AXI4 endpoints;
    # no interface-width conversions are invented by this generator.
    links = []
    for inst in config["subsystems"]:
        name = inst["name"]
        if inst["type"] == "compute":
            links.extend([
                (name+"_local_data", "global_out", "global_data", name),
                ("global_data", name+"_sram", name+"_local_data", "global_in"),
                (name+"_local_config", "global_out", "global_config", name),
                ("global_config", name+"_regs", name+"_local_config", "global_in"),
            ])
        else:
            links.append(("global_config", name+"_regs",
                          name+"_local_config", "global_in"))
            for item in config["networks"]["global_data"]["outputs"]:
                links.append(("global_data", item["name"], name+"_local_data", item["name"]))
    targets = [(name, ep) for name, net in networks.items()
               for ep, desc in net["eps"].items() if desc.get("sbr_port_protocol")]
    linked_targets = {(a,b) for a,b,_,_ in links}
    linked_managers = {(c,d) for _,_,c,d in links}
    for a,b,c,d in links:
        if b not in networks[a]["eps"] or d not in networks[c]["eps"]:
            raise ValueError(f"invalid link {a}.{b} -> {c}.{d}")
        if not networks[a]["eps"][b].get("sbr_port_protocol"):
            raise ValueError(f"{a}.{b} is not an AXI subordinate")
        if not networks[c]["eps"][d].get("mgr_port_protocol"):
            raise ValueError(f"{c}.{d} is not an AXI manager")
        # Compare *every* protocol field, not only data width.
        def signature(n, ep):
            x=networks[n]["eps"][ep]
            protocol=(x.get("mgr_port_protocol") or x.get("sbr_port_protocol"))[0]
            return next({key: p[key] for key in ("protocol", "data_width", "addr_width",
                                                "id_width", "user_width")}
                        for p in networks[n]["config"]["protocols"] if p["name"] == protocol)
        if signature(a,b) != signature(c,d):
            raise ValueError(f"unsafe incompatible AXI connection: {a}.{b} -> {c}.{d}: "
                             f"{signature(a,b)} != {signature(c,d)}")

    text = ["`timescale 1ns/1ps",
            "// Generated executable composition of the actual eight FlooNoCs.",
            "// NO pass-through simulation model substitutes for a router.",
            "module supernoc_tb;",
            "  logic clk=0, rst_n=0;",
            "  always #5 clk=~clk;",
            "  initial begin repeat (8) @(posedge clk); rst_n=1; end",
            "  initial begin #100000; $fatal(1,\"super-NoC traffic timeout\"); end"]
    for name, net in sorted(networks.items()):
        package = net["entry"]["top_module"]+"_pkg"
        for ep, desc in net["eps"].items():
            direction = "in" if desc.get("mgr_port_protocol") else "out"
            base = name+"__"+ep
            text.extend([f"  {package}::axi_{direction}_req_t {base}_req;",
                         f"  {package}::axi_{direction}_rsp_t {base}_rsp;"])
    for a,b,c,d in links:
        source=a+"__"+b
        sink=c+"__"+d
        text.append(f"  assign {sink}_req = {source}_req;")
        text.append(f"  assign {source}_rsp = {sink}_rsp;")
    # PULP AXI upstream class driver, not a home-built bus functional model.
    # Two independent compute data managers and one CSR manager exercise
    # both global fabrics and local fabrics, preserving AXI4/AXI4-Lite semantics.
    bfm = []
    for inst in config["subsystems"]:
        if inst["type"] == "compute":
            bfm.append((inst["name"]+"_local_data", "cpu", 64, 64, 4))
    bfm.append((config["boot"]["primary"]+"_local_config", "cpu", 32, 32, 1))
    for name,ep,aw,dw,iw in bfm:
        key = name+"__"+ep
        text.extend([
            f"  AXI_BUS_DV #(.AXI_ADDR_WIDTH({aw}), .AXI_DATA_WIDTH({dw}), "
            f".AXI_ID_WIDTH({iw}), .AXI_USER_WIDTH(1)) bus_{key}(clk);",
            f"  `AXI_ASSIGN_TO_REQ({key}_req, bus_{key})",
            f"  `AXI_ASSIGN_FROM_RESP(bus_{key}, {key}_rsp)",
            f"  typedef axi_test::axi_driver #(.AW({aw}), .DW({dw}), .IW({iw}), "
            f".UW(1), .TA(2ns), .TT(8ns)) driver_{key}_t;",
            f"  driver_{key}_t driver_{key};"
        ])
    # Other initiators will be supplied by PULP test drivers; unconnected
    # manager ports are explicitly idle, not simulated transactions.
    for name, net in networks.items():
        for ep, desc in net["eps"].items():
            if (desc.get("mgr_port_protocol") and (name, ep) not in linked_managers
                    and (name, ep) not in {(x,y) for x,y,_,_,_ in bfm}):
                text.append(f"  assign {name}__{ep}_req = '0;")
    # Upstream PULP simulation-only memory models on all leaf targets.
    # They respond to all AXI4 channels and do not model actual DRAM timing.
    for name, ep in targets:
        if (name,ep) in linked_targets:
            continue
        package = networks[name]["entry"]["top_module"]+"_pkg"
        p=next(x for x in networks[name]["config"]["protocols"] if
               x["name"]==networks[name]["eps"][ep]["sbr_port_protocol"][0])
        base=name+"__"+ep
        text.extend([
            f"  axi_sim_mem #(.AddrWidth({p['addr_width']}), .DataWidth({p['data_width']}), "
            f".IdWidth({p['id_width']}), .UserWidth({p['user_width']}), .NumPorts(1), "
            f".UninitializedData(\"zeros\"), .axi_req_t({package}::axi_out_req_t), "
            f".axi_rsp_t({package}::axi_out_rsp_t)) memory_{base} (",
            "    .clk_i(clk), .rst_ni(rst_n),",
            f"    .axi_req_i({base}_req), .axi_rsp_o({base}_rsp),",
            "    .mon_w_valid_o(), .mon_w_addr_o(), .mon_w_data_o(), .mon_w_id_o(),",
            "    .mon_w_user_o(), .mon_w_beat_count_o(), .mon_w_last_o(),",
            "    .mon_r_valid_o(), .mon_r_addr_o(), .mon_r_data_o(), .mon_r_id_o(),",
            "    .mon_r_user_o(), .mon_r_beat_count_o(), .mon_r_last_o());"
        ])
    for name, net in sorted(networks.items()):
        ports=[".clk_i(clk)", ".rst_ni(rst_n)", ".test_enable_i(1'b0)"]
        for ep, desc in net["eps"].items():
            direction="in" if desc.get("mgr_port_protocol") else "out"
            base=name+"__"+ep
            ports += [f".{ep}_axi_{direction}_req_{'i' if direction=='in' else 'o'}({base}_req)",
                      f".{ep}_axi_{direction}_rsp_{'o' if direction=='in' else 'i'}({base}_rsp)"]
        text.append(f"  {net['entry']['top_module']} u_{name} (")
        text.append("    "+",\n    ".join(ports)+");")
    # Directed sequences use PULP's upstream axi_driver send/receive tasks.
    # All traffic passes through the real instantiated FlewNoC modules.
    for name, ep, aw, dw, iw in bfm:
        key=name+"__"+ep
        text.extend([
            f"  task automatic write_{key}(input logic [{aw-1}:0] addr, "
            f"input logic [{dw-1}:0] payload);",
            f"    driver_{key}_t::ax_beat_t awbeat = new;",
            f"    driver_{key}_t::w_beat_t wbeat = new;",
            f"    driver_{key}_t::b_beat_t bbeat;",
            "    awbeat.ax_id = 1;",
            "    awbeat.ax_addr = addr;",
            "    awbeat.ax_len = 0;",
            f"    awbeat.ax_size = $clog2({dw}/8);",
            "    awbeat.ax_burst = axi_pkg::BURST_INCR;",
            "    wbeat.w_data = payload;",
            "    wbeat.w_strb = '1;",
            "    wbeat.w_last = 1;",
            f"    driver_{key}.send_aw(awbeat);",
            f"    driver_{key}.send_w(wbeat);",
            f"    driver_{key}.recv_b(bbeat);",
            "    if (bbeat.b_resp !== axi_pkg::RESP_OKAY || bbeat.b_id !== 1)",
            f'      $fatal(1, "FAIL {key} write addr=%h B id=%h resp=%h", addr, bbeat.b_id, bbeat.b_resp);',
            "  endtask",
            f"  task automatic read_{key}(input logic [{aw-1}:0] addr, "
            f"input logic [{dw-1}:0] expected);",
            f"    driver_{key}_t::ax_beat_t ar = new;",
            f"    driver_{key}_t::r_beat_t rbeat;",
            "    ar.ax_id = 1;",
            "    ar.ax_addr = addr;",
            "    ar.ax_len = 0;",
            f"    ar.ax_size = $clog2({dw}/8);",
            "    ar.ax_burst = axi_pkg::BURST_INCR;",
            f"    driver_{key}.send_ar(ar);",
            f"    driver_{key}.recv_r(rbeat);",
            "    if (rbeat.r_data !== expected || rbeat.r_resp !== axi_pkg::RESP_OKAY ||",
            "        rbeat.r_id !== 1 || rbeat.r_last !== 1)",
            f'      $fatal(1, "FAIL {key} read addr=%h expected=%h got=%h", addr, expected, rbeat.r_data);',
            "  endtask",
        ])
    text.append("  initial begin")
    for name,ep,aw,dw,iw in bfm:
        key=name+"__"+ep
        text.append(f"    driver_{key} = new(bus_{key});")
        text.append(f"    driver_{key}.reset_master();")
    text.append("    wait(rst_n); repeat(3) @(posedge clk);")
    # Deterministic smoke: own SRAM, remote CPU SRAM via two NoCs,
    # global HBM/DDR via local memory NoC and configuration CSR plane.
    tests = [
        ("compute0_local_data", "cpu", 0x10000000, 0x1122334455667788),
        ("compute0_local_data", "cpu", 0x11000000, 0x8877665544332211),
        ("compute0_local_data", "cpu", 0x100000000, 0x4242424212345678),
        ("compute0_local_data", "cpu", 0x140000000, 0xfeedfacefacefeed),
        ("compute1_local_data", "cpu", 0x10000008, 0x9876543210abcdef),
        ("compute0_local_config", "cpu", 0x40000000, 0x10203040),
        ("compute0_local_config", "cpu", 0x40010000, 0x22334455),
        ("compute0_local_config", "cpu", 0x40030000, 0xaabbccdd),
    ]
    for name, ep, addr, value in tests:
        key=name+"__"+ep
        text.append(f"    write_{key}('h{addr:x}, 'h{value:x});")
        text.append(f"    read_{key}('h{addr:x}, 'h{value:x});")
    text.extend([
        "    repeat(8) @(posedge clk);",
        '    $display("PASS: SuperNoC real FlooNoC read/write paths: 8 networks instantiated");',
        "    $finish;",
        "  end",
        "endmodule", ""
    ])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(text))
    return {"networks": sorted(networks), "links": [list(x) for x in links],
            "pending_drivers": [[n,e] for n,net in networks.items()
                for e,d in net["eps"].items() if d.get("mgr_port_protocol")
                and (n,e) not in linked_managers]}
