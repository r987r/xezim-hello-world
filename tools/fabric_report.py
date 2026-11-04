#!/usr/bin/env python3
"""Publish a read-only, address-accurate SoC fabric inventory and route matrix.

This *does not* estimate router latency or claim reserved DMA/controllers work.
FlooGen profiles and the shared super-NoC manifest are the routing authority;
interface_contracts supplies planned budgets, never independently proven RTL caps.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from math import ceil
from statistics import median
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class FabricReportError(ValueError):
    pass


def number(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def windows(endpoint):
    regions = endpoint.get("addr_range") or []
    return [regions] if isinstance(regions, dict) else regions


def owner(network, subsystem_names):
    for name in sorted(subsystem_names, key=len, reverse=True):
        if network.startswith(name + "_"):
            return name
    if network.startswith("global_"):
        return "global"
    raise FabricReportError(f"unknown owning subsystem for {network}")


def contract_port(network, endpoint, subsystem):
    if network.startswith("global_data"):
        return "global_data." + endpoint + "_in" if endpoint.startswith("compute") and not endpoint.endswith("_sram") else None
    if network.startswith("global_config"):
        if endpoint.startswith("compute") and not endpoint.endswith("_regs"):
            return "global_config." + endpoint + "_in"
        if endpoint.endswith("_regs"):
            return "global_config." + endpoint[:-5] + "_out"
        return None
    if network == subsystem + "_local_data":
        return {
            "cpu": f"{subsystem}.local_data.cpu_in",
            "dma": f"{subsystem}.local_data.dma_in",
            "sram": f"{subsystem}.local_data.sram_out",
            "global_out": f"{subsystem}.local_data.global_out",
        }.get(endpoint)
    if network == subsystem + "_local_config":
        return f"{subsystem}.local_config." + {
            "cpu": "cpu_in", "global_in": "global_in",
            "dma_regs": "dma_csr_out", "global_out": "global_out",
            "reset_ctrl": "reset_ctrl_out",
        }.get(endpoint, "") if endpoint in {
            "cpu", "global_in", "dma_regs", "global_out", "reset_ctrl"} else None
    return None


def xy_routers(start, stop, network):
    x, y = start
    xx, yy = stop
    nodes = [f"{network}.router_{x}_{y}"]
    while x != xx:
        x += 1 if xx > x else -1
        nodes.append(f"{network}.router_{x}_{y}")
    while y != yy:
        y += 1 if yy > y else -1
        nodes.append(f"{network}.router_{x}_{y}")
    return nodes


def prepare_networks(manifest, root):
    networks = {}
    for name, entry in sorted(manifest["networks"].items()):
        profile = yaml.safe_load((root / entry["config"]).read_text())
        if profile["routing"]["route_algo"] != "XY":
            raise FabricReportError(f"{name}: only upstream-generated XY routing is characterized")
        dims = profile["routers"][0]["array"]
        if dims[0] * dims[1] != entry["routers"]:
            raise FabricReportError(f"{name}: router count mismatch")
        ports = {e["name"]: e for e in profile["endpoints"]}
        if len(ports) != entry["endpoint_count"]:
            raise FabricReportError(f"{name}: endpoint count mismatch")
        positions = {}
        for link in profile["connections"]:
            if link["src"] not in ports or link["src"] in positions or link["dst"] != "router":
                raise FabricReportError(f"{name}: bad or duplicated NI attachment")
            coords = tuple(link["dst_idx"])
            if len(coords) != 2 or not (0 <= coords[0] < dims[0] and 0 <= coords[1] < dims[1]):
                raise FabricReportError(f"{name}: out-of-range NI attachment")
            positions[link["src"]] = coords
        if positions.keys() != ports.keys():
            raise FabricReportError(f"{name}: missing NI attachment")
        protocols = {p["name"]: p for p in profile["protocols"]}
        networks[name] = {"entry": entry, "profile": profile, "ports": ports,
                          "positions": positions, "protocols": protocols}
    return networks


def trace(start, address, networks, links):
    """Follow upstream FlooGen decoder + shared cross-network wiring."""
    current, seen, stages, names = start, set(), [], []
    while current not in seen:
        seen.add(current)
        network, ingress = current.split(".", 1)
        if network not in networks or ingress not in networks[network]["ports"]:
            raise FabricReportError(f"invalid route endpoint {current}")
        n = networks[network]
        matches = [name for name, ep in n["ports"].items()
                   if ep.get("sbr_port_protocol") and any(
                       number(r["base"]) <= address < number(r["base"]) + number(r["size"])
                       for r in windows(ep))]
        if len(matches) != 1:
            raise FabricReportError(f"{current}: ambiguous/missing decoder for 0x{address:x}: {matches}")
        egress = matches[0]
        path = xy_routers(n["positions"][ingress], n["positions"][egress], network)
        stages.append({"kind": "mesh", "network": network, "from": current,
                       "to": f"{network}.{egress}", "routers": path,
                       "router_links": len(path) - 1, "latency_cycles": None})
        names.append(network)
        out = f"{network}.{egress}"
        if out not in links:
            return out, stages, names
        dst = links[out]
        stages.append({"kind": "inter_mesh_axi", "from": out, "to": dst,
                       "router_links": 0, "latency_cycles": None})
        current = dst
    raise FabricReportError(f"cyclic NoC route from {start} @ 0x{address:x}")


def build(soc, knobs, noc_manifest, networks, super_manifest, chip_manifest, ports):
    address_map = {plane: {e["name"]: e for e in soc["address_map"][plane]}
                   for plane in ("data", "config")}
    targets = []
    for plane, entries in address_map.items():
        for name, r in sorted(entries.items()):
            targets.append({"name": name, "plane": plane, "address_base": f"0x{number(r['base']):x}",
                            "address_size": f"0x{number(r['size']):x}",
                            "target_read_latency_cycles": None,
                            "target_write_latency_cycles": None,
                            "latency_status": "unmeasured"})
    target_by_name = {t["name"]: t for t in targets}
    contract_ports = ports
    actors = chip_manifest["axi_actors"]
    names = {s["name"] for s in soc["subsystems"]}
    inventory = []
    for netname, n in sorted(networks.items()):
        sub = owner(netname, names)
        plane = n["entry"]["plane"]
        for epname, ep in sorted(n["ports"].items()):
            role = "initiator" if ep.get("mgr_port_protocol") else "target"
            protocols = ep.get("mgr_port_protocol") or ep.get("sbr_port_protocol")
            if len(protocols) != 1 or protocols[0] not in n["protocols"]:
                raise FabricReportError(f"{netname}.{epname}: invalid protocol")
            protocol = n["protocols"][protocols[0]]
            cname = contract_port(netname, epname, sub)
            budget = contract_ports.get(cname) if cname else None
            if budget is None:
                budget = knobs["defaults"]["axi4" if plane == "data" else "axi4_lite"]
            identity = f"{netname}.{epname}"
            actor = actors.get(identity, {"kind": "interconnect", "label": "Inter-NoC fabric boundary"})
            inventory.append({"name": identity, "subsystem": sub, "fabric": netname,
                              "interface_name": f"{epname}_axi_{'in' if role == 'initiator' else 'out'}",
                              "role": role, "plane": plane, "protocol": "axi4_transport",
                              "endpoint_protocol": "axi4_lite" if plane == "config" else "axi4",
                              "data_bits": protocol["data_width"], "addr_bits": protocol["addr_width"],
                              "id_bits": protocol["id_width"], "max_burst_beats": budget["max_burst_beats"],
                              "max_pending_reads_budget": budget["max_pending_reads"],
                              "max_pending_writes_budget": budget["max_pending_writes"],
                              "budget_source": cname if cname in contract_ports else "plane_default",
                              "fabric_shared_max_txns": n["entry"]["native_parameters"]["MaxTxns"],
                              "fabric_max_unique_ids": n["entry"]["native_parameters"]["MaxUniqueIds"],
                              "clock_signal": "clk_i", "clock_domain": "soc_single_clock",
                              "clock_frequency_hz": None,
                              "integration": actor["kind"], "actor": actor["label"],
                              "router": f"{netname}.router_{n['positions'][epname][0]}_{n['positions'][epname][1]}",
                              "address_windows": [{"base": f"0x{number(x['base']):x}",
                                                   "size": f"0x{number(x['size']):x}"} for x in windows(ep)]})
    # Physical controller ports are not integrated; the logical AXI models behind
    # the existing target crossbar still need explicit inventory rows.
    for memory in soc["memory_targets"]:
        target = memory["name"]
        sub = target.split(".")[0]
        port_name = f"{sub}.memory_data.{target.split('.')[-1]}_out"
        contract = contract_ports.get(port_name)
        if contract is None:
            raise FabricReportError(f"missing target interface contract: {port_name}")
        inventory.append({"name": target, "subsystem": sub,
                          "fabric": f"{sub}.memory_data", "interface_name": port_name,
                          "role": "target", "plane": "data", "protocol": "axi4_model",
                          "endpoint_protocol": "axi4", "data_bits": contract["data_bits"],
                          "addr_bits": contract["addr_bits"], "id_bits": contract["id_bits"],
                          "max_burst_beats": contract["max_burst_beats"],
                          "max_pending_reads_budget": contract["max_pending_reads"],
                          "max_pending_writes_budget": contract["max_pending_writes"],
                          "budget_source": port_name, "fabric_shared_max_txns": None,
                          "fabric_max_unique_ids": None, "clock_signal": "clk_i",
                          "clock_domain": "soc_single_clock", "clock_frequency_hz": None,
                          "integration": "behavioral_memory_model",
                          "actor": "AXI-backed SRAM model, not a DDR/HBM controller",
                          "router": None,
                          "address_windows": [{"base": target_by_name[target]["address_base"],
                                               "size": target_by_name[target]["address_size"]}]})
    by_interface = {p["name"]: p for p in inventory}
    links = {}
    linked_inputs = set()
    for line in super_manifest["connections"]:
        a, b = line["from"], line["to"]
        if a in links or b in linked_inputs or a not in by_interface or b not in by_interface:
            raise FabricReportError(f"duplicate/unknown inter-mesh link {a} -> {b}")
        if by_interface[a]["role"] != "target" or by_interface[b]["role"] != "initiator":
            raise FabricReportError(f"invalid inter-mesh direction {a} -> {b}")
        if any(by_interface[a][attr] != by_interface[b][attr]
               for attr in ("plane", "addr_bits", "data_bits", "id_bits")):
            raise FabricReportError(f"incompatible inter-mesh AXI widths {a} -> {b}")
        links[a] = b
        linked_inputs.add(b)
    masters = [f"{m['network']}.{m['endpoint']}" for m in super_manifest["masters"]]
    if len(masters) != len(set(masters)):
        raise FabricReportError("duplicate external initiator")
    routes, matrix = [], []
    for m in super_manifest["masters"]:
        source = f"{m['network']}.{m['endpoint']}"
        if source not in by_interface or by_interface[source]["role"] != "initiator":
            raise FabricReportError(f"missing external initiator: {source}")
        plane = m["plane"]
        for target in (t for t in targets if t["plane"] == plane):
            label, base, size = target["name"], number(target["address_base"]), number(target["address_size"])
            candidates = [r for r in m["regions"] if number(r["base"]) <= base and
                          base + size <= number(r["base"]) + number(r["size"])]
            if not candidates:
                matrix.append({"source": source, "target": label, "plane": plane,
                               "access": "none", "route_id": None})
                continue
            if len(candidates) != 1:
                raise FabricReportError(f"multiple matching windows: {source} -> {label}")
            permission = candidates[0]["access"]
            if permission not in ("read", "read_write"):
                raise FabricReportError(f"unknown access policy {permission}")
            final, stages, visited = trace(source, base, networks, links)
            expected = candidates[0]["destination"]
            actual = "s_" + final.replace(".", "_", 1)
            if actual != expected or visited != candidates[0]["networks"]:
                raise FabricReportError(f"route/manifest divergence {source} -> {label}: "
                                        f"{actual}/{visited} != {expected}/{candidates[0]['networks']}")
            if label.startswith("memory0.") and label in {x["name"] for x in soc["memory_targets"]}:
                if not final.endswith(".target_crossbar"):
                    raise FabricReportError(f"{label}: missing memory crossbar")
                stages.append({"kind": "memory_crossbar", "from": final, "to": label,
                               "router_links": 0, "latency_cycles": None})
            else:
                real_name = ("boot." + final.split(".")[-1][5:] if final.endswith((".boot_rom", ".boot_flash"))
                             else final.split("_local_")[0] + "." + final.split(".")[-1])
                aliases = {"boot_rom": "boot.rom", "boot_flash": "boot.flash",
                           "controller_regs": "memory0.ctrl", "dma_regs": label,
                           "reset_ctrl": "boot.reset_ctrl"}
                real_name = aliases.get(final.split(".")[-1], real_name)
                if real_name != label:
                    raise FabricReportError(f"route terminates at {real_name} not {label}")
            stages.append({"kind": "target_service", "from": label, "to": label,
                           "router_links": 0, "latency_cycles": None})
            if trace(source, base + size - 1, networks, links)[0] != final:
                raise FabricReportError(f"window changes endpoint: {source} -> {label}")
            route_id = f"{source}->{label}"
            hops = sum(s["router_links"] for s in stages)
            route = {"id": route_id, "source": source, "target": label, "plane": plane,
                     "access": "R" if permission == "read" else "RW",
                     "source_integration": by_interface[source]["integration"],
                     "target_integration": ("behavioral_memory_model" if label in {x["name"] for x in soc["memory_targets"]}
                                            else by_interface[final]["integration"]),
                     "network_count": len(visited), "router_links": hops,
                     "inter_mesh_links": len(visited) - 1,
                     "network_path": visited, "stages": stages,
                     "latency": {"transaction": "one_beat", "request_cycles": None,
                                 "target_read_cycles": None, "target_write_cycles": None,
                                 "response_cycles": None, "end_to_end_read_cycles": None,
                                 "end_to_end_write_cycles": None, "status": "unmeasured"}}
            route["one_beat_observations"] = []
            routes.append(route)
            matrix.append({"source": source, "target": label, "plane": plane,
                           "access": route["access"], "route_id": route_id,
                           "router_links": hops, "inter_mesh_links": len(visited) - 1,
                           "target_read_latency_cycles": None,
                           "target_write_latency_cycles": None})
    return {"schema_version": 1,
            "source_of_truth": ["config/soc.yaml", "config/interface_contracts.yaml",
                                "gen/noc/floonoc/manifest.json", "gen/noc/floonoc/**/floogen.yaml",
                                "gen/supernoc/manifest.json", "gen/chip/manifest.json"],
            "scope": "chip_boot_configuration_topology",
            "timing_note": "All latencies are unmeasured. Router/link counts are topology-only. "
                           "No clock frequency, idle one-beat RTL timing or physical memory latency is asserted.",
            "summary": {"interfaces": len(inventory), "initiators": len(masters),
                        "targets": len(targets), "reachable_routes": len(routes),
                        "meshes": len(networks), "cross_mesh_links": len(links)},
            "interfaces": inventory, "targets": targets, "initiators": masters,
            "matrix": matrix, "routes": routes}



def attach_one_beat_observations(report, entries, output, source_sha):
    """Attach genuine B/RLAST endpoint timing; never infer router-hop timing.

    Only clean, complete, successful, bound captures are eligible. Old-source
    runs are kept distinguishable and carry their own commit + test scope.
    """
    routes = {r["id"]: r for r in report["routes"]}
    by_source = defaultdict(list)
    target_info = {t["name"]: t for t in report["targets"]}
    for route in report["routes"]:
        by_source[route["source"]].append(route)
    for entry in entries:
        if not entry.get("axi") or not entry.get("passed") or "axi-transactions.json" not in entry.get("assets", []):
            continue
        path = output / Path(entry["path"]).parent / "axi-transactions.json"
        trace = json.loads(path.read_text())
        run = trace["run"]
        if not run.get("capture_bound") or run.get("capture_overflow") or run.get("dirty") is not False:
            continue
        matched = defaultdict(list)
        for item in trace["sections"]["axi"]["transactions"]:
            if (item.get("role") != "initiator" or item.get("status") != "complete"
                    or item.get("expected_beats") != 1 or item.get("issues")
                    or number(item.get("response") or 0) != 0 or item.get("latency_ps") is None):
                continue
            for route in by_source[item["monitor"]]:
                target = target_info[route["target"]]
                address = number(item["address"])
                if (route["plane"] == item["plane"] and
                    number(target["address_base"]) <= address <
                        number(target["address_base"]) + number(target["address_size"])):
                    matched[(route["id"], item["operation"])].append(number(item["latency_ps"]))
        for (route_id, operation), samples in matched.items():
            samples.sort()
            routes[route_id]["one_beat_observations"].append({
                "operation": operation, "count": len(samples),
                "min_ps": samples[0], "median_ps": median(samples),
                "p95_ps": samples[ceil(0.95 * len(samples)) - 1],
                "source_sha": entry["source_sha"],
                "matches_site_source": entry["source_sha"] == source_sha,
                "test_scope": entry["target"], "simulator": entry["engine"],
                "run_report": entry["path"],
                "scope": "initiator_end_to_end_B_or_RLAST_not_router_hops",
            })
    return report


def load(root=ROOT):
    from interface_contracts import build as resolve_contracts
    soc = yaml.safe_load((root / "config/soc.yaml").read_text())
    knobs = yaml.safe_load((root / "config/interface_contracts.yaml").read_text())
    noc_root = root / "gen/noc/floonoc"
    noc_manifest = json.loads((noc_root / "manifest.json").read_text())
    networks = prepare_networks(noc_manifest, noc_root)
    resolved = resolve_contracts(soc, knobs, networks["global_data"]["profile"])
    super_manifest = json.loads((root / "gen/supernoc/manifest.json").read_text())
    chip_manifest = json.loads((root / "gen/chip/manifest.json").read_text())
    return build(soc, knobs, noc_manifest, networks, super_manifest,
                 chip_manifest, resolved["ports"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.dumps(load(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data)
    else:
        print(data)


if __name__ == "__main__":
    main()
