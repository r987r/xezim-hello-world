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
    # Other initiators will be supplied by PULP test drivers; unconnected
    # manager ports are explicitly idle, not simulated transactions.
    for name, net in networks.items():
        for ep, desc in net["eps"].items():
            if desc.get("mgr_port_protocol") and (name, ep) not in linked_managers:
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
    text.extend(["  // Only structural connectivity established. Traffic will be",
                 "  // enabled by upstream PULP AXI agents in this SAME TB.",
                 "endmodule", ""])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(text))
    return {"networks": sorted(networks), "links": [list(x) for x in links],
            "pending_drivers": [[n,e] for n,net in networks.items()
                for e,d in net["eps"].items() if d.get("mgr_port_protocol")
                and (n,e) not in linked_managers]}
